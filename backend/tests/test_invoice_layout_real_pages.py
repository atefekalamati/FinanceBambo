# -*- coding: utf-8 -*-
"""The layout engine against the real stored invoices, with the real model.

Slow and environment-dependent: it loads PaddleOCR and reads images off disk, so it skips
by name when either is absent. What it pins is the thing synthetic geometry cannot -- that
the provider really does return boxes for a real photograph, and that the engine's answer
on these particular pages is the one that was measured rather than one that drifted.

THE THREE-PAGE INVOICE

Pages 1 and 2 are item tables and page 3 is a summary. All three currently reconstruct
NOTHING, and that is the correct outcome, not a failure of this code:

    page 1   72 lines, mean confidence 0.47, no heading row read at all
    page 2   87 lines, mean confidence 0.45, likewise
    page 3   24 lines, mean confidence 0.80, and it is a summary page

The recogniser returned `'ld'bdd`, `are`, `xl` and `e55` where product names and amounts
belong -- the loaded model is `arabic_PP-OCRv5`, which mangles the Persian-only letters
these pages are full of. A table rebuilt from that would be shaped correctly and filled
with nonsense, so the structural rule and the confidence band both refuse it.

The letterhead invoice is the control: same code, legible page, and the table comes back
whole. Without it these assertions would be satisfied by a function that always returns
None.
"""

import sys
import unittest
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from extraction import layout

ORG = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
PROJECT = "terrace"

#: Both checkouts are looked in: a virtualenv and the stored files live in whichever one
#: the host was run from, and this test should not care which.
ROOTS = (Path("E:/bamboo/FINANCE-integrate/backend/devhost/.files"),
         Path("E:/bamboo/FINANCE/backend/devhost/.files"))

PAGE_ONE = "46dd5e04-00e4-45bd-8e62-d1b5c059548b.jpg"
PAGE_TWO = "b390969d-fa77-409b-95d3-a20978b614b0.jpg"
PAGE_THREE = "f03db762-4108-4283-bfd3-759808e552cd.jpg"
LETTERHEAD = "867425d6-d6ba-40bb-b18f-f8602e48e9c0.png"


def stored(name):
    for root in ROOTS:
        candidate = root / ORG / PROJECT / name
        if candidate.is_file():
            return candidate
    return None


class RealPageTestCase(unittest.TestCase):
    _read = {}

    @classmethod
    def setUpClass(cls):
        try:
            from extraction.providers.paddle_ocr import PaddleOCRProvider
        except ImportError as error:
            raise unittest.SkipTest("PaddleOCR is not installed here (%s). Use the "
                                    "canonical interpreter: see docs/DEV_RUNTIME_FA.md"
                                    % error)
        cls._provider = PaddleOCRProvider()

    def read(self, name):
        """One recognition per image per run, however many tests ask for it."""
        if name not in RealPageTestCase._read:
            path = stored(name)
            if path is None:
                self.skipTest("%s is not stored locally" % name)
            RealPageTestCase._read[name] = self._provider.read(str(path))
        return RealPageTestCase._read[name]


class GeometrySurvivesTests(RealPageTestCase):
    def test_every_recognised_line_carries_its_position(self):
        """The fault this whole change is about: the boxes were being read past."""
        result = self.read(PAGE_ONE)
        lines = result.get("lines")
        self.assertTrue(lines, "the provider must return per-line detail")
        self.assertTrue(all(entry.get("box") for entry in lines),
                        "every line of a real photograph should have a box")
        self.assertEqual(len(lines), result["lineCount"])

    def test_the_older_keys_still_mean_what_they_meant(self):
        """`lines` is additive. A caller that only wants the text is unaffected."""
        result = self.read(PAGE_ONE)
        for key in ("text", "confidence", "provider", "language", "lineCount"):
            self.assertIn(key, result)
        self.assertEqual("\n".join(entry["text"] for entry in result["lines"]),
                         result["text"])


class LegiblePageTests(RealPageTestCase):
    """The control. Same engine, a page the model can actually read."""

    def test_a_legible_invoice_reconstructs_its_whole_table(self):
        table = layout.reconstruct(self.read(LETTERHEAD)["lines"])
        self.assertIsNotNone(table, "the engine must find a table it can find")
        self.assertEqual("header", table.column_source)
        self.assertTrue(table.trustworthy)
        self.assertGreaterEqual(len(table.rows), 3)
        for role in ("name", "unit", "quantity", "unit_price", "amount"):
            self.assertIn(role, table.roles)

    def test_the_cells_of_the_first_row_are_the_document_s_own(self):
        table = layout.reconstruct(self.read(LETTERHEAD)["lines"])
        first = table.rows[0]
        self.assertIn("سیمان", layout.normalize(first["name"]))
        self.assertEqual("100", layout.normalize(first["quantity"]))
        self.assertIn("120", first["amount"])


class ThreePageInvoiceTests(RealPageTestCase):
    def test_the_item_pages_are_read_but_not_believed(self):
        """A table IS spatially present on both. Its cells are not readable, so no line
        items are offered -- which is the refusal, not a failure to try."""
        for name in (PAGE_ONE, PAGE_TWO):
            with self.subTest(name[:8]):
                result = self.read(name)
                self.assertTrue(result["lines"], "the page was read")
                self.assertGreater(len(layout.group_rows(
                    layout.lines_from(result["lines"]))), 10,
                    "and it has the shape of a table")
                self.assertIsNone(layout.reconstruct(result["lines"]),
                                  "but nothing readable enough to offer as line items")

    def test_no_heading_row_was_recognised_on_the_item_pages(self):
        """Why the header-free path exists at all. The heading band is shaded and the
        model returned nothing for it."""
        for name in (PAGE_ONE, PAGE_TWO):
            with self.subTest(name[:8]):
                rows = layout.group_rows(layout.lines_from(self.read(name)["lines"]))
                index, anchors = layout.find_header(rows)
                self.assertIsNone(index)
                self.assertEqual({}, anchors)

    def test_the_summary_page_is_recognised_as_one(self):
        result = self.read(PAGE_THREE)
        rows = layout.group_rows(layout.lines_from(result["lines"]))
        index, anchors = layout.find_header(rows)
        self.assertEqual(layout.SUMMARY_PAGE, layout.classify(rows, index, anchors))
        self.assertIsNone(layout.reconstruct(result["lines"]),
                          "a summary page has no line items by definition")


if __name__ == "__main__":
    unittest.main()
