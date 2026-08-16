import sys
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.main import create_app
from app.finance.security.context import AuthContext

ORG=UUID("11111111-1111-4111-8111-111111111111")
ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT="sample_site_01"
SNAPSHOT=UUID("30000000-0000-4000-8000-000000000001")
REPORT=UUID("40000000-0000-4000-8000-000000000001")


class AuthProvider:
    def __init__(self,permissions):self.permissions=tuple(permissions)
    async def current(self,_request):
        return AuthContext(userId=ACTOR,organizationId=ORG,projectId=PROJECT,
            organizationRole="finance_viewer",projectRole="viewer",
            permissionCodes=self.permissions,locale="fa-IR",timezone="Asia/Tehran")


class ScopeAuthorizer:
    async def require_organization(self,_context,organization_id):
        if organization_id!=str(ORG):raise HTTPException(403,"organization denied")
    async def require_project(self,_context,organization_id,project_id):
        if organization_id!=str(ORG) or project_id!=PROJECT:raise HTTPException(403,"project denied")


class PermissionAuthorizer:
    async def require(self,context,permission_code):
        if permission_code not in context.permission_codes:raise HTTPException(403,"permission denied")


class Reports:
    async def overview(self,scope,reporting_date,progress_snapshot_id=None):
        return await self.live(scope,reporting_date,progress_snapshot_id)
    async def live(self,_scope,reporting_date,progress_snapshot_id=None):
        return {"reportingDate":reporting_date,"progressSnapshotId":progress_snapshot_id or SNAPSHOT,
            "metrics":{"initialEstimateIrr":"100","actualCostIrr":"50","currentExecutedValueIrr":"40","remainingPhysicalCostIrr":"60","moneyRequiredToContinueIrr":"50","forecastFinalCostIrr":"100","actualCostPerSquareMeterIrr":"5","forecastPerSquareMeterIrr":"10"},
            "breakdown":[],"topPriceVariances":[],"topQuantityVariances":[],"warnings":[],"calculationStatus":"complete","incompleteMetricKeys":[],"missingPriceCount":0}
    async def get_snapshot(self,scope,report_id):
        return {"reportSnapshotId":report_id,"organizationId":scope.organization_id,"projectId":scope.project_id,
            "issuedAt":"2026-08-09T00:00:00Z","issuedBy":ACTOR,"progressSnapshotId":SNAPSHOT,
            "resourceVersionIds":[UUID(int=1)],"priceVersionIds":[UUID(int=2)],"invoiceIds":[],
            "unitConversionIds":[],"calculatedMetrics":{"actualCostIrr":"50"},"immutable":True}


def client(permissions):
    app=create_app();app.state.auth_context_provider=AuthProvider(permissions)
    app.state.scope_authorizer=ScopeAuthorizer();app.state.permission_authorizer=PermissionAuthorizer()
    app.state.finance_live_report_service=Reports()
    return TestClient(app)


class ReportingPermissionApiTests(unittest.TestCase):
    def test_report_view_only_can_read_live_and_issued_reports(self):
        with client(("finance_report.view",)) as api:
            live=api.get(f"/api/projects/{PROJECT}/finance/reports/live",params={"reportingDate":"2026-08-09"})
            issued=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots/{REPORT}")
        self.assertEqual((200,200),(live.status_code,issued.status_code))
        self.assertEqual("50",live.json()["metrics"]["actualCostIrr"])
        self.assertNotIn("invoiceIds",live.json())

    def test_report_view_only_cannot_read_or_mutate_operational_finance(self):
        reads=("invoices","price-history","estimate-lines","files","extractions")
        with client(("finance_report.view",)) as api:
            responses=[api.get(f"/api/projects/{PROJECT}/finance/{path}") for path in reads]
            mutation=api.post(f"/api/projects/{PROJECT}/finance/resources",json={"type":"general_cost","code":"G-1","title":"Internal"})
        self.assertTrue(all(response.status_code==403 for response in responses))
        self.assertEqual(403,mutation.status_code)

    def test_operational_view_and_report_view_do_not_grant_export(self):
        for permissions in (("finance.view",),("finance_report.view",)):
            with self.subTest(permissions=permissions),client(permissions) as api:
                csv=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots/{REPORT}/csv")
                xlsx=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots/{REPORT}/xlsx")
                self.assertEqual((403,403),(csv.status_code,xlsx.status_code))

    def test_finance_view_only_keeps_operational_summary_but_cannot_read_live_report(self):
        with client(("finance.view",)) as api:
            denied=api.get(f"/api/projects/{PROJECT}/finance/reports/live",params={"reportingDate":"2026-08-09"})
            overview=api.get(f"/api/projects/{PROJECT}/finance/overview",params={"reportingDate":"2026-08-09"})
            issue=api.post(f"/api/projects/{PROJECT}/finance/report-snapshots",json={"reportingDate":"2026-08-09"})
            issued=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots/{REPORT}")
        self.assertEqual((403,200,403,403),(denied.status_code,overview.status_code,issue.status_code,issued.status_code))
        self.assertEqual("complete",overview.json()["calculationStatus"])


if __name__=="__main__":unittest.main()
