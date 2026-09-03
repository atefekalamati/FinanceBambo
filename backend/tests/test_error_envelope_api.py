import sys
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.main import create_app
from app.finance.domain.resources import FinanceRecordNotFound
from app.finance.security.context import AuthContext

ORG=UUID("11111111-1111-4111-8111-111111111111")
ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT="sample_site_01"
SNAPSHOT=UUID("30000000-0000-4000-8000-000000000001")
LINE=UUID("10000000-0000-4000-8000-000000000001")


class AuthProvider:
    def __init__(self,permissions):self.permissions=tuple(permissions)
    async def current(self,_request):
        return AuthContext(userId=ACTOR,organizationId=ORG,projectId=PROJECT,
            permissionCodes=list(self.permissions),organizationRole="finance_expert",
            projectRole="finance_expert",timezone="Asia/Tehran",locale="fa")


class ScopeAuthorizer:
    async def require_organization(self,_context,organization_id):
        if organization_id!=str(ORG):raise HTTPException(403,"organization denied")
    async def require_project(self,_context,organization_id,project_id):
        if organization_id!=str(ORG) or project_id!=PROJECT:raise HTTPException(403,"project denied")


class PermissionAuthorizer:
    async def require(self,context,permission_code):
        if permission_code not in context.permission_codes:raise HTTPException(403,"permission denied")


class Progress:
    async def override(self,_scope,_line_id,_command):raise FinanceRecordNotFound("progress snapshot not found")


def client(permissions=("finance.view","finance.edit")):
    app=create_app();app.state.auth_context_provider=AuthProvider(permissions)
    app.state.scope_authorizer=ScopeAuthorizer();app.state.permission_authorizer=PermissionAuthorizer()
    app.state.progress_service=Progress()
    return TestClient(app)


def envelope(response):
    payload=response.json()
    assert set(payload)=={"error"},payload
    error=payload["error"]
    assert set(error)=={"code","message","requestId","details"},error
    assert error["requestId"].startswith("req-"),error
    return error


class ErrorEnvelopeApiTests(unittest.TestCase):
    """Every failure the browser can provoke must arrive in the one shape api-client.js parses."""

    def test_rejected_payload_names_the_offending_fields(self):
        with client() as api:
            response=api.post(f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json={"progressSnapshotId":str(SNAPSHOT),"overrideValue":"9","reason":"  "})
        self.assertEqual(422,response.status_code)
        error=envelope(response)
        self.assertEqual("VALIDATION_ERROR",error["code"])
        self.assertEqual(["reason"],[item["field"] for item in error["details"]])
        self.assertTrue(error["details"][0]["message"])

    def test_validation_details_carry_the_nested_field_path_without_echoing_the_value(self):
        with client() as api:
            response=api.post(f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json={"progressSnapshotId":"not-a-uuid","overrideValue":"secret-value","reason":"اصلاح معتبر"})
        error=envelope(response)
        self.assertEqual({"progressSnapshotId","overrideValue"},{item["field"] for item in error["details"]})
        self.assertNotIn("secret-value",response.text)

    def test_unknown_field_is_reported_rather_than_silently_dropped(self):
        with client() as api:
            response=api.post(f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json={"progressSnapshotId":str(SNAPSHOT),"overrideValue":"9","reason":"اصلاح معتبر","surprise":1})
        self.assertEqual(422,response.status_code)
        self.assertIn("surprise",{item["field"] for item in envelope(response)["details"]})

    def test_permission_denial_carries_the_forbidden_code(self):
        with client(permissions=("finance.view",)) as api:
            response=api.post(f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json={"progressSnapshotId":str(SNAPSHOT),"overrideValue":"9","reason":"اصلاح معتبر"})
        self.assertEqual(403,response.status_code)
        error=envelope(response)
        self.assertEqual(("FINANCE_FORBIDDEN","permission denied"),(error["code"],error["message"]))

    def test_unknown_route_is_enveloped_too(self):
        with client() as api:
            response=api.get(f"/api/projects/{PROJECT}/finance/no-such-endpoint")
        self.assertEqual(404,response.status_code)
        self.assertEqual("FINANCE_NOT_FOUND",envelope(response)["code"])

    def test_domain_errors_keep_their_own_status_and_code(self):
        with client() as api:
            response=api.post(f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json={"progressSnapshotId":str(SNAPSHOT),"overrideValue":"9","reason":"اصلاح معتبر"})
        self.assertEqual(404,response.status_code)
        error=envelope(response)
        self.assertEqual(("FINANCE_NOT_FOUND","progress snapshot not found"),(error["code"],error["message"]))

    def test_every_request_gets_a_distinct_request_id(self):
        with client() as api:
            first=api.get(f"/api/projects/{PROJECT}/finance/missing-a")
            second=api.get(f"/api/projects/{PROJECT}/finance/missing-b")
        self.assertNotEqual(envelope(first)["requestId"],envelope(second)["requestId"])


if __name__=="__main__":unittest.main()
