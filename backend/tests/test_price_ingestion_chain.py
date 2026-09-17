# -*- coding: utf-8 -*-
"""Sheet to database to API: the chain a finance estimate's price travels.

THE DEFECT THESE WERE WRITTEN FOR

A supplier typing «تماس بگیرید» into the price sheet used to blank a product's price
everywhere. The rejected row arrived with a newer business date than the last real price,
won the `DISTINCT ON` that picks the current observation, and the API answered null --
`invalid_source`, no number -- while a perfectly good price sat in the same table three
days older.

A row is rejected because it could not be believed. It must not thereby become the thing
everyone believes. `SelectionTests` pins that, in both directions: the believable price is
what is returned, AND the fact that a newer row was refused is reported rather than
hidden, because a reader owed a three-day-old number is also owed the reason.

THE DATE RULES

Two tests exist only to say what must never happen: `fetched_at` and today are not
business dates. A price is for a day the supplier quoted. The day we happened to read the
sheet is a different fact and lives in `fetchedAt`; substituting either would state a
price for a day nobody quoted, which is worse than having no price.
"""

import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_price_rows import decide_row
from app.finance.schemas.material_prices import MaterialPriceResponse
from app.finance.services.material_price_import import (MaterialPriceImportError,
                                                        MaterialPriceSheetNotConfigured)
from test_material_price_api import FakeRepository, observation, service

CELLS = {"source": "Mashhad Foolad", "productId": "REBAR-1",
         "محصول": "میلگرد آجدار ۸ A3", "قیمت": "95500",
         "تاریخ آپدیت ورک فلو": "1405-06-22"}


def decided(**changes):
    return decide_row(worksheet="steel -Rebar", row_number=2,
                      cells=dict(CELLS, **changes))


class ValidationTests(unittest.TestCase):
    """A row becomes a price only if it says who, what, how much and for when."""

    def test_a_complete_row_is_accepted(self):
        row = decided()
        self.assertEqual("accepted", row.status)
        self.assertEqual(date(2026, 9, 13), row.workflow_date_gregorian)

    def test_every_unusable_price_is_refused(self):
        for text in ("تماس بگیرید", "ناموجود", "توافقی", "-", "", "  ", "abc"):
            with self.subTest(text):
                row = decided(**{"قیمت": text})
                self.assertEqual("rejected", row.status)
                self.assertIsNone(row.price_irr)

    def test_a_blank_product_name_is_refused(self):
        self.assertEqual("rejected", decided(**{"محصول": ""}).status)

    def test_a_blank_source_is_refused(self):
        self.assertEqual("rejected", decided(source="").status)

    def test_an_unknown_product_id_prefix_is_refused(self):
        """The prefix is what says which category a row belongs to."""
        row = decided(productId="WIDGET-1")
        self.assertEqual("rejected", row.status)
        self.assertIn("not a known category", " ".join(row.reasons))

    def test_a_rejected_row_keeps_what_the_cell_said(self):
        row = decided(**{"قیمت": "تماس بگیرید"})
        self.assertEqual("تماس بگیرید", row.raw_price)
        self.assertIn("تماس بگیرید", " ".join(row.reasons))


