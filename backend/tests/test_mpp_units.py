# -*- coding: utf-8 -*-
"""Reading a schedule's units, and the two conversions on the way in.

What these defend: a unit nothing recognised stays None. The alternative -- answering
"count" to be helpful -- turns a shrug into a fact that every conversion, price and total
downstream inherits, and nothing downstream can tell it was a guess.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from coreint.finance_mpp_sync import _file_rials, _file_units
from coreint.mpp_units import normalize_unit


class UnitReadingTests(unittest.TestCase):
    def test_a_registry_code_is_read_exactly(self):
        self.assertEqual(("m", "registry", "exact"), normalize_unit("m"))
        self.assertEqual(("m3", "registry", "exact"), normalize_unit("m3"))
        self.assertEqual(("kg", "registry", "exact"), normalize_unit("kg"))

    def test_a_known_spelling_is_read_as_an_alias(self):
        for spelling in ("مترمکعب", "متر مکعب"):
            self.assertEqual(("m3", "alias", "alias"), normalize_unit(spelling))
        self.assertEqual(("m2", "alias", "alias"), normalize_unit("مترمربع"))
        self.assertEqual(("kg", "alias", "alias"), normalize_unit("کیلوگرم"))
        self.assertEqual(("hour", "alias", "alias"), normalize_unit("ساعت"))

    def test_the_files_own_misspelling_is_an_alias_because_it_is_in_the_data(self):
        # Five assignments of this project spell مترمکعب as مترمرکعب. A misspelling that
        # appears in the data and has exactly one plausible reading is an alias, not a guess.
        self.assertEqual(("m3", "alias", "alias"), normalize_unit("مترمرکعب"))

    def test_a_single_character_is_an_initial_and_never_a_unit(self):
        for initial in ("د", "ت", "ج", "پ", "غ"):
            code, source, confidence = normalize_unit(initial)
            self.assertIsNone(code)
            self.assertEqual("resource_initial", source)
            self.assertEqual("low", confidence)

    def test_something_that_is_not_a_unit_is_said_to_be_so(self):
        for text in ("واحد", "اصل", "درصد", ""):
            code, source, confidence = normalize_unit(text)
            self.assertIsNone(code)
            self.assertEqual("not_a_unit", source)

    def test_an_unrecognised_unit_is_refused_rather_than_guessed(self):
        code, source, confidence = normalize_unit("دسیمترمکعب")
        self.assertIsNone(code, "a unit nothing knows must not become one it half knows")
        self.assertEqual("none", source)
        self.assertEqual("low", confidence)

    def test_nothing_is_ever_read_from_the_resource_name(self):
        # Guessing m3 from «بتن» is a rule about what a thing usually is, and it is wrong
        # exactly when it matters. The module is not given the name and must not want it.
        import inspect
        # It is given the unit text and nothing else, so a name is not available to read.
        self.assertEqual(["raw"], list(inspect.signature(normalize_unit).parameters))
        from coreint.mpp_units import UNIT_ALIASES
        # And the table it consults maps unit words, never the names of things. A rule
        # keyed on what a thing is usually made of is wrong exactly when the schedule
        # means something else -- concrete sold by the truckload, labour by the day.
        for material in ("بتن", "میلگرد", "کارگر", "آجر", "سیمان"):
            self.assertNotIn(material, UNIT_ALIASES)

    def test_low_confidence_always_comes_with_no_unit(self):
        for text in ("د", "واحد", "دسیمترمکعب", None, "   "):
            code, _source, confidence = normalize_unit(text)
            if confidence == "low":
                self.assertIsNone(code)


class ConversionTests(unittest.TestCase):
    def test_units_come_off_the_hundred_scale_the_reader_returns(self):
        # Verified against the project's own MS Project dialog: 56000 is shown as 560.
        self.assertEqual(Decimal("560"), _file_units("56000.0"))
        self.assertEqual(Decimal("7516.4"), _file_units("751640.0"))

    def test_the_file_says_toman_and_finance_stores_rials(self):
        self.assertEqual(Decimal("728000000"), _file_rials("72800000.0", Decimal(10)))
        self.assertEqual(Decimal("13520000000"), _file_rials("1352000000", Decimal(10)))

    def test_an_absent_figure_stays_absent_through_both_conversions(self):
        self.assertIsNone(_file_units(None))
        self.assertIsNone(_file_rials(None))

    def test_a_real_zero_survives_both_conversions(self):
        self.assertEqual(Decimal(0), _file_units("0"))
        self.assertEqual(Decimal(0), _file_rials("0", Decimal(10)))

    def test_the_conversions_are_stated_once_each(self):
        source = (BACKEND_ROOT / "coreint" / "finance_mpp_sync.py").read_text(encoding="utf-8")
        self.assertEqual(1, source.count("_UNITS_SCALE = Decimal(100)"))
        self.assertEqual(1, source.count("_TOMAN_TO_RIAL = Decimal(10)"))


if __name__ == "__main__":
    unittest.main()
