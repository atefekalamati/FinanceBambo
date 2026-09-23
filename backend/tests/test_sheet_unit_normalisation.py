# -*- coding: utf-8 -*-
"""What a supplier typed, and which registry code it is -- or that it is none.

The sheet is typed by people on different keyboards. «کیلو» and «كيلو» are the same word
with one letter from two Unicode blocks, «متر مربع» and «مترمربع» are the same unit with a
space nobody meant, and a map keyed on one spelling silently fails on the other. The
failure is quiet: the price imports, the unit does not resolve, and the row simply never
prices anything.

The rule that matters more than any of the mappings: a unit this system has no CODE for
returns None. It does not get a name invented for it here. The module docstring records
why -- an earlier draft invented `piece`, `g`, `cm` and `branch` as names of its own, and
a price and a Finance resource could then agree about a unit only by accident.
"""

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.unit_registry import UNIT_REGISTRY
from app.finance.services.material_price_resolution import (SHEET_UNIT_SPELLINGS,
                                                            UNMAPPED_SHEET_SPELLINGS,
                                                            canonical_unit,
                                                            normalize_unit_text)


class TheVocabularyIsTheRegistrysTests(unittest.TestCase):
    """The map is an input normaliser, not a second vocabulary."""

    def test_every_mapping_lands_on_a_code_the_registry_has(self):
        for spelling, code in SHEET_UNIT_SPELLINGS.items():
            if code is None:
                continue
            with self.subTest(spelling):
                self.assertIn(code, UNIT_REGISTRY,
                              "%r maps to %r, which the registry does not have" %
                              (spelling, code))

    def test_a_unit_with_no_registry_code_stays_unrecognised(self):
        """«بسته», «رول», «برگ», «جفت», «ست» are real units. The registry has none of them.

        Naming them here would produce a unit with no dimension and no conversion: it
        would read as resolved and could never be crossed with anything, which is worse
        than being unrecognised because nothing would ask about it again.
        """
        for spelling in UNMAPPED_SHEET_SPELLINGS:
            with self.subTest(spelling):
                self.assertIsNone(canonical_unit(spelling))

    def test_count_has_one_code_and_it_is_the_registrys(self):
        """`each`, not `number` -- the registry decides the name, not the sheet."""
        self.assertNotIn("number", UNIT_REGISTRY)
        for spelling in ("عدد", "دانه", "تعداد", "قطعه", "piece", "number", "pcs"):
            with self.subTest(spelling):
                self.assertEqual("each", canonical_unit(spelling))


class WhatTheSheetActuallyWritesTests(unittest.TestCase):
    CASES = (
        ("کیلوگرم", "kg"), ("کیلو", "kg"), ("kg", "kg"), ("KG", "kg"),
        ("kilogram", "kg"), ("گرم", "g"), ("تن", "ton"), ("ton", "ton"),
        ("متر", "m"), ("مترطول", "m"), ("meter", "m"),
        ("سانتیمتر", "cm"), ("میلیمتر", "mm"),
        ("مترمربع", "m2"), ("متر مربع", "m2"), ("sqm", "m2"), ("m2", "m2"),
        ("مترمکعب", "m3"), ("متر مکعب", "m3"), ("cmb", "m3"), ("cubic meter", "m3"),
        ("شاخه", "branch"), ("کیسه", "bag"),
        ("روز", "day"), ("ساعت", "hour"),
    )

    def test_each_spelling_resolves(self):
        for spelling, code in self.CASES:
            with self.subTest(spelling):
                self.assertEqual(code, canonical_unit(spelling))


class TwoSpellingsOfOneWordTests(unittest.TestCase):
    def test_an_arabic_keyboard_and_a_persian_one_agree(self):
        """«كيلو» carries U+0643; «کیلو» carries U+06A9. One word, two blocks."""
        self.assertEqual(canonical_unit("کیلو"), canonical_unit("كيلو"))
        self.assertEqual("kg", canonical_unit("كيلو گرم"))

    def test_spaces_nobody_meant_do_not_hide_a_unit(self):
        for spelling in ("متر مربع", "متر  مربع", "  مترمربع  "):
            with self.subTest(spelling):
                self.assertEqual("m2", canonical_unit(spelling))
        self.assertEqual("cm", canonical_unit("سانتی متر"))
        self.assertEqual("mm", canonical_unit("میلی متر"))

    def test_the_zero_width_non_joiner_is_not_a_different_unit(self):
        self.assertEqual("cm", canonical_unit("سانتی‌متر"))

    def test_persian_and_arabic_digits_fold_to_ascii(self):
        self.assertEqual("m2", normalize_unit_text("m۲"))
        self.assertEqual("m2", normalize_unit_text("m٢"))

    def test_normalisation_does_not_decide_what_the_unit_is(self):
        """It reduces text. Naming is `canonical_unit`'s job, and the split is the point."""
        self.assertEqual("furlong", normalize_unit_text(" FURLONG "))
        self.assertIsNone(canonical_unit("furlong"))


class NothingIsGuessedTests(unittest.TestCase):
    def test_a_missing_unit_does_not_become_a_count(self):
        """The most dangerous default there is: «no unit» silently meaning «each».

        A price per nothing multiplied by a quantity of something is a number with no
        meaning, and it would look exactly like a real one.
        """
        for absent in (None, "", "   ", "‌"):
            with self.subTest(repr(absent)):
                self.assertIsNone(canonical_unit(absent))

    def test_an_unknown_spelling_is_not_returned_as_itself(self):
        """Returning the raw text would let it travel on looking like a code."""
        for unknown in ("furlong", "بشکه", "qty", "واحد سفارشی"):
            with self.subTest(unknown):
                self.assertIsNone(canonical_unit(unknown))

    def test_an_exact_registry_code_is_never_altered(self):
        for code in sorted(UNIT_REGISTRY):
            with self.subTest(code):
                self.assertEqual(code, canonical_unit(code))


if __name__ == "__main__":
    unittest.main()
