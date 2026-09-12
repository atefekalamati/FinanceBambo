# -*- coding: utf-8 -*-
"""The one door MPP files come through. Every test here is an attack or an accident.

No database, no JVM, no MPXJ: path containment, size, emptiness and magic bytes are pure
filesystem questions, and they are exactly the checks that must hold even when everything
else is broken.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import coreint.mpp_files as mpp_files
from coreint.mpp_files import (OLE2_MAGIC, MppFileEmpty, MppFileError, MppFileNotFound,
                               MppFileNotStable, MppFileTooLarge, MppFormatUnsupported,
                               MppPathNotAllowed, resolve_import_file)

#: A minimal byte-stream that passes the OLE2 magic check. Not a parseable schedule --
#: parseability is MPXJ's question, and this module deliberately does not ask it.
FAKE_MPP = OLE2_MAGIC + b"\x00" * 64


class ImportRootTests(unittest.TestCase):
    def setUp(self):
        self._root = tempfile.TemporaryDirectory()
        self.root = Path(self._root.name)
        (self.root / "terrace.mpp").write_bytes(FAKE_MPP)
        # Something worth stealing, OUTSIDE the root.
        self.secret = self.root.parent / ("secret-%s.env" % os.getpid())
        self.secret.write_bytes(b"DSN=postgres://user:password@db/prod")

    def tearDown(self):
        self._root.cleanup()
        try:
            self.secret.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------- the happy door
    def test_a_real_file_inside_the_root_resolves_with_its_facts(self):
        resolved = resolve_import_file(self.root, "terrace.mpp")
        self.assertEqual("terrace.mpp", resolved.relative_name)
        self.assertEqual(len(FAKE_MPP), resolved.size_bytes)
        self.assertEqual(64, len(resolved.sha256), "a full sha256 hex digest")

    def test_a_subdirectory_inside_the_root_is_still_inside(self):
        (self.root / "archive").mkdir()
        (self.root / "archive" / "old.mpp").write_bytes(FAKE_MPP)
        resolved = resolve_import_file(self.root, "archive/old.mpp")
        self.assertEqual("archive/old.mpp", resolved.relative_name)

    def test_a_persian_file_name_is_ordinary(self):
        (self.root / "زمان بندی پل.mpp").write_bytes(FAKE_MPP)
        resolved = resolve_import_file(self.root, "زمان بندی پل.mpp")
        self.assertEqual(len(FAKE_MPP), resolved.size_bytes)

    def test_a_name_with_spaces_is_ordinary(self):
        (self.root / "my plan v2.mpp").write_bytes(FAKE_MPP)
        self.assertEqual("my plan v2.mpp",
                         resolve_import_file(self.root, "my plan v2.mpp").relative_name)

    # ----------------------------------------------------------------------- traversal
    def test_dot_dot_cannot_leave_the_root(self):
        with self.assertRaises(MppPathNotAllowed):
            resolve_import_file(self.root, "../%s" % self.secret.name)

    def test_a_deeper_dot_dot_chain_cannot_leave_either(self):
        with self.assertRaises(MppPathNotAllowed):
            resolve_import_file(self.root, "a/b/../../../%s" % self.secret.name)

    def test_an_absolute_path_is_not_a_relative_name(self):
        # Path joining with an absolute path REPLACES the root -- resolve() then puts the
        # candidate outside it, and containment refuses. This is the classic bypass.
        with self.assertRaises((MppPathNotAllowed, MppFormatUnsupported)):
            resolve_import_file(self.root, str(self.secret))

    def test_an_absolute_path_inside_the_root_is_still_refused(self):
        # Accepting it would confirm the server's directory layout to whoever guessed
        # it, and the absolute string would persist as `relative_name` into rows and
        # logs that must never carry one.
        with self.assertRaises(MppPathNotAllowed):
            resolve_import_file(self.root, str(self.root / "terrace.mpp"))

    def test_a_rooted_or_drive_relative_name_is_refused(self):
        for anchored in ("/terrace.mpp", "\\terrace.mpp", "C:terrace.mpp"):
            with self.subTest(anchored=anchored):
                with self.assertRaises((MppPathNotAllowed, MppFormatUnsupported)):
                    resolve_import_file(self.root, anchored)

    def test_a_symlink_pointing_outside_the_root_is_refused(self):
        link = self.root / "innocent.mpp"
        try:
            link.symlink_to(self.secret)
        except OSError:
            # Windows denies symlink creation to unprivileged users. A directory JUNCTION
            # is the same escape (resolve() follows it identically) and needs no
            # privilege, so the containment check still gets its real test.
            outside = self.root.parent / ("outside-%s" % os.getpid())
            outside.mkdir()
            self.addCleanup(__import__("shutil").rmtree, outside, True)
            (outside / "stolen.mpp").write_bytes(FAKE_MPP)
            import _winapi
            _winapi.CreateJunction(str(outside), str(self.root / "evil"))
            with self.assertRaises(MppPathNotAllowed):
                resolve_import_file(self.root, "evil/stolen.mpp")
            return
        with self.assertRaises((MppPathNotAllowed, MppFormatUnsupported)):
            resolve_import_file(self.root, "innocent.mpp")

    # ------------------------------------------------------------------------ the file
    def test_a_missing_file_is_named_by_its_relative_name_only(self):
        with self.assertRaises(MppFileNotFound) as caught:
            resolve_import_file(self.root, "nope.mpp")
        self.assertNotIn(str(self.root), str(caught.exception),
                         "the absolute path must not leak into the message")

    def test_an_empty_file_is_refused_before_any_parser_sees_it(self):
        (self.root / "empty.mpp").write_bytes(b"")
        with self.assertRaises(MppFileEmpty):
            resolve_import_file(self.root, "empty.mpp")

    def test_the_wrong_extension_is_refused(self):
        (self.root / "plan.xlsx").write_bytes(FAKE_MPP)
        with self.assertRaises(MppFormatUnsupported):
            resolve_import_file(self.root, "plan.xlsx")

    def test_a_renamed_non_ole2_file_is_refused_by_its_bytes(self):
        (self.root / "fake.mpp").write_bytes(b"PK\x03\x04 actually a zip" + b"\x00" * 40)
        with self.assertRaises(MppFormatUnsupported):
            resolve_import_file(self.root, "fake.mpp")

    def test_an_oversized_file_is_refused_with_the_limit_named(self):
        (self.root / "big.mpp").write_bytes(FAKE_MPP + b"\x00" * (2 * 1024 * 1024))
        with self.assertRaises(MppFileTooLarge) as caught:
            resolve_import_file(self.root, "big.mpp", max_size_mb=1)
        self.assertIn("1", str(caught.exception))

    def test_a_blank_name_is_a_missing_file_not_a_directory_read(self):
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                with self.assertRaises(MppFileNotFound):
                    resolve_import_file(self.root, blank)

    def test_a_missing_root_refuses_everything(self):
        with self.assertRaises(MppPathNotAllowed):
            resolve_import_file(self.root / "never-created", "terrace.mpp")

    # ------------------------------------------------------------------------- hashing
    def test_the_hash_is_of_the_exact_bytes(self):
        import hashlib
        resolved = resolve_import_file(self.root, "terrace.mpp")
        self.assertEqual(hashlib.sha256(FAKE_MPP).hexdigest(), resolved.sha256)

    def test_two_different_files_hash_differently(self):
        (self.root / "other.mpp").write_bytes(OLE2_MAGIC + b"\x01" * 64)
        a = resolve_import_file(self.root, "terrace.mpp").sha256
        b = resolve_import_file(self.root, "other.mpp").sha256
        self.assertNotEqual(a, b)


class FileStillArrivingTests(unittest.TestCase):
    """Half a copy passes the empty gate and the magic gate, and must not pass the door.

    Measured before this existed: 819,200 of a real schedule's 1,638,400 bytes resolved
    cleanly, with a digest describing half a file. The parser would then have answered
    "corrupt schedule" -- a sentence about the FILE, when the truth was about the CLOCK.
    """

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.path = self.root / "arriving.mpp"

    def test_a_file_that_grows_while_it_is_read_is_refused(self):
        # The signature is driven rather than the disk raced: a test that has to win a race
        # passes on a fast disk and fails on a slow one, which is worse than no test. Two
        # answers, in order -- what the file looked like before the hash pass, and after.
        self.path.write_bytes(FAKE_MPP)
        answers = iter([(len(FAKE_MPP), 1), (len(FAKE_MPP) + 1024, 2)])
        with unittest.mock.patch.object(mpp_files, "stable_signature",
                                        lambda _path: next(answers)):
            with self.assertRaises(MppFileNotStable) as caught:
                resolve_import_file(str(self.root), "arriving.mpp")
        self.assertEqual("MPP_FILE_NOT_STABLE", caught.exception.code)
        # The refusal never names the absolute path, like every other refusal here.
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_a_file_rewritten_to_the_same_length_is_still_refused(self):
        # Size alone would miss this: the same number of bytes, different bytes. The mtime
        # is the half of the signature that catches it.
        self.path.write_bytes(FAKE_MPP)
        answers = iter([(len(FAKE_MPP), 111), (len(FAKE_MPP), 222)])
        with unittest.mock.patch.object(mpp_files, "stable_signature",
                                        lambda _path: next(answers)):
            with self.assertRaises(MppFileNotStable):
                resolve_import_file(str(self.root), "arriving.mpp")

    def test_the_signature_reads_both_halves_from_the_file(self):
        self.path.write_bytes(FAKE_MPP)
        size, mtime = mpp_files.stable_signature(self.path)
        self.assertEqual(len(FAKE_MPP), size)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)

    def test_a_file_that_holds_still_resolves_exactly_as_before(self):
        # The guard must not turn an ordinary read into a refusal.
        self.path.write_bytes(FAKE_MPP)
        resolved = resolve_import_file(str(self.root), "arriving.mpp")
        self.assertEqual(len(FAKE_MPP), resolved.size_bytes)
        self.assertEqual(64, len(resolved.sha256))
        self.assertEqual("arriving.mpp", resolved.relative_name)

    def test_the_refusal_is_its_own_code_and_not_a_format_complaint(self):
        # An operator reading MPP_FORMAT_UNSUPPORTED goes looking for a bad file. There
        # isn't one, and the two codes must not be mistaken for each other.
        self.assertNotEqual(MppFileNotStable.code, MppFormatUnsupported.code)
        self.assertTrue(issubclass(MppFileNotStable, MppFileError))


if __name__ == "__main__":
    unittest.main()
