"""The server-side Google Sheets fetch, and the reasons it cannot be turned on the network.

The point of moving this off the browser was CSP and the module's no-external-request
rule. The point of these tests is the other half: that accepting a URL from a caller did
not hand anyone a way to make this server fetch something else.
"""

import asyncio
import unittest
import urllib.error

from app.finance.services.google_sheet import (
    GoogleSheetError,
    MAX_BYTES,
    export_url,
    fetch_sheet_as_xlsx,
    parse_sheet_link,
)

XLSX = b"PK\x03\x04" + b"\x00" * 64
SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"


def run(coro):
    return asyncio.run(coro)


class LinkParsingTests(unittest.TestCase):
    def test_a_sheet_link_gives_up_its_document_and_its_tab(self):
        self.assertEqual(parse_sheet_link(SHEET), ("1AbCdEfGhIjKlMnOpQrStUvWxYz", None))
        self.assertEqual(parse_sheet_link(SHEET + "#gid=1842"),
                         ("1AbCdEfGhIjKlMnOpQrStUvWxYz", "1842"))

    def test_a_published_to_web_link_is_accepted(self):
        document, _ = parse_sheet_link(
            "https://docs.google.com/spreadsheets/d/e/2PACX-1vABCDEFGHIJKLMNOPQRSTUVWXYZ/pubhtml")
        self.assertEqual(document, "2PACX-1vABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def test_the_tab_travels_to_the_export(self):
        """Reading the wrong sheet of a workbook is the quiet way an import imports nothing."""
        self.assertEqual(
            export_url("ABC", "77"),
            "https://docs.google.com/spreadsheets/d/ABC/export?format=xlsx&gid=77")
        self.assertEqual(
            export_url("ABC", None),
            "https://docs.google.com/spreadsheets/d/ABC/export?format=xlsx")


class NotAnOpenProxyTests(unittest.TestCase):
    """Nothing a caller sends is ever used as an address."""

    def test_addresses_that_are_not_google_sheets_are_refused_before_any_request(self):
        for hostile in [
            "http://169.254.169.254/latest/meta-data/",      # cloud metadata
            "http://127.0.0.1:8000/api/projects",            # this server
            "http://localhost/admin",
            "file:///etc/passwd",
            "https://evil.example.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz",
            # A host that merely ends in something google-ish.
            "https://docs.google.com.evil.example/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz",
            "",
            "   ",
        ]:
            with self.subTest(hostile=hostile):
                with self.assertRaises(GoogleSheetError):
                    parse_sheet_link(hostile)

    def test_a_google_link_that_is_not_a_sheet_is_refused(self):
        for other in ["https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
                      "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view",
                      "https://www.google.com/"]:
            with self.subTest(other=other):
                with self.assertRaises(GoogleSheetError):
                    parse_sheet_link(other)

    def test_the_fetched_address_is_built_here_not_taken_from_the_caller(self):
        asked = []

        def download(url):
            asked.append(url)
            return XLSX

        # Everything after the document id -- a query, a fragment, another host in the
        # path -- is discarded, because only the id and the gid are ever read.
        run(fetch_sheet_as_xlsx(
            SHEET + "?x=http://169.254.169.254/#gid=5", download=download))
        self.assertEqual(
            asked,
            ["https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz"
             "/export?format=xlsx&gid=5"])


class FetchFailureTests(unittest.TestCase):
    def test_a_workbook_comes_back_as_bytes(self):
        self.assertEqual(run(fetch_sheet_as_xlsx(SHEET, download=lambda url: XLSX)), XLSX)

    def test_a_private_sheet_is_named_as_one(self):
        def refused(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

        with self.assertRaises(GoogleSheetError) as caught:
            run(fetch_sheet_as_xlsx(SHEET, download=lambda url: refused(url)))
        self.assertIn("not public", str(caught.exception))

    def test_a_sign_in_page_is_told_apart_from_a_workbook_by_its_bytes(self):
        """Google answers a private sheet with 200 and HTML, so the status cannot say."""
        with self.assertRaises(GoogleSheetError) as caught:
            run(fetch_sheet_as_xlsx(SHEET, download=lambda url: b"<!doctype html><title>Sign in"))
        self.assertIn("not public", str(caught.exception))

    def test_a_sheet_larger_than_the_cap_is_refused_before_it_is_parsed(self):
        with self.assertRaises(GoogleSheetError) as caught:
            run(fetch_sheet_as_xlsx(SHEET, download=lambda url: b"PK" + b"x" * MAX_BYTES))
        self.assertIn("too large", str(caught.exception))

    def test_an_unreachable_google_does_not_surface_a_raw_socket_error(self):
        def unreachable(url):
            raise urllib.error.URLError("no route to host")

        with self.assertRaises(GoogleSheetError) as caught:
            run(fetch_sheet_as_xlsx(SHEET, download=lambda url: unreachable(url)))
        self.assertIn("could not reach", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