class DateTests(unittest.TestCase):
    def test_a_blank_date_is_refused_and_nothing_stands_in_for_it(self):
        row = decided(**{"تاریخ آپدیت ورک فلو": ""})
        self.assertEqual("rejected", row.status)
        self.assertIsNone(row.workflow_date_gregorian)

    def test_fetched_at_is_never_used_as_the_business_date(self):
        """Two different facts. The day we read the sheet is not the day it was quoted."""
        row = decided()
        self.assertEqual(date(2026, 9, 13), row.workflow_date_gregorian)
        # The parser is handed no clock at all, so there is nothing for it to substitute.
        self.assertNotIn("fetched", " ".join(row.reasons).lower())

    def test_today_is_never_used_as_the_business_date(self):
        for written in ("", "1405/13/40", "فردا"):
            with self.subTest(written):
                row = decided(**{"تاریخ آپدیت ورک فلو": written})
                self.assertIsNone(row.workflow_date_gregorian)
                self.assertNotEqual(date.today(), row.workflow_date_gregorian)


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    """Which observation becomes the current price."""

    @staticmethod
    def valid(**changes):
        return observation(validation_status="valid", **changes)

    @staticmethod
    def refused(**changes):
        return observation(validation_status="rejected", normalized_price_irr=None,
                           raw_price="تماس بگیرید",
                           validation_reasons=["price is not a number: 'تماس بگیرید'"],
                           **changes)

    async def test_a_newer_rejected_row_does_not_hide_a_valid_price(self):
        """The defect this module exists for, at the service boundary.

        The repository is what orders these, so the fake stands in for a database that
        has already applied the rule: the valid row comes first. What is asserted here is
        that the service reports the valid price and does not let the refusal blank it.
        """
        rows, _ = await service(rows=[self.valid()]).current(object())
        self.assertEqual(Decimal("955000"), rows[0]["current_price_irr"])
        self.assertEqual("resolved", rows[0]["resolution_status"])

    async def test_the_skipped_row_is_reported_rather_than_hidden(self):
        rows, _ = await service(rows=[self.valid(
            rejected_after_date=date(2026, 9, 16),
            rejected_after_raw_price="تماس بگیرید",
            rejected_after_reasons=["price is not a number: 'تماس بگیرید'"])],
        ).current(object())
        self.assertEqual(date(2026, 9, 16), rows[0]["rejected_after_date"])
        self.assertEqual("تماس بگیرید", rows[0]["rejected_after_raw_price"])
        self.assertTrue(rows[0]["rejected_after_reasons"])

    async def test_nothing_is_reported_as_skipped_when_the_newest_row_was_chosen(self):
        rows, _ = await service(rows=[self.valid()]).current(object())
        self.assertIsNone(rows[0]["rejected_after_date"])
        self.assertEqual([], rows[0]["rejected_after_reasons"])

    async def test_a_listing_whose_rows_are_all_invalid_still_appears(self):
        """"We have this product and cannot price it" is an answer. Silence is not."""
        rows, _ = await service(rows=[self.refused()]).current(object())
        self.assertEqual(1, len(rows))
        self.assertIsNone(rows[0]["current_price_irr"])
        self.assertEqual("invalid_source", rows[0]["resolution_status"])

    async def test_the_ordering_rule_lives_in_sql_and_says_what_it_prefers(self):
        """Pinned as text because the ordering IS the fix and a silent edit undoes it."""
        import inspect
        from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
        source = inspect.getsource(PsycopgMaterialPriceRepository.latest_observations)
        self.assertIn("o.validation_status = 'valid'", source)
        self.assertIn("o.workflow_date_gregorian IS NOT NULL) DESC", source)
        self.assertIn("o.workflow_date_gregorian DESC NULLS LAST", source)
        self.assertIn("o.fetched_at DESC, o.id", source)


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_new_fields_are_declared_and_supplied(self):
        rows, _ = await service(rows=[observation()]).current(object())
        for field in ("rejected_after_date", "rejected_after_raw_price",
                      "rejected_after_reasons"):
            self.assertIn(field, MaterialPriceResponse.model_fields, field)
            self.assertIn(field, rows[0], field)

    def test_the_import_refusals_are_coded_business_errors_not_500s(self):
        self.assertEqual(409, MaterialPriceImportError.status)
        self.assertEqual("MATERIAL_PRICE_IMPORT_REFUSED", MaterialPriceImportError.code)
        self.assertEqual("MATERIAL_PRICE_SHEET_NOT_CONFIGURED",
                         MaterialPriceSheetNotConfigured.code)
        self.assertTrue(issubclass(MaterialPriceSheetNotConfigured,
                                   MaterialPriceImportError),
                        "the CLI catches the base class and must keep working")

    def test_the_trigger_endpoint_takes_no_caller_supplied_source(self):
        """A caller who could name the sheet could point this host at any sheet at all.

        The assertion is about SOURCE, not about the parameter count: `force` and
        `dueOnly` were added later and say when to import, never what to import from.
        Pinning the exact list made this fail for the right endpoint gaining the right
        parameter, which is a guard testing its own wording rather than the rule.
        """
        import inspect
        from app.finance import router
        params = list(inspect.signature(router.start_material_price_import).parameters)
        # `triggerSource` contains "source" and is not one: it names the CALLER, for the
        # audit trail. The rule is about where prices are read FROM, so it is spelled out
        # rather than approximated by a substring.
        self.assertEqual([], [p for p in params
                              if "sheet" in p.lower() or "url" in p.lower()
                              or p.lower() in ("source", "sourceurl", "pricesource")],
                         "the sheet is configuration and must never be a request field")


if __name__ == "__main__":
    unittest.main()
