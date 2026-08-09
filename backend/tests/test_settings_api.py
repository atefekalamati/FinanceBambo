import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.domain.settings import FinanceProjectSettings, StaleSettingsVersion
from app.finance.security.context import AuthContext


ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT_ID = "sample_site_01"


class AuthProvider:
    def __init__(self, permission_codes=("finance.view", "finance.edit")):
        self.permission_codes = permission_codes

    async def current(self, _request):
        return AuthContext(
            userId=ACTOR_ID,
            organizationId=ORG_ID,
            projectId=PROJECT_ID,
            organizationRole="finance_viewer",
            projectRole="editor",
            permissionCodes=self.permission_codes,
            locale="fa-IR",
            timezone="Asia/Tehran",
        )


class ScopeAuthorizer:
    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG_ID):
            raise HTTPException(403, "organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if organization_id != str(ORG_ID) or project_id != PROJECT_ID:
            raise HTTPException(403, "project denied")


class PermissionAuthorizer:
    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission denied")


class Repository:
    def __init__(self):
        self.current = FinanceProjectSettings(
            id=uuid4(),
            organization_id=ORG_ID,
            project_id=PROJECT_ID,
            gross_built_area=Decimal("4250.0000"),
            currency="IRR",
            revision=1,
            effective_from=date(2026, 8, 1),
            reason="ثبت اولیه",
            created_by=ACTOR_ID,
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

    async def get_current(self, scope):
        if scope.organization_id == ORG_ID and scope.project_id == PROJECT_ID:
            return self.current
        return None

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
        if expected_revision != self.current.revision:
            raise StaleSettingsVersion()
        self.current = FinanceProjectSettings(
            id=settings_id,
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            gross_built_area=gross_built_area,
            currency="IRR",
            revision=expected_revision + 1,
            effective_from=effective_from,
            reason=reason,
            created_by=actor_user_id,
            created_at=occurred_at,
        )
        return self.current


def client(permission_codes=("finance.view", "finance.edit")):
    from app.finance.services.settings import FinanceSettingsService

    application = create_app()
    application.state.auth_context_provider = AuthProvider(permission_codes)
    application.state.scope_authorizer = ScopeAuthorizer()
    application.state.permission_authorizer = PermissionAuthorizer()
    application.state.finance_settings_service = FinanceSettingsService(Repository())
    return TestClient(application)


class FinanceSettingsApiTests(unittest.TestCase):
    def test_get_settings_and_base_summary(self):
        with client() as api:
            settings = api.get(f"/api/projects/{PROJECT_ID}/finance/settings")
            summary = api.get(f"/api/projects/{PROJECT_ID}/finance/summary")
        self.assertEqual(200, settings.status_code)
        self.assertEqual("4250.0000", settings.json()["grossBuiltArea"])
        self.assertEqual(200, summary.status_code)
        self.assertEqual("IRR", summary.json()["currency"])

    def test_patch_settings_and_reject_body_scope_override(self):
        payload = {
            "grossBuiltArea": "5000.1250",
            "effectiveFrom": "2026-08-07",
            "reason": "اصلاح نقشه",
            "expectedRevision": 1,
        }
        with client() as api:
            response = api.patch(
                f"/api/projects/{PROJECT_ID}/finance/settings", json=payload
            )
            overridden = api.patch(
                f"/api/projects/{PROJECT_ID}/finance/settings",
                json={**payload, "organizationId": str(uuid4())},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual("5000.1250", response.json()["grossBuiltArea"])
        self.assertEqual(422, overridden.status_code)

    def test_cross_project_and_missing_permissions_are_denied(self):
        with client() as api:
            cross_project = api.get("/api/projects/other_site/finance/settings")
        with client(()) as api:
            no_permission = api.get(f"/api/projects/{PROJECT_ID}/finance/settings")
        self.assertEqual(403, cross_project.status_code)
        self.assertEqual(403, no_permission.status_code)


if __name__ == "__main__":
    unittest.main()
