# -*- coding: utf-8 -*-
"""Where an MPP file is allowed to come from, and nothing else.

Core owns MPP file handling. This module is the only place a path from configuration or
from a caller is turned into a file the importer may open, and it exists because every one
of its refusals is an attack or an accident that has actually happened somewhere:

  * a caller passing ``..\\..\\secrets.env`` as a "schedule";
  * a symlink inside the import root pointing at a file outside it;
  * an empty file produced by a copy that died, which a parser would report as "corrupt
    schedule" and a planner would read as "my file is broken";
  * a file that is still ARRIVING -- half a copy already carries the OLE2 magic and a
    non-zero size, so neither of the gates above notices it, and the parser's "corrupt
    schedule" is the wrong sentence for "wait two seconds";
  * a 2 GB upload that is not a schedule at all.

The rule is single and total: **a file is only readable if its fully-resolved real path is
inside the fully-resolved import root.** Everything below is that rule plus reporting.

One thing this module cannot promise on its own: that the bytes it hashed are the bytes
somebody later parses. It hands back a path, and opening that path again is a second read
of a file that may have moved on. `FinanceMppSyncService._parse_a_private_copy` closes that
by copying the file, checking the copy against this digest, and parsing the copy -- so the
question stops being about timing and becomes about there having been one set of bytes.

Errors carry stable ``code`` values (the contract the API and logs use). The MESSAGE never
contains the absolute filesystem path -- callers log and return ``relative_name`` only, so
a response cannot leak the server's directory layout. The absolute path lives on the
exception object for local debugging and stays out of ``str()``.
"""

import hashlib
from pathlib import Path

#: The only extension the importer accepts. MPXJ can read more formats, but this pipeline
#: is specified for MPP; widening it is a decision, not a default.
ALLOWED_SUFFIX = ".mpp"

#: OLE2 compound-file magic. Every real .mpp starts with it; a renamed .xlsx or a text file
#: does not, and refusing here is cheaper and clearer than a parser stack trace.
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

DEFAULT_MAX_FILE_SIZE_MB = 100


class MppFileError(RuntimeError):
    """Base of every refusal. ``code`` is stable; the message never carries the full path."""

    code = "MPP_FILE_ERROR"

    def __init__(self, message, *, absolute_path=None):
        super().__init__(message)
        #: For local debugging only. Never serialized into API responses or log lines.
        self.absolute_path = absolute_path


class MppFileNotFound(MppFileError):
    code = "MPP_FILE_NOT_FOUND"


class MppPathNotAllowed(MppFileError):
    code = "MPP_PATH_NOT_ALLOWED"


class MppFileTooLarge(MppFileError):
    code = "MPP_FILE_TOO_LARGE"


class MppFileEmpty(MppFileError):
    code = "MPP_FILE_EMPTY"


class MppFormatUnsupported(MppFileError):
    code = "MPP_FORMAT_UNSUPPORTED"


class MppFileNotStable(MppFileError):
    """The file changed while it was being read, so no single version of it was seen.

    Distinct from `MppFormatUnsupported` on purpose. A schedule that is mid-copy is not a
    bad file and the operator has nothing to fix -- the answer is to ask again in a
    moment, and a caller can only know that if the refusal says so.
    """

    code = "MPP_FILE_NOT_STABLE"


class ResolvedMppFile:
    """A file that passed every gate, with the facts the importer needs.

    ``relative_name`` is the identity a caller may see and log. ``path`` is for opening
    the file and for nothing else.
    """

    def __init__(self, path, relative_name, size_bytes, sha256):
        self.path = path
        self.relative_name = relative_name
        self.size_bytes = size_bytes
        self.sha256 = sha256

    def __repr__(self):  # keep accidental logging safe too
        return "ResolvedMppFile(%r, %d bytes, sha=%s...)" % (
            self.relative_name, self.size_bytes, self.sha256[:12])


