# -*- coding: utf-8 -*-
"""Two policies on a negative general cost, and why they are deliberately different.

THE QUESTION

A general cost line can hold a negative amount. Whether it MAY depends entirely on where
the amount came from, and the two answers are not a contradiction:

  * A person typing one into the estimate form is refused. Nothing in the product asks a
    user for a negative general cost, and a minus sign typed by accident into a money
    field is a correction nobody made and nobody would see.

  * A fixed cost read out of an MPP file is accepted exactly as stated. This project's
    schedule corrects one activity downwards by -2,972,160,000 against its neighbour's
    +5,290,960,000.5 -- one correction spread across two related activities. Clamping it
    to zero would publish an initial estimate the schedule does not have, and would do it
    in the direction that looks more plausible, so nobody would query it.

The difference is evidence. The file is a record of what was planned; the form is an
opportunity to mistype. These tests exist so that neither policy can be changed by
accident while looking like a tidy-up of the other.

WHAT IS NOT CHANGED HERE

The manual rule is the one that was already in the product, kept as it was. This file
documents it beside the MPP rule rather than altering either.
"""

import asyncio
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.reports import calculate_live_report
from app.finance.domain.resources import FinanceResource, UnitMismatch
from app.finance.schemas.resources import EstimateLineCreate
from app.finance.security.guards import FinanceScope
from app.finance.services.resources import FinanceResourcesService

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
RESOURCE = UUID("22222222-2222-4222-8222-222222222222")
GENERAL_LINE = UUID("10000000-0000-4000-8000-000000000003")
GENERAL = UUID("20000000-0000-4000-8000-000000000003")
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Repo:
    def __init__(self, resource):
        self.resource = resource
        self.lines = []

    async def get_resource(self, _scope, resource_id):
        return self.resource if resource_id == self.resource.id else None

    async def create_estimate_line(self, _scope, value, _audit_id):
        self.lines.append(value)
        return value


class Activities:
    async def get_activity(self, _organization_id, _project_id, external_id):
        return {"id": external_id, "title": "اجرای فونداسیون", "wbsCode": "1.2",
                "status": "active"}

    async def list_activities(self, *_a, **_k):
        return [], 0


def general_cost_line(amount):
    return {"id": GENERAL_LINE, "resource_id": GENERAL, "resource_type": "general_cost",
            "resource_code": "gen", "resource_title": "هزینه ثابت فعالیت",
            "original_quantity": None, "revised_quantity": amount,
            "original_unit_price_irr": amount, "current_unit_price_irr": amount,
            "assignment_external_id": None, "activity_external_id": None,
            "progress_snapshot_id": SNAPSHOT}


class ManualGeneralCostIsUnchangedTests(unittest.TestCase):
    """What a person may type. Existing product policy, restated here, not altered."""

    def setUp(self):
        self.resource = FinanceResource(
            RESOURCE, ORG, "sample_site_01", "general_cost", "GC", "هزینه مجوز",
            None, None, None, ACTOR, NOW, source_resource_uid=4242)
        self.repo = Repo(self.resource)
        self.service = FinanceResourcesService(
            self.repo, lambda: UUID(int=7), Activities(), lambda: NOW)
        self.scope = FinanceScope(ORG, "sample_site_01", ACTOR)

    def create(self, amount):
        return run(self.service.create_estimate_line(
            self.scope,
            EstimateLineCreate(resourceId=RESOURCE, activityExternalId="A1",
                               originalQuantity=amount, source="manual_entry")))

    def test_a_positive_amount_is_accepted_as_it_always_was(self):
        line = self.create("2500000")
        self.assertEqual(Decimal("2500000"), line.original_unit_price_irr)
        self.assertIsNone(line.original_quantity, "a general cost measures nothing")

    def test_a_negative_amount_typed_by_a_person_is_still_refused(self):
        with self.assertRaises(UnitMismatch):
            self.create("-2500000")
        self.assertEqual([], self.repo.lines, "nothing reached the repository")

    def test_the_refusal_is_the_services_and_not_only_the_schemas(self):
        # `originalUnitPriceIrr` carries `ge=0`, so the schema stops that spelling before
        # the service sees it. `originalQuantity` does not, and the same amount arrives
        # through it -- which is why the rule has to live in the service as well.
        from app.finance.schemas.resources import EstimateLineCreate as Create
        with self.assertRaises(ValueError):
            Create(resourceId=RESOURCE, activityExternalId="A1",
                   originalUnitPriceIrr="-1", source="manual_entry")

    def test_a_fractional_amount_is_refused_for_the_same_reason_a_negative_one_is(self):
        # Kept in the same case to say that the integer rule and the sign rule are one
        # policy about what a person may state, not two unrelated guards.
        with self.assertRaises(UnitMismatch):
            self.create("2500000.5")


