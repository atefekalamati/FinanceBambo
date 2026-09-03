import inspect
import sys
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import Request

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.security.context import AuthContext
from app.finance.security.guards import (
    FinanceNotFound,
    FinanceScope,
    authorize_finance_request,
    require_scoped_record,
)


ORG_A = "11111111-1111-4111-8111-111111111111"
ORG_B = "22222222-2222-4222-8222-222222222222"
PROJECT_A = "sample_site_01"
PROJECT_B = "other_site_01"


def context(locale="fa-IR") -> AuthContext:
    return AuthContext(
        userId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
        organizationId=ORG_A,
        projectId=PROJECT_A,
        organizationRole="org_chief",
        projectRole="project_admin",
        permissionCodes=["finance.view"],
        locale=locale,
        timezone="Asia/Tehran",
    )


class FakeAuth:
    def __init__(self, calls, locale="fa-IR"):
        self.calls = calls
        self.locale = locale

    async def current(self, _request):
        self.calls.append("authentication")
        return context(self.locale)


class FakeScopeAuthorizer:
    def __init__(self, calls, fail_at=None):
        self.calls = calls
        self.fail_at = fail_at

    async def require_organization(self, _context, organization_id):
        self.calls.append("organization")
        if self.fail_at == "organization":
            raise PermissionError("organization denied")
        self.organization_id = organization_id

    async def require_project(self, _context, organization_id, project_id):
        self.calls.append("project")
        if self.fail_at == "project":
            raise PermissionError("project denied")
        self.project_scope = organization_id, project_id


class FakePermissionAuthorizer:
    def __init__(self, calls, denied=False):
        self.calls = calls
        self.denied = denied

    async def require(self, _context, permission_code):
        self.calls.append("permission")
        if self.denied:
            raise PermissionError("permission denied")
        self.permission_code = permission_code


class SecurityGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_gates_execute_in_contract_order(self):
        calls = []
        scope_authorizer = FakeScopeAuthorizer(calls)
        permission_authorizer = FakePermissionAuthorizer(calls)
        result = await authorize_finance_request(
            request=object(),
            project_id=PROJECT_A,
            permission_code="finance.view",
            auth_provider=FakeAuth(calls),
            scope_authorizer=scope_authorizer,
            permission_authorizer=permission_authorizer,
        )
        self.assertEqual(
            ["authentication", "organization", "project", "permission"], calls
        )
        self.assertEqual(UUID(ORG_A), result.organization_id)
        self.assertEqual(PROJECT_A, result.project_id)
        self.assertEqual("fa", result.locale)

    async def test_host_locale_flows_to_finance_scope_without_changing_scope_or_permission(self):
        calls = []
        result = await authorize_finance_request(
            request=object(),
            project_id=PROJECT_A,
            permission_code="finance.view",
            auth_provider=FakeAuth(calls, "ar-SA"),
            scope_authorizer=FakeScopeAuthorizer(calls),
            permission_authorizer=FakePermissionAuthorizer(calls),
        )
        self.assertEqual((UUID(ORG_A), PROJECT_A, "ar"), (result.organization_id, result.project_id, result.locale))
        self.assertEqual(["authentication", "organization", "project", "permission"], calls)

    async def test_failed_organization_gate_stops_later_gates(self):
        calls = []
        with self.assertRaises(PermissionError):
            await authorize_finance_request(
                request=object(),
                project_id=PROJECT_A,
                permission_code="finance.view",
                auth_provider=FakeAuth(calls),
                scope_authorizer=FakeScopeAuthorizer(calls, "organization"),
                permission_authorizer=FakePermissionAuthorizer(calls),
            )
        self.assertEqual(["authentication", "organization"], calls)

    async def test_cross_project_membership_stops_permission_gate(self):
        calls = []
        with self.assertRaises(PermissionError):
            await authorize_finance_request(
                request=object(),
                project_id=PROJECT_B,
                permission_code="finance.view",
                auth_provider=FakeAuth(calls),
                scope_authorizer=FakeScopeAuthorizer(calls, "project"),
                permission_authorizer=FakePermissionAuthorizer(calls),
            )
        self.assertEqual(["authentication", "organization", "project"], calls)

    async def test_missing_finance_permission_is_denied(self):
        calls = []
        with self.assertRaises(PermissionError):
            await authorize_finance_request(
                request=object(),
                project_id=PROJECT_A,
                permission_code="finance.view",
                auth_provider=FakeAuth(calls),
                scope_authorizer=FakeScopeAuthorizer(calls),
                permission_authorizer=FakePermissionAuthorizer(calls, denied=True),
            )
        self.assertEqual(
            ["authentication", "organization", "project", "permission"], calls
        )

    def test_body_scope_cannot_enter_shared_guard(self):
        parameters = inspect.signature(authorize_finance_request).parameters
        self.assertNotIn("organization_id_body", parameters)
        self.assertNotIn("project_id_body", parameters)
        self.assertNotIn("body", parameters)

    def test_valid_id_outside_organization_is_hidden(self):
        scope = FinanceScope(organization_id=UUID(ORG_A), project_id=PROJECT_A)
        record = {"id": "valid-id", "organization_id": ORG_B, "project_id": PROJECT_A}
        with self.assertRaises(FinanceNotFound) as caught:
            require_scoped_record(record, scope)
        self.assertEqual((404, "FINANCE_NOT_FOUND"), (caught.exception.status, caught.exception.code))

    def test_valid_id_outside_project_is_hidden(self):
        scope = FinanceScope(organization_id=UUID(ORG_A), project_id=PROJECT_A)
        record = {"id": "valid-id", "organization_id": ORG_A, "project_id": PROJECT_B}
        with self.assertRaises(FinanceNotFound):
            require_scoped_record(record, scope)

    def test_file_outside_scope_is_hidden_without_returning_record(self):
        scope = FinanceScope(organization_id=UUID(ORG_A), project_id=PROJECT_A)
        file_record = {
            "file_id": "known-file",
            "organization_id": ORG_B,
            "project_id": PROJECT_B,
            "content": b"must-not-leak",
        }
        with self.assertRaises(FinanceNotFound):
            require_scoped_record(file_record, scope)


if __name__ == "__main__":
    unittest.main()
