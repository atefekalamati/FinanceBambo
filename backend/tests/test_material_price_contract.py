# -*- coding: utf-8 -*-
"""What the material price API promises after 0027, 0028 and 0029.

Three things are pinned here, and they fail for different reasons.

THE SNAPSHOT IS NOT THE CURRENT NAME

0027 added `product_external_id`, `product_name_snapshot` and `provider_name_snapshot` to
`price_observations`. They exist so that a price read a year ago can still say which
product it was for, under the name it had THEN. A response that quietly showed today's
name against a year-old price would be asserting something nobody recorded, so the two
identities travel in separate fields and a null snapshot stays null.

A DECLARED FIELD THAT IS ALWAYS NULL IS A CONTRACT THAT LIES

The response model declared 29 fields the service never put in the row -- every typed
specification column 0027 added, all three snapshots, and `labelledByName`, which the
frontend reads and rendered empty on every row. OpenAPI published them, the database had
them, and the shaping dict in between dropped them. `test_every_declared_field_is_supplied`
is the guard that makes that shape of bug fail here instead of on screen.

A WEIGHT WITH NO BASIS MAY NOT CROSS UNITS

Every weight in the database says basis 'unknown', because no worksheet states what a
weight is per. 27 is then 27 per branch, per metre or per piece -- and the last two differ
by more than a factor of ten. `conversionEligible` is false in that case, and the
gram/kilogram tests pin the direction of the one conversion that IS safe, because getting
it backwards is a 1,000,000x error rather than a 1000x one.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.material_specs import (SPEC_COLUMNS,
                                               WEIGHT_BASES_USABLE_FOR_CONVERSION)
from app.finance.schemas.material_prices import (MaterialPriceHistoryResponse,
                                                 MaterialPriceResponse)
from test_material_price_api import observation, service


def setting(unit, category="rebar"):
    return {"category": category, "resource_id": None, "provider_item_id": None,
            "display_unit": unit}


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_identity_travels_as_the_sheet_stated_it(self):
        rows, _ = await service(rows=[observation(
            product_external_id="RB-8-A3",
            product_name_snapshot="میلگرد آجدار ۸ A3",
            provider_name_snapshot="فولاد مشهد")]).current(object())
        self.assertEqual("RB-8-A3", rows[0]["product_id_snapshot"])
        self.assertEqual("میلگرد آجدار ۸ A3", rows[0]["product_name_snapshot"])
        self.assertEqual("فولاد مشهد", rows[0]["provider_name_snapshot"])

    async def test_a_rename_does_not_reach_back_into_the_snapshot(self):
        """The listing is called something else now. The observation is not edited."""
        rows, _ = await service(rows=[observation(
            external_name="میلگرد آجدار ۸ A3 -- کد جدید",
            provider_name="فولاد مشهد (نام جدید)",
            product_name_snapshot="میلگرد آجدار ۸ A3",
            provider_name_snapshot="فولاد مشهد")]).current(object())
        self.assertEqual("میلگرد آجدار ۸ A3", rows[0]["product_name_snapshot"])
        self.assertEqual("میلگرد آجدار ۸ A3 -- کد جدید", rows[0]["external_name"])
        self.assertNotEqual(rows[0]["product_name_snapshot"], rows[0]["external_name"])

    async def test_a_missing_snapshot_stays_missing(self):
        """The 3,821 rows written before 0027 have none, and none is the honest answer.

        Filling it from `externalName` is the one thing this must never do: the constraint
        is NOT VALID precisely because no truthful value exists for those rows.
        """
        rows, _ = await service(rows=[observation()]).current(object())
        for field in ("product_id_snapshot", "product_name_snapshot",
                      "provider_name_snapshot"):
            self.assertIsNone(rows[0][field], field)


class DeclaredFieldTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_declared_field_is_supplied(self):
        """Nothing the response model promises may be structurally absent from the row.

        `specs` is built by the router and `labelledByName` by the actor decorator, so they
        are the two exceptions; everything else must come out of the service.
        """
        rows, _ = await service(rows=[observation()]).current(object())
        supplied = set(rows[0]) | {"specs", "labelled_by_name"}
        missing = sorted(set(MaterialPriceResponse.model_fields) - supplied)
        self.assertEqual([], missing,
                         "declared by the schema, published in OpenAPI, and never set")

    async def test_the_typed_specification_columns_reach_the_reader(self):
        stored = {"weight_value": Decimal("27.5"), "weight_kg": Decimal("27.5"),
                  "weight_basis": "unknown", "manufacturer": "ذوب آهن",
                  "length_m": Decimal("12"), "spec_source": "dedicated_column"}
        rows, _ = await service(rows=[observation(**stored)]).current(object())
        for column, value in stored.items():
            self.assertEqual(value, rows[0][column], column)

    async def test_an_unresolved_source_weight_still_reaches_the_api(self):
        rows, _ = await service(rows=[observation(
            weight_value=Decimal("32"), weight_kg=None)]).current(object())
        declared = {key: value for key, value in rows[0].items()
                    if key in MaterialPriceResponse.model_fields}
        payload = MaterialPriceResponse.model_validate(declared).model_dump(by_alias=True)
        self.assertEqual(Decimal("32"), payload["weightValue"])
        self.assertIsNone(payload["weightKg"])

    async def test_a_column_the_sheet_said_nothing_about_is_null_not_zero(self):
        rows, _ = await service(rows=[observation()]).current(object())
        for column in SPEC_COLUMNS:
            self.assertIsNone(rows[0][column], column)


class ConversionEligibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_nothing_to_cross_is_null_rather_than_true(self):
        """No display unit chosen. "Not asked" and "no" are different answers."""
        rows, _ = await service(rows=[observation()]).current(object())
        self.assertIsNone(rows[0]["conversion_eligible"])

    async def test_the_unit_it_is_already_in_is_not_a_crossing(self):
        rows, _ = await service(rows=[observation()],
                                settings=[setting("kg")]).current(object())
        self.assertIsNone(rows[0]["conversion_eligible"])

    async def test_a_crossing_the_registry_bridges_is_eligible(self):
        rows, _ = await service(rows=[observation()],
                                settings=[setting("ton")]).current(object())
        self.assertIs(True, rows[0]["conversion_eligible"])

    async def test_an_unknown_weight_basis_is_refused(self):
        """27 kg per WHAT. Nobody wrote it down, so nothing may be computed from it."""
        rows, _ = await service(
            rows=[observation(weight_kg=Decimal("27"),
                              weight_basis="unknown")],
            settings=[setting("branch")]).current(object())
        self.assertIs(False, rows[0]["conversion_eligible"])
        self.assertIsNone(rows[0]["current_price_irr"],
                          "an ineligible crossing must withhold the price, not guess it")

    async def test_a_stated_basis_is_eligible(self):
        rows, _ = await service(
            rows=[observation(weight_kg=Decimal("27"),
                              weight_basis="branch")],
            settings=[setting("branch")]).current(object())
        self.assertIs(True, rows[0]["conversion_eligible"])

    async def test_a_measured_factor_makes_it_eligible_whatever_the_weight_says(self):
        """A person measured this product and gave a reason. That is evidence."""
        rows, _ = await service(
            rows=[observation(weight_kg=Decimal("27"), weight_basis="unknown")],
            settings=[setting("branch")],
            factors=[{"from_unit": "kg", "to_unit": "branch",
                      "factor": Decimal("27"), "origin": "manual"}]).current(object())
        self.assertIs(True, rows[0]["conversion_eligible"])

    def test_unknown_is_not_a_usable_basis(self):
        self.assertNotIn("unknown", WEIGHT_BASES_USABLE_FOR_CONVERSION)


class GramKilogramTests(unittest.IsolatedAsyncioTestCase):
    """The 1000x error, pinned in both directions.

    A price is PER a unit, so it scales with the unit, not against it. A gram costing 1,000
    rial is a kilogram costing 1,000,000 -- not one costing 1. Getting this backwards does
    not look wrong on screen; it looks like a cheap supplier.
    """

    async def test_a_price_per_gram_becomes_a_thousand_times_more_per_kilogram(self):
        rows, _ = await service(
            rows=[observation(source_unit="g", normalized_price_irr=Decimal("1000"))],
            settings=[setting("kg")]).current(object())
        self.assertEqual(Decimal("1000000"), Decimal(rows[0]["current_price_irr"]))
        self.assertEqual("kg", rows[0]["target_unit"])

    async def test_a_price_per_kilogram_becomes_a_thousandth_per_gram(self):
        rows, _ = await service(
            rows=[observation(source_unit="کیلو", normalized_price_irr=Decimal("1000000"))],
            settings=[setting("g")]).current(object())
        self.assertEqual(Decimal("1000"), Decimal(rows[0]["current_price_irr"]))
        self.assertEqual("g", rows[0]["target_unit"])

    async def test_the_round_trip_returns_the_number_it_started_with(self):
        start = Decimal("854500")
        up, _ = await service(
            rows=[observation(source_unit="کیلو", normalized_price_irr=start)],
            settings=[setting("ton")]).current(object())
        back, _ = await service(
            rows=[observation(source_unit="ton",
                              normalized_price_irr=Decimal(up[0]["current_price_irr"]))],
            settings=[setting("kg")]).current(object())
        self.assertEqual(start, Decimal(back[0]["current_price_irr"]))

    async def test_the_factor_that_was_applied_is_reported(self):
        """A converted price with no stated factor is a number nobody can check."""
        rows, _ = await service(
            rows=[observation(source_unit="g", normalized_price_irr=Decimal("1000"))],
            settings=[setting("kg")]).current(object())
        self.assertIsNotNone(rows[0]["conversion_factor"])
        self.assertIsNotNone(rows[0]["conversion_note"])
        self.assertEqual("dimension", rows[0]["factor_origin"])


class UnreadableDateTests(unittest.TestCase):
    """A cell that said something which was not a date.

    Before 0027 such a row was accepted and stored with `validationStatus = 'valid'` and a
    null business date. The constraint 0027 added refuses that row, so the disagreement
    would have surfaced as an aborted import rather than as one rejected row: a single bad
    cell in a sheet of two thousand taking the other 1,999 with it.

    Rejecting keeps the raw text, names the reason, and leaves the row findable. The one
    thing that must never happen is the substitution that would satisfy the constraint --
    `fetched_at` or today standing in for a business date nobody quoted.
    """

    CELLS = {"source": "Mashhad Foolad", "productId": "REBAR-1",
             "محصول": "میلگرد آجدار ۸ A3", "قیمت": "95500",
             # Required since the pricing unit became mandatory; this suite is about dates.
             "واحد - وزن": "کیلو"}

    def row(self, written):
        from app.finance.domain.material_price_rows import decide_row
        return decide_row(worksheet="steel -Rebar", row_number=2,
                          cells=dict(self.CELLS, **{"تاریخ آپدیت ورک فلو": written}))

    def test_a_real_date_is_accepted(self):
        row = self.row("1405-06-22")
        self.assertEqual("accepted", row.status)
        self.assertIsNotNone(row.workflow_date_gregorian)

    def test_a_date_that_is_not_a_date_is_rejected(self):
        for written in ("1405/13/40", "فردا", "1405-07-31", "1405-12-30"):
            with self.subTest(written):
                row = self.row(written)
                self.assertEqual("rejected", row.status)
                self.assertIsNone(row.workflow_date_gregorian)

    def test_the_rejected_row_keeps_what_the_cell_said(self):
        """Evidence. A reader has to be able to see the text that could not be read."""
        row = self.row("1405/13/40")
        self.assertEqual("1405/13/40", row.workflow_date_raw)
        self.assertIn("1405/13/40", " ".join(row.reasons))

    def test_a_blank_date_and_an_unreadable_one_are_told_apart(self):
        """Two different failures. An empty cell and a wrong cell need different fixes."""
        self.assertNotEqual(list(self.row("").reasons),
                            list(self.row("1405/13/40").reasons))

    def test_nothing_substitutes_a_date_for_the_missing_one(self):
        from datetime import date
        for written in ("", "1405/13/40", "فردا"):
            with self.subTest(written):
                row = self.row(written)
                self.assertIsNone(row.workflow_date_gregorian)
                self.assertNotEqual(date.today(), row.workflow_date_gregorian)


class HistoryContractTests(unittest.TestCase):
    def test_history_declares_both_identities_separately(self):
        fields = MaterialPriceHistoryResponse.model_fields
        for field in ("product_name_snapshot", "provider_name_snapshot",
                      "product_external_id", "current_product_name",
                      "current_provider_name", "row_fingerprint", "collection_run_id"):
            self.assertIn(field, fields)

    def test_the_current_name_is_never_the_snapshot_field(self):
        """Two fields, never merged. A reader must be able to SEE a rename."""
        row = MaterialPriceHistoryResponse.model_validate({
            "id": uuid4(), "sourceCurrency": "TOMAN", "observedAt": "2026-09-13T00:00:00Z",
            "observedAtSource": "workflow_date", "fetchedAt": "2026-09-14T00:00:00Z",
            "validationStatus": "valid",
            "productNameSnapshot": "میلگرد آجدار ۸ A3",
            "currentProductName": "میلگرد آجدار ۸ A3 -- کد جدید"})
        self.assertNotEqual(row.product_name_snapshot, row.current_product_name)

    def test_a_row_with_no_snapshot_validates_and_stays_null(self):
        row = MaterialPriceHistoryResponse.model_validate({
            "id": uuid4(), "sourceCurrency": "TOMAN", "observedAt": "2026-09-13T00:00:00Z",
            "observedAtSource": "workflow_date", "fetchedAt": "2026-09-14T00:00:00Z",
            "validationStatus": "rejected", "validationReasons": ["missing_product_id"],
            "currentProductName": "میلگرد آجدار ۸ A3"})
        self.assertIsNone(row.product_name_snapshot)
        self.assertIsNone(row.product_external_id)


if __name__ == "__main__":
    unittest.main()