def stable_signature(path):
    """What must not change while the file is being read: its length and its clock.

    Both, because a write that replaces bytes without changing the length still moves the
    mtime, and a file appended to in a single burst can land on the same mtime tick.

    Its own function so the check reads as one idea in `resolve_import_file`, and so a test
    can state "the file changed underneath us" without having to win a race against a real
    writer on a disk of unknown speed.
    """
    info = path.stat()
    return (info.st_size, info.st_mtime_ns)


def resolve_import_file(import_root, relative_name,
                        max_size_mb=DEFAULT_MAX_FILE_SIZE_MB) -> ResolvedMppFile:
    """The one door: a relative name inside the configured root, or a refusal.

    ``relative_name`` is what an API or a job configuration supplies. It is joined to the
    root and then ``resolve()``d, which collapses ``..`` AND follows symlinks -- so a link
    that lives inside the root but points outside it fails the same containment check as a
    plain traversal. The root itself is resolved first for the same reason.
    """
    if not relative_name or not str(relative_name).strip():
        raise MppFileNotFound("no file name was given")
    # An anchored name is refused even when it would land INSIDE the root: accepting it
    # confirms the server's directory layout to whoever guessed it, and the string then
    # persists as `relative_name` into rows, responses and logs that must never carry
    # absolute paths. `drive or root` also catches Windows drive-relative ("C:x") and
    # rooted ("\\x") forms that is_absolute() alone misses.
    supplied = Path(str(relative_name))
    if supplied.drive or supplied.root:
        raise MppPathNotAllowed("an absolute path is not a relative file name")
    root = Path(import_root)
    if not root.is_dir():
        # A misconfigured root is an operator problem, not a caller problem, but the
        # refusal code is the same family: nothing may be read.
        raise MppPathNotAllowed("the MPP import root is not configured or does not exist")
    root = root.resolve()

    candidate = (root / str(relative_name)).resolve()
    # Containment is checked on RESOLVED paths: `..` is already collapsed and symlinks are
    # already followed, so escaping via either fails here, with one error for both.
    if root != candidate and root not in candidate.parents:
        raise MppPathNotAllowed("the requested file is outside the MPP import root")

    if candidate.suffix.lower() != ALLOWED_SUFFIX:
        raise MppFormatUnsupported("only .mpp files are accepted",
                                   absolute_path=candidate)
    if not candidate.is_file():
        raise MppFileNotFound("MPP file does not exist: %s" % relative_name,
                              absolute_path=candidate)

    size = candidate.stat().st_size
    if size == 0:
        raise MppFileEmpty("MPP file is empty: %s" % relative_name,
                           absolute_path=candidate)
    limit = int(max_size_mb) * 1024 * 1024
    if size > limit:
        raise MppFileTooLarge(
            "MPP file exceeds the configured limit of %s MB: %s"
            % (max_size_mb, relative_name), absolute_path=candidate)

    # Hash and magic in one pass over the bytes. The digest is the idempotency key of the
    # whole import -- an unchanged file must never produce a second snapshot -- so it is
    # computed here, once, on the exact bytes that will be parsed.
    before = stable_signature(candidate)
    digest = hashlib.sha256()
    first = b""
    with candidate.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            if not first:
                first = chunk[:8]
            digest.update(chunk)
    if not first.startswith(OLE2_MAGIC):
        raise MppFormatUnsupported(
            "file is not an OLE2 document, so it is not a real .mpp: %s" % relative_name,
            absolute_path=candidate)

    # Did the file hold still while that pass ran? A copy in progress grows underneath the
    # reader, and the digest above would then describe no version of the file that ever
    # existed -- half of one and half of the next. Size AND mtime, because a write that
    # replaces bytes without changing the length still moves the mtime.
    #
    # This refuses rather than waits. How long an import may block is a policy belonging to
    # whoever schedules it, not to the door it comes through; the code says which refusal
    # this is so a caller can decide to ask again.
    if stable_signature(candidate) != before:
        raise MppFileNotStable(
            "the file changed while it was being read, so it is still arriving: %s"
            % relative_name, absolute_path=candidate)

    return ResolvedMppFile(candidate, str(relative_name), size, digest.hexdigest())
