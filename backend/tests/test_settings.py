import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.settings import FinanceProjectSettings, StaleSettingsVersion
from app.finance.schemas.settings import FinanceSettingsPatch, FinanceSettingsResponse
from app.finance.security.context import AuthContext
from app.finance.security.guards import FinanceScope
from app.finance.services.settings import (SETTINGS_EDIT_PERMISSION,
                                           FinanceSettingsService, may_edit_settings)


ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SETTING_1 = UUID("10000000-0000-4000-8000-000000000001")
SETTING_2 = UUID("10000000-0000-4000-8000-000000000002")
AUDIT_ID = UUID("90000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def initial_setting() -> FinanceProjectSettings:
    return FinanceProjectSettings(
        id=SETTING_1,
        organization_id=ORG_ID,
        project_id="sample_site_01",
        gross_built_area=Decimal("4250.0000"),
        currency="IRR",
        revision=1,
        effective_from=date(2026, 8, 1),
        reason="ثبت اولیه",
        created_by=ACTOR_ID,
        created_at=NOW,
    )


class FakeSettingsRepository:
    def __init__(self):
        self.versions = [initial_setting()]
        self.audit_events = []

    async def get_current(self, scope):
        matches = [
            row
            for row in self.versions
            if row.organization_id == scope.organization_id
            and row.project_id == scope.project_id
        ]
        return matches[-1] if matches else None

    async def append_revision_with_audit(
        self,
        scope,
        gross_built_area,
        effective_from,
        reason,
        expected_revision,
        actor_user_id,
        settings_id,
        audit_id,
        occurred_at,
    ):
        current = await self.get_current(scope)
        if current is None and expected_revision == 0:
            next_revision = 1
        elif current is not None and current.revision == expected_revision:
            next_revision = current.revision + 1
        else:
            raise StaleSettingsVersion()
        updated = FinanceProjectSettings(
            id=settings_id,
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            gross_built_area=gross_built_area,
            currency="IRR",
            revision=next_revision,
            effective_from=effective_from,
            reason=reason,
            created_by=actor_user_id,
            created_at=occurred_at,
        )
        self.versions.append(updated)
        self.audit_events.append(
            {
                "id": audit_id,
                "action": "finance_settings.revised",
                "before": None if current is None else str(current.gross_built_area),
                "after": str(updated.gross_built_area),
            }
        )
        return updated


class FinanceSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = FakeSettingsRepository()
        ids = iter((SETTING_2, AUDIT_ID))
        self.service = FinanceSettingsService(
            repository=self.repository,
            id_factory=lambda: next(ids),
            clock=lambda: NOW,
        )
        self.scope = FinanceScope(
            organization_id=ORG_ID,
            project_id="sample_site_01",
            actor_user_id=ACTOR_ID,
        )

    def test_patch_accepts_positive_decimal_and_rejects_zero_or_negative(self):
        valid = FinanceSettingsPatch(
            grossBuiltArea="5000.1250",
            effectiveFrom="2026-08-07",
            reason="اصلاح نقشه مصوب",
            expectedRevision=1,
        )
        self.assertEqual(Decimal("5000.1250"), valid.gross_built_area)
        for value in ("0", "-0.0001"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                FinanceSettingsPatch(
                    grossBuiltArea=value,
                    effectiveFrom="2026-08-07",
                    reason="نامعتبر",
                    expectedRevision=1,
                )
        with self.assertRaises(ValidationError):
            FinanceSettingsPatch(
                grossBuiltArea="5000",
                effectiveFrom="2026-08-07",
                reason="   ",
                expectedRevision=1,
            )

    async def test_update_appends_revision_preserves_previous_and_writes_audit(self):
        command = FinanceSettingsPatch(
            grossBuiltArea="5000.1250",
            effectiveFrom="2026-08-07",
            reason="اصلاح نقشه مصوب",
            expectedRevision=1,
        )
        updated = await self.service.update(self.scope, command)
        self.assertEqual(2, updated.revision)
        self.assertEqual(2, len(self.repository.versions))
        self.assertEqual(Decimal("4250.0000"), self.repository.versions[0].gross_built_area)
        self.assertEqual("finance_settings.revised", self.repository.audit_events[0]["action"])

    async def test_initial_registration_creates_revision_one(self):
        self.repository.versions.clear()
        command = FinanceSettingsPatch(
            grossBuiltArea="4250",
            effectiveFrom="2026-08-07",
            reason="ثبت اولیه",
            expectedRevision=0,
        )
        created = await self.service.update(self.scope, command)
        self.assertEqual(1, created.revision)
        self.assertEqual(Decimal("4250"), created.gross_built_area)

    async def test_stale_version_is_rejected_without_partial_revision_or_audit(self):
        command = FinanceSettingsPatch(
            grossBuiltArea="5000",
            effectiveFrom="2026-08-07",
            reason="نسخه قدیمی",
            expectedRevision=9,
        )
        with self.assertRaises(StaleSettingsVersion):
            await self.service.update(self.scope, command)
        self.assertEqual(1, len(self.repository.versions))
        self.assertEqual([], self.repository.audit_events)

    async def test_get_and_summary_use_current_revision(self):
        current = await self.service.get(self.scope)
        summary = await self.service.summary(self.scope)
        self.assertEqual(current, summary)
        response = FinanceSettingsResponse.from_domain(current)
        payload = response.model_dump(mode="json", by_alias=True)
        self.assertEqual("4250.0000", payload["grossBuiltArea"])
        self.assertEqual("IRR", payload["currency"])
        self.assertEqual(1, payload["revision"])

    def test_editing_settings_costs_finance_edit_whatever_the_caller_is_called(self):
        """A role name is not a permission.

        The rule here used to be `finance.view if organization_role == "org_chief" else
        finance.edit`. An org chief therefore edited the gross built area -- the divisor
        under every per-square-metre figure this module publishes -- holding read-only
        permission, and taking `finance.edit` away from them changed nothing at all. Two
        things made that worse than an ordinary over-grant: the bypass was invisible from
        the permission list, and it moved whenever the host renamed a role.
        """
        chief = FinanceScope(
            organization_id=ORG_ID, project_id="sample_site_01", actor_user_id=ACTOR_ID,
            organization_role="org_chief", permission_codes=("finance.view",))
        editor = FinanceScope(
            organization_id=ORG_ID, project_id="sample_site_01", actor_user_id=ACTOR_ID,
            organization_role="guest", permission_codes=("finance.view", "finance.edit"))

        self.assertEqual("finance.edit", SETTINGS_EDIT_PERMISSION)
        # The chief holds the grander title and the weaker permission. Title loses.
        self.assertFalse(may_edit_settings(chief))
        self.assertTrue(may_edit_settings(editor))

    def test_no_role_name_can_stand_in_for_the_edit_permission(self):
        """Whatever the host calls somebody, only the permission opens the gate."""
        for role in ("org_chief", "bambo_admin", "project_manager", "finance_expert",
                     "support", "guest"):
            with self.subTest(role=role):
                viewer = FinanceScope(
                    organization_id=ORG_ID, project_id="sample_site_01",
                    actor_user_id=ACTOR_ID, organization_role=role,
                    permission_codes=("finance.view", "finance_report.view",
                                      "finance_report.export", "finance.manage_invoice"))
                self.assertFalse(may_edit_settings(viewer),
                                 "%s edited settings without finance.edit" % role)


if __name__ == "__main__":
    unittest.main()
