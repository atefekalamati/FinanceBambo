# -*- coding: utf-8 -*-
"""The MPP-authoritative model for Items and Estimates.

WHAT IS BEING PINNED

The schedule says what exists. Finance classifies it, prices it and adds it up, and may
not invent an item beside it. Three families of test:

    identity      one MPP resource is one item; one assignment is one use of it; two
                  resources that share a name stay two; a task is never an item
    meaning       an assignment's "Units" number is interpreted, never assumed -- 7516.4
                  cubic metres is a quantity, 1.0 against a WORK resource is 100% of one
                  machine, and nothing multiplies the second by a price
    arithmetic    assignment amounts roll up to the resource and to the project exactly
                  once, and anything not calculable is null and reported, never zero

THE FIXTURE IS THE REAL FILE'S SHAPE

The rows below are the audited project's task 1219 «کانال کنی», verbatim from
`finance_mpp_rows`: two materials with resolved units and real costs, and two WORK
resources whose unit text -- «ب», «ک» -- resolved to nothing. That last pair is the whole
reason this module exists, so the tests use the real one rather than an invented one.
"""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.assignment_semantics import (ALLOCATION_PERCENTAGE, CALCULATED,
                                                     NOT_CALCULABLE, PHYSICAL_QUANTITY,
                                                     UNKNOWN, assignment_estimate,
                                                     value_kind)
from app.finance.services.items_and_estimates import ItemsAndEstimatesService

ORG = UUID("11111111-1111-4111-8111-111111111111")
VERSION = UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
OTHER_VERSION = UUID("bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")


def row(**changes):
    """One `finance_mpp_rows` row joined as the repository returns it."""
    value = {
        "source_assignment_uid": 9447, "source_resource_uid": 152, "source_task_uid": 1219,
        "task_name": "کانال کنی", "task_wbs": "3.4.1",
        "resource_name": "کانال کنی", "file_resource_type": "MATERIAL",
        "resource_unit": "مترمکعب", "normalized_unit": "m3", "unit_source": "alias",
        "unit_confidence": "alias",
        "source_assignment_units": Decimal("7516.4"),
        "source_assignment_cost_irr": Decimal("15234765668"),
        "source_cost": None, "source_actual_cost": None,
        "resource_id": uuid4(), "resource_title": "کانال کنی", "resource_type": "material",
        "base_unit": "m3", "finance_resource_uid": 152,
        "estimate_line_id": uuid4(), "legacy_status": None,
        "mapping_id": None, "provider_item_id": None, "selected_unit": None,
        "conversion_status": None, "mapping_version": None,
        "mapped_product_name": None, "mapped_product_category": None,
        # The shared resolver's own columns. `price_as_of` is no longer a column of its
        # own: the effective date belongs to whichever rung answered, so it comes back
        # from the resolver beside the amount rather than from the observation alone.
        "current_unit_price_irr": None, "price_source_unit": None,
        "current_price_source": "none", "current_price_unit": None,
        "current_price_scope": None, "current_price_effective_from": None,
        "price_version_id": None,
    }
    value.update(changes)
    return value


#: Task 1219 as the file states it. The two WORK rows are the ones that must not be priced.
KANAL_KESHI = [
    row(),
    row(source_assignment_uid=9459, source_resource_uid=134, resource_name="بسترکوبی",
        resource_title="بسترکوبی", resource_unit="مترمربع", normalized_unit="m2",
        base_unit="m2", finance_resource_uid=134,
        source_assignment_units=Decimal("3956.0"),
        source_assignment_cost_irr=Decimal("197800000")),
    row(source_assignment_uid=9816, source_resource_uid=158, resource_name="بیل مکانیکی",
        resource_title="بیل مکانیکی", file_resource_type="WORK", resource_type="equipment",
        resource_unit="ب", normalized_unit=None, unit_source="not_a_unit",
        unit_confidence="low", base_unit=None, finance_resource_uid=158,
        source_assignment_units=Decimal("1.0"),
        source_assignment_cost_irr=Decimal("0")),
    row(source_assignment_uid=9817, source_resource_uid=171, resource_name="کامیون",
        resource_title="کامیون", file_resource_type="WORK", resource_type="equipment",
        resource_unit="ک", normalized_unit=None, unit_source="not_a_unit",
        unit_confidence="low", base_unit=None, finance_resource_uid=171,
        source_assignment_units=Decimal("1.0"),
        source_assignment_cost_irr=Decimal("0")),
]