class MppFixedCostKeepsItsSignTests(unittest.TestCase):
    """What a file may state. The mapper writes the evidence, not a tidied version of it.

    The amounts themselves are asserted in `test_finance_mpp_mapping.py`, where the fake
    schedule lives -- `test_a_negative_fixed_cost_is_carried_as_the_file_states_it` and
    `test_the_corrected_activity_keeps_its_negative`. What belongs HERE is the structural
    reason those two can keep passing while the manual rule above also keeps passing.
    """

    def test_the_mapper_does_not_go_through_the_service_that_refuses_negatives(self):
        # The two policies can only coexist because they are two paths. If the mapper ever
        # started creating its lines through `FinanceResourcesService.create_estimate_line`,
        # every negative fixed cost in the file would begin to be refused -- silently, as a
        # mapping that produced fewer lines than the schedule has.
        import inspect

        from coreint import finance_mpp_mapping
        source = inspect.getsource(finance_mpp_mapping)
        self.assertNotIn("FinanceResourcesService", source)
        self.assertNotIn("create_estimate_line", source)


class NegativeFixedCostInTheReportTests(unittest.TestCase):
    """What the two headline figures do with a negative general cost, stated on purpose."""

    def test_the_initial_estimate_follows_the_file_in_both_directions(self):
        report = calculate_live_report(
            [general_cost_line("28296880000"), general_cost_line("-29721600000")],
            [], [], [], None)
        self.assertEqual(Decimal("-1424720000"), report.metrics["initialEstimateIrr"],
                         "a correction downwards reduces the estimate, as the file says")

    def test_a_single_negative_line_is_not_clamped_out_of_the_estimate(self):
        report = calculate_live_report([general_cost_line("-29721600000")], [], [], [], None)
        self.assertEqual(Decimal("-29721600000"), report.metrics["initialEstimateIrr"])
        # The per-type breakdown carries the revised figure, and it agrees: a negative
        # line is not quietly dropped from one total while surviving in the other.
        general = next(item for item in report.breakdown
                       if item["resourceType"] == "general_cost")
        self.assertEqual(Decimal("-29721600000"), general["initialEstimateIrr"])
        self.assertEqual(Decimal("-29721600000"), general["revisedEstimateIrr"])

    def test_the_residue_line_is_small_and_still_counted(self):
        report = calculate_live_report(
            [general_cost_line("28296880000"), general_cost_line("-29721600000"),
             general_cost_line("52909600005"), general_cost_line("59")],
            [], [], [], None)
        self.assertEqual(Decimal("51484880064"), report.metrics["initialEstimateIrr"],
                         "the whole fixed-cost reading of the schedule, aggregate included")

    def test_money_required_to_continue_never_goes_below_zero(self):
        """DOCUMENTED, NOT INCIDENTAL.

        `max(revised - actual, 0)` per line is the existing rule and stays. A negative
        general cost therefore lowers the initial estimate but contributes nothing to what
        is still needed -- because there is no such thing as needing a negative amount of
        money to finish, and a forecast that netted one line's correction against another
        line's outstanding work would understate what the project still has to spend.

        Changing this needs a product decision, not a refactor, which is why the number
        is asserted here rather than left to be discovered.
        """
        report = calculate_live_report([general_cost_line("-29721600000")], [], [], [], None)
        self.assertEqual(Decimal("0"), report.metrics["moneyRequiredToContinueIrr"])
        self.assertEqual(Decimal("0"), report.metrics["forecastFinalCostIrr"],
                         "no actual spend and nothing required, so nothing is forecast")

    def test_a_negative_line_does_not_cancel_another_lines_outstanding_work(self):
        report = calculate_live_report(
            [general_cost_line("-29721600000"), general_cost_line("52909600005")],
            [], [], [], None)
        self.assertEqual(Decimal("23188000005"), report.metrics["initialEstimateIrr"])
        self.assertEqual(Decimal("52909600005"),
                         report.metrics["moneyRequiredToContinueIrr"],
                         "the positive line is still owed in full")


if __name__ == "__main__":
    unittest.main()
