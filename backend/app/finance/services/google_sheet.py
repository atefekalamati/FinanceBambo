"""Fetching a Google Sheet as the .xlsx the import already accepts.

The browser must not do this. Every path the finance client calls is resolved against
the page's own origin and refused otherwise, the module's own rule is that it makes no
external browser request, and the BAMBO dashboard's Content-Security-Policy names
`connect-src 'self'` -- so a fetch to docs.google.com from the page works only until
that header stops being report-only. The server has none of those constraints, so the
server does it and hands the bytes to the same parser an upload reaches.

Nothing about the import contract changes: what comes back is a workbook, judged by
`parse_excel` exactly as an uploaded one is.

## Why this is not an open proxy

The link a person pastes is never fetched. It is parsed for two things -- a document id
and an optional tab id -- and both are matched against patterns that admit nothing but
Google's own identifiers. The URL that is actually requested is then BUILT here, from
those two values and a constant host.

That is what keeps this from being a server-side request forgery hole. A caller cannot
reach `169.254.169.254`, or a service on localhost, or anything else inside the network,
because no part of what they send is ever used as an address. Redirects are followed --
Google's export redirects to googleusercontent -- but only to hosts on the same short
allowlist, checked on every hop.
"""

import asyncio
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

from ..domain.errors import FinanceDomainError


class GoogleSheetError(FinanceDomainError):
    """A link that could not become a workbook, said in terms a person can act on."""

    status = 422
    code = "GOOGLE_SHEET_UNAVAILABLE"


#: Google's own document identifier. The `e/` form is a published-to-web link.
_SHEET_ID = re.compile(r"/spreadsheets/d/(?:e/)?(?P<id>[A-Za-z0-9_-]{20,})")
#: The tab, when the link names one. Reading the wrong sheet of a workbook is the most
#: common way an import silently imports nothing, and this is what prevents it.
_GID = re.compile(r"[#&?]gid=(?P<gid>\d+)")

#: Hosts a redirect may land on. Google's export answers from googleusercontent.
_ALLOWED_HOSTS = ("docs.google.com", "drive.google.com", "googleusercontent.com")

#: A spreadsheet is small. Anything larger is not the thing that was asked for, and
#: reading it into memory to find that out is the mistake this avoids.
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 20


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in _ALLOWED_HOSTS)


def parse_sheet_link(value: str) -> tuple[str, str | None]:
    """The document and tab a link names, or a refusal.

    Anything that is not a Google Sheets address is rejected here, before a request is
    made -- including a Google address of some other kind, because a Docs or Slides
    link exports something this parser cannot read.
    """
    text = (value or "").strip()
    if not text:
        raise GoogleSheetError("a Google Sheets link is required")
    try:
        parsed = urlparse(text)
    except ValueError as exc:
        raise GoogleSheetError("that is not a valid link") from exc
    if parsed.scheme not in ("http", "https"):
        raise GoogleSheetError("a Google Sheets link must start with https://")
    if not re.fullmatch(r"(.+\.)?google\.com", (parsed.hostname or "").lower()):
        raise GoogleSheetError("that link does not point at Google Sheets")
    found = _SHEET_ID.search(parsed.path)
    if found is None:
        raise GoogleSheetError("that link does not point at a Google Sheet")
    gid = _GID.search(text)
    return found.group("id"), (gid.group("gid") if gid else None)


def export_url(document_id: str, gid: str | None) -> str:
    """The address this actually requests, built rather than accepted."""
    url = f"https://docs.google.com/spreadsheets/d/{document_id}/export?format=xlsx"
    return f"{url}&gid={gid}" if gid else url


class _AllowlistedRedirects(urllib.request.HTTPRedirectHandler):
    """Follow Google's own redirects and nothing else's."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_allowed(urlparse(newurl).hostname or ""):
            raise GoogleSheetError("Google redirected somewhere unexpected; the link was not read")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str) -> bytes:
    """Blocking read of one address. Transport only -- it judges nothing."""
    opener = urllib.request.build_opener(_AllowlistedRedirects())
    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        # One byte more than the cap, so "exactly at the limit" is not an error and
        # anything past it is caught without reading the whole of it.
        return response.read(MAX_BYTES + 1)


def _judge(content: bytes) -> bytes:
    """Is this a workbook? Separate from fetching it, because the answer is in the bytes."""
    if len(content) > MAX_BYTES:
        raise GoogleSheetError("that sheet is too large to import")
    # A private sheet answers 200 with a sign-in page rather than an error status, so the
    # status code cannot tell the two apart. The first two bytes can: a workbook is a zip.
    if not content.startswith(b"PK"):
        raise GoogleSheetError(
            "Google did not return a spreadsheet. This usually means the sheet is not "
            "public and a sign-in page came back instead."
        )
    return content


async def fetch_sheet_as_xlsx(link: str, download=_download) -> bytes:
    """A pasted link, as workbook bytes.

    Every failure a caller can cause is turned into a `GoogleSheetError` here rather than
    inside the transport, so an injected downloader is judged by exactly the rules the
    real one is -- a test that swapped it out would otherwise be exercising a path that
    does not exist in production.

    `download` is blocking and runs in a worker thread: one slow sheet must not stop
    every other request this process is serving.
    """
    document_id, gid = parse_sheet_link(link)
    try:
        content = await asyncio.to_thread(download, export_url(document_id, gid))
    except GoogleSheetError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GoogleSheetError(
                "this sheet is not public. In Google Sheets set access to "
                "'anyone with the link can view'."
            ) from exc
        raise GoogleSheetError(f"Google refused the link (status {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GoogleSheetError("the server could not reach Google Sheets") from exc
    return _judge(content)