class Repo:
    """Rows this test wrote, so every assertion is about the code."""

    #: Distinguishes "caller said nothing" from "caller said there is no version".
    DEFAULT = object()

    def __init__(self, rows=(), legacy=(), version=DEFAULT):
        self.rows = list(rows)
        self._legacy = list(legacy)
        self._version = version if version is not Repo.DEFAULT else {
            "id": VERSION, "source_file_name_safe": "test_progress.mpp",
            "source_sha256": "a" * 64, "imported_at": None, "reporting_date": None,
            "row_count": 789}
        self.asked_for = None

    async def live_version(self, _scope):
        return self._version

    async def assignments(self, _scope, source_version_id):
        self.asked_for = source_version_id
        return [r for r in self.rows
                if r.get("source_version_id", VERSION) == source_version_id]

    async def legacy_lines(self, _scope):
        return self._legacy


def service(**kwargs):
    return ItemsAndEstimatesService(Repo(**kwargs))


def priced(**changes):
    """A material assignment with everything needed to price it.

    The defaults are merged rather than passed as keywords so a caller can override any
    of them -- `priced(conversion_status="incompatible")` has to mean "priced except for
    that", not a duplicate-keyword error.
    """
    values = {"mapping_id": uuid4(), "provider_item_id": uuid4(), "selected_unit": "m3",
              "conversion_status": "automatic", "mapped_product_name": "بتن آماده C25",
              "current_unit_price_irr": Decimal("1000")}
    values.update(changes)
    return row(**values)


class IdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_mpp_resource_is_one_item(self):
        body = await service(rows=KANAL_KESHI).listing(object())
        uids = [r["source_resource_uid"] for r in body["resources"]]
        self.assertEqual([134, 152, 158, 171], sorted(uids))
        self.assertEqual(4, len(body["resources"]))

    async def test_one_resource_in_many_activities_keeps_many_assignments(self):
        """Five uses of one item are five assignments and ONE item."""
        rows = [row(source_assignment_uid=9000 + n, source_task_uid=1200 + n,
                    task_name="فعالیت %d" % n) for n in range(5)]
        body = await service(rows=rows).listing(object())
        self.assertEqual(1, len(body["resources"]))
        self.assertEqual(5, body["resources"][0]["assignment_count"])
        self.assertEqual(5, len({a["source_assignment_uid"]
                                 for a in body["resources"][0]["assignments"]}))

    async def test_two_resources_sharing_a_name_stay_two(self):
        rows = [row(source_resource_uid=10, source_assignment_uid=1, resource_name="سیمان"),
                row(source_resource_uid=11, source_assignment_uid=2, resource_name="سیمان")]
        body = await service(rows=rows).listing(object())
        self.assertEqual(2, len(body["resources"]))
        self.assertEqual({10, 11}, {r["source_resource_uid"] for r in body["resources"]})

    async def test_an_assignment_with_no_resource_uid_is_not_merged_with_others(self):
        """Unidentified is not an identity. Two nameless rows are not one item."""
        rows = [row(source_resource_uid=None, source_assignment_uid=1),
                row(source_resource_uid=None, source_assignment_uid=2)]
        body = await service(rows=rows).listing(object())
        self.assertEqual(2, len(body["resources"]))

    async def test_a_task_never_becomes_an_item(self):
        """Four assignments across one task -- the task is a field, never a row."""
        body = await service(rows=KANAL_KESHI).listing(object())
        for resource in body["resources"]:
            self.assertIsNotNone(resource["source_resource_uid"])
            for assignment in resource["assignments"]:
                self.assertEqual(1219, assignment["source_task_uid"])
                self.assertEqual("کانال کنی", assignment["task_name"])

    async def test_the_listing_is_scoped_to_one_source_version(self):
        rows = [row(source_version_id=VERSION, source_assignment_uid=1),
                row(source_version_id=OTHER_VERSION, source_assignment_uid=2)]
        repo = Repo(rows=rows)
        body = await ItemsAndEstimatesService(repo).listing(object())
        self.assertEqual(VERSION, repo.asked_for)
        self.assertEqual(1, sum(r["assignment_count"] for r in body["resources"]))
        self.assertEqual(VERSION, body["source_version"]["id"])

    async def test_no_schedule_imported_reports_an_empty_project_plainly(self):
        body = await ItemsAndEstimatesService(Repo(version=None)).listing(object())
        self.assertIsNone(body["source_version"])
        self.assertEqual([], body["resources"])
        self.assertIsNone(body["project_current_estimate_irr"])


class MeaningTests(unittest.IsolatedAsyncioTestCase):
    """What the Units number is. The tests the whole model rests on."""

    def test_a_material_with_a_resolved_unit_is_a_quantity(self):
        self.assertEqual(PHYSICAL_QUANTITY, value_kind("MATERIAL", "m3", "alias"))

    def test_a_work_resource_is_an_allocation(self):
        self.assertEqual(ALLOCATION_PERCENTAGE, value_kind("WORK", None, "not_a_unit"))

    def test_a_material_whose_unit_did_not_resolve_is_unknown_not_a_quantity(self):
        """«ب» is not a unit. 12 rows of the audited file are exactly this."""
        self.assertEqual(UNKNOWN, value_kind("MATERIAL", None, "not_a_unit"))

    async def test_a_work_hundred_percent_is_not_quantity_one_hundred(self):
        body = await service(rows=KANAL_KESHI).listing(object())
        digger = next(r for r in body["resources"] if r["source_resource_uid"] == 158)
        assignment = digger["assignments"][0]
        self.assertEqual(ALLOCATION_PERCENTAGE, assignment["assignment_value_kind"])
        self.assertEqual(Decimal("100"), assignment["assignment_allocation_percent"])
        self.assertIsNone(assignment["assignment_quantity"],
                          "an allocation has no quantity to state")

    async def test_an_allocation_is_never_multiplied_by_a_material_price(self):
        rows = [priced(source_resource_uid=158, source_assignment_uid=9816,
                       resource_name="بیل مکانیکی", file_resource_type="WORK",
                       normalized_unit=None, unit_source="not_a_unit",
                       source_assignment_units=Decimal("1.0"))]
        body = await service(rows=rows).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertIsNone(assignment["current_estimate_irr"])
        self.assertEqual(NOT_CALCULABLE, assignment["calculation_status"])
        self.assertIn("allocation_percentage_not_quantity", assignment["issue_codes"])
        self.assertIsNone(body["project_current_estimate_irr"])

    async def test_the_four_real_assignments_of_kanal_keshi(self):
        """The Section 17 verification, against the file's own numbers."""
        body = await service(rows=KANAL_KESHI).listing(object())
        seen = {r["source_resource_uid"]: r for r in body["resources"]}
        self.assertEqual(Decimal("7516.4"),
                         seen[152]["assignments"][0]["assignment_quantity"])
        self.assertEqual(Decimal("3956.0"),
                         seen[134]["assignments"][0]["assignment_quantity"])
        for uid in (158, 171):
            assignment = seen[uid]["assignments"][0]
            self.assertIsNone(assignment["assignment_quantity"])
            self.assertEqual(Decimal("100"), assignment["assignment_allocation_percent"])
        # And every one of them still belongs to the task the file put it in.
        self.assertEqual({1219}, {a["source_task_uid"] for r in body["resources"]
                                  for a in r["assignments"]})

    def test_unknown_semantics_are_not_guessed(self):
        estimate, status, issues = assignment_estimate(UNKNOWN, Decimal("5"),
                                                       Decimal("1000"))
        self.assertIsNone(estimate)
        self.assertEqual(NOT_CALCULABLE, status)
        self.assertEqual(("unknown_assignment_semantics",), issues)


class ArithmeticTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_material_quantity_is_priced(self):
        body = await service(rows=[priced()]).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertEqual(Decimal("7516400"), assignment["current_estimate_irr"])
        self.assertEqual(CALCULATED, assignment["calculation_status"])
        self.assertEqual([], assignment["issue_codes"])

    async def test_assignments_roll_up_to_one_resource_total(self):
        rows = [priced(source_assignment_uid=1, source_assignment_units=Decimal("10")),
                priced(source_assignment_uid=2, source_assignment_units=Decimal("20")),
                priced(source_assignment_uid=3, source_assignment_units=Decimal("30"))]
        body = await service(rows=rows).listing(object())
        resource = body["resources"][0]
        self.assertEqual(3, resource["assignment_count"])
        self.assertEqual(Decimal("60000"), resource["current_estimate_irr"])
        self.assertEqual(sum(a["current_estimate_irr"] for a in resource["assignments"]),
                         resource["current_estimate_irr"])

    async def test_the_project_counts_each_assignment_exactly_once(self):
        """And does NOT add the resource aggregates on top."""
        rows = [priced(source_resource_uid=1, source_assignment_uid=1,
                       source_assignment_units=Decimal("10")),
                priced(source_resource_uid=1, source_assignment_uid=2,
                       source_assignment_units=Decimal("20")),
                priced(source_resource_uid=2, source_assignment_uid=3,
                       source_assignment_units=Decimal("30"))]
        body = await service(rows=rows).listing(object())
        self.assertEqual(Decimal("60000"), body["project_current_estimate_irr"])
        self.assertEqual(
            Decimal("60000"),
            sum(a["current_estimate_irr"] for r in body["resources"]
                for a in r["assignments"]))
        # The aggregates exist and sum to the same thing -- which is exactly why adding
        # them to the project total would double it.
        self.assertEqual(Decimal("60000"),
                         sum(r["current_estimate_irr"] for r in body["resources"]))
        self.assertEqual(3, body["counted_assignments"])

    async def test_grouping_does_not_change_the_total(self):
        one = [priced(source_resource_uid=1, source_assignment_uid=n,
                      source_assignment_units=Decimal("10")) for n in range(1, 4)]
        many = [priced(source_resource_uid=n, source_assignment_uid=n,
                       source_assignment_units=Decimal("10")) for n in range(1, 4)]
        first = await service(rows=one).listing(object())
        second = await service(rows=many).listing(object())
        self.assertEqual(1, len(first["resources"]))
        self.assertEqual(3, len(second["resources"]))
        self.assertEqual(first["project_current_estimate_irr"],
                         second["project_current_estimate_irr"])

    async def test_a_missing_price_is_null_and_is_reported(self):
        body = await service(rows=[row()]).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertIsNone(assignment["current_estimate_irr"])
        self.assertIn("missing_price", assignment["issue_codes"])
        self.assertTrue(assignment["excluded_from_total"])
        self.assertEqual(1, body["excluded_assignments"])
        self.assertEqual({"missing_price": 1}, body["issue_counts"])

    async def test_an_unresolved_conversion_is_null_not_the_unconverted_price(self):
        body = await service(rows=[priced(conversion_status="incompatible")]).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertIsNone(assignment["converted_unit_price_irr"])
        self.assertIsNone(assignment["current_estimate_irr"])
        self.assertIn("missing_conversion", assignment["issue_codes"])
        self.assertEqual(Decimal("1000"), assignment["current_unit_price_irr"],
                         "the price is still reported -- it is the crossing that failed")

    async def test_a_missing_quantity_is_null_not_zero(self):
        body = await service(rows=[priced(source_assignment_units=None)]).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertIsNone(assignment["current_estimate_irr"])
        self.assertIn("missing_quantity", assignment["issue_codes"])

    async def test_zero_quantity_is_zero_and_is_not_missing(self):
        body = await service(rows=[priced(source_assignment_units=Decimal("0"))]).listing(object())
        assignment = body["resources"][0]["assignments"][0]
        self.assertEqual(Decimal("0"), assignment["current_estimate_irr"])
        self.assertEqual(CALCULATED, assignment["calculation_status"])
        self.assertEqual([], assignment["issue_codes"])
        self.assertFalse(assignment["excluded_from_total"])

    async def test_excluded_rows_are_counted_never_silently_dropped(self):
        rows = [priced(source_assignment_uid=1),
                row(source_assignment_uid=2),
                row(source_assignment_uid=3, file_resource_type="WORK",
                    normalized_unit=None, unit_source="not_a_unit")]
        body = await service(rows=rows).listing(object())
        self.assertEqual(1, body["counted_assignments"])
        self.assertEqual(2, body["excluded_assignments"])
        self.assertEqual(3, sum(r["assignment_count"] for r in body["resources"]))

    async def test_a_total_quantity_is_only_offered_when_the_units_agree(self):
        same = [priced(source_assignment_uid=1, source_assignment_units=Decimal("10")),
                priced(source_assignment_uid=2, source_assignment_units=Decimal("20"))]
        mixed = [priced(source_assignment_uid=1, source_assignment_units=Decimal("10")),
                 priced(source_assignment_uid=2, source_assignment_units=Decimal("20"),
                        normalized_unit="m2")]
        body = await service(rows=same).listing(object())
        self.assertEqual(Decimal("30"), body["resources"][0]["total_assignment_quantity"])
        body = await service(rows=mixed).listing(object())
        self.assertIsNone(body["resources"][0]["total_assignment_quantity"],
                          "cubic metres plus square metres is not a quantity")


class MappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_mpp_name_survives_a_price_mapping(self):
        body = await service(rows=[priced(resource_name="کانال گالوانیزه",
                                          mapped_product_name="ورق گالوانیزه ضخامت ۰.۵")]
                             ).listing(object())
        resource = body["resources"][0]
        self.assertEqual("کانال گالوانیزه", resource["resource_name"])
        self.assertEqual("ورق گالوانیزه ضخامت ۰.۵", resource["mapped_product_name"])
        self.assertNotEqual(resource["resource_name"], resource["mapped_product_name"])
        self.assertEqual("approved", resource["mapping_status"])

    async def test_an_unmapped_resource_still_appears(self):
        """A listing that dropped them would answer "45 items" for a schedule of 68."""
        body = await service(rows=[row()]).listing(object())
        self.assertEqual(1, len(body["resources"]))
        self.assertEqual("not_mapped", body["resources"][0]["mapping_status"])
        self.assertIsNone(body["resources"][0]["mapped_product_name"])

    async def test_a_mapping_never_creates_a_resource(self):
        mapped = await service(rows=[priced()]).listing(object())
        bare = await service(rows=[row()]).listing(object())
        self.assertEqual(len(bare["resources"]), len(mapped["resources"]))
        self.assertEqual(bare["resources"][0]["source_resource_uid"],
                         mapped["resources"][0]["source_resource_uid"])


class LegacyTests(unittest.IsolatedAsyncioTestCase):
    LEGACY = [{"id": uuid4(), "legacy_status": "legacy_unlinked", "source": "manual_entry",
               "created_at": None, "original_quantity": Decimal("10"),
               "original_unit_price_irr": Decimal("1000"),
               "resource_title": "برآورد مصالح مورد نياز", "resource_type": "material",
               "invoice_linked": True}]

    async def test_a_source_less_row_never_enters_a_total(self):
        body = await service(rows=[priced()], legacy=self.LEGACY).listing(object())
        self.assertEqual(Decimal("7516400"), body["project_current_estimate_irr"])
        self.assertEqual(1, len(body["legacy_lines"]))

    async def test_it_is_reported_rather_than_hidden(self):
        body = await service(rows=[], legacy=self.LEGACY).listing(object())
        line = body["legacy_lines"][0]
        self.assertEqual("legacy_unlinked", line["legacy_status"])
        self.assertTrue(line["invoice_linked"],
                        "an invoice is evidence a person did something; it is preserved")
        self.assertEqual("برآورد مصالح مورد نياز", line["resource_title"])

    async def test_it_is_never_grafted_into_the_resource_tree(self):
        body = await service(rows=[], legacy=self.LEGACY).listing(object())
        self.assertEqual([], body["resources"],
                         "a row with no assignment has no resource to be a child of")


class ManualCreationRefusedTests(unittest.IsolatedAsyncioTestCase):
    """The creation paths that could produce an item no schedule accounts for.

    Both refuse with a coded 409 rather than a 500 or a silent success, and the refusal is
    at the SERVICE, so it holds for every caller and not only for the HTTP route.
    """

    def setUp(self):
        from test_resources_estimates import ActivityProvider, Repo as ResourceRepo
        from app.finance.services.resources import FinanceResourcesService
        from app.finance.security.guards import FinanceScope
        self.repo = ResourceRepo()
        self.service = FinanceResourcesService(self.repo, uuid4, ActivityProvider(),
                                               lambda: None)
        self.scope = FinanceScope(ORG, "sample_site_01",
                                  UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"))

    def seed(self, uid):
        """A resource as the importer would have written it -- or without a uid."""
        from app.finance.domain.resources import FinanceResource
        value = FinanceResource(uuid4(), ORG, "sample_site_01", "material", "M1", "سیمان",
                                "kg", "mass", None,
                                UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"), None,
                                source_resource_uid=uid)
        self.repo.resources.append(value)
        return value

    async def test_creating_a_resource_is_refused(self):
        from app.finance.domain.resources import MppResourceRequired
        from app.finance.schemas.resources import ResourceCreate
        with self.assertRaises(MppResourceRequired) as caught:
            await self.service.create_resource(
                self.scope, ResourceCreate(type="material", code="X", title="قلم دستی",
                                           baseUnit="kg"))
        self.assertEqual("MPP_RESOURCE_REQUIRED", caught.exception.code)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual([], self.repo.resources, "nothing was written")

    async def test_an_estimate_line_on_a_source_less_resource_is_refused(self):
        from app.finance.domain.resources import MppResourceRequired
        from app.finance.schemas.resources import EstimateLineCreate
        resource = self.seed(uid=None)
        with self.assertRaises(MppResourceRequired) as caught:
            await self.service.create_estimate_line(
                self.scope,
                EstimateLineCreate(resourceId=resource.id, activityExternalId="A1",
                                   originalQuantity="1", source="manual_entry"))
        self.assertEqual("MPP_RESOURCE_REQUIRED", caught.exception.code)
        self.assertEqual([], self.repo.lines, "nothing was written")

    async def test_an_estimate_line_on_an_mpp_resource_is_allowed(self):
        """The refusal is about provenance, not about the endpoint existing."""
        from app.finance.schemas.resources import EstimateLineCreate
        resource = self.seed(uid=94)
        line = await self.service.create_estimate_line(
            self.scope,
            EstimateLineCreate(resourceId=resource.id, activityExternalId="A1",
                               originalQuantity="1", source="manual_entry"))
        self.assertEqual(1, len(self.repo.lines))
        self.assertEqual(resource.id, line.resource_id)

    async def test_classifying_an_existing_resource_is_still_allowed(self):
        """One of the few edits the approved model permits, and it must keep working."""
        from app.finance.schemas.resources import ResourcePatch
        resource = self.seed(uid=94)
        updated = await self.service.update_resource(self.scope, resource.id,
                                                     ResourcePatch(type="equipment"))
        self.assertEqual("equipment", updated.type)
        self.assertEqual(94, updated.source_resource_uid, "identity is never changed")
        self.assertEqual(1, len(self.repo.resources), "no new resource was made")


if __name__ == "__main__":
    unittest.main()


class AManualResourcePriceNeedsNoMappingTests(unittest.TestCase):
    """A price somebody typed is already in the resource's own unit.

    `conversionStatus` describes a MAPPING -- whether a listing's unit could be crossed
    into the line's. A manually priced machine has no mapping, so it answered None, fell
    through the gate meant for listings, and was reported as a missing conversion. The
    price resolved, appeared on the row, and produced no estimate: «قیمت هست، برآورد نیست»
    with nothing on screen saying why.
    """

    def _row(self, **over):
        base = {"current_unit_price_irr": Decimal("32000000"),
                "current_price_source": "manual_resource",
                "current_price_unit": "hour",
                # No mapping exists, and none is needed.
                "conversion_status": None,
                "normalized_unit": "hour", "resource_unit": "hour",
                "source_assignment_units": Decimal("100")}
        base.update(over)
        return row(**base)

    def test_a_manual_price_is_not_reported_as_a_missing_conversion(self):
        assignment = ItemsAndEstimatesService._assignment(self._row())
        self.assertNotIn("missing_conversion", assignment["issue_codes"])
        self.assertEqual("manual_resource", assignment["price_source"])
        self.assertEqual("hour", assignment["price_unit"])

    def test_a_sheet_price_still_needs_its_mapping_to_have_crossed_the_units(self):
        """The gate stays shut for the case it was built for.

        Widening it for manual prices must not let an unconverted listing price through:
        a price per «کیلو» multiplied by a quantity in metres is a number, and a wrong one.
        """
        assignment = ItemsAndEstimatesService._assignment(
            self._row(current_price_source="sheet", conversion_status="unknown"))
        self.assertIn("missing_conversion", assignment["issue_codes"])
        self.assertIsNone(assignment["current_estimate_irr"], "null, never a guess")

    def test_a_sheet_price_whose_mapping_did_cross_them_is_used(self):
        assignment = ItemsAndEstimatesService._assignment(
            self._row(current_price_source="sheet", conversion_status="factor"))
        self.assertNotIn("missing_conversion", assignment["issue_codes"])

    def test_no_price_is_still_no_price(self):
        assignment = ItemsAndEstimatesService._assignment(
            self._row(current_unit_price_irr=None, current_price_source="none",
                      current_price_unit=None))
        self.assertIsNone(assignment["current_estimate_irr"])
        self.assertEqual("none", assignment["price_source"])
