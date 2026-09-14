import sys
import unittest
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.main import create_app
from app.finance.schemas.base import to_camel
from app.finance.security.context import AuthContext
from app.finance.schemas.reports import OperationalOverviewResponse
from app.finance.services.reports import FinanceLiveReportService

OVERVIEW_KEYS={to_camel(name) for name in FinanceLiveReportService.OVERVIEW_FIELDS}

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
        report=await self.live(scope,reporting_date,progress_snapshot_id)
        return {key:report[key] for key in OVERVIEW_KEYS}
    async def live(self,_scope,reporting_date,progress_snapshot_id=None):
        return {"reportingDate":reporting_date,"progressSnapshotId":progress_snapshot_id or SNAPSHOT,
            # Which Core snapshot was calculated from. Present whether or not a Finance
            # reference exists, because reading no longer creates one.
            "hostSnapshotId":9001,
            "metrics":{"initialEstimateIrr":"100","actualCostIrr":"50","currentExecutedValueIrr":"40","remainingPhysicalCostIrr":"60","moneyRequiredToContinueIrr":"50","forecastFinalCostIrr":"100","actualCostPerSquareMeterIrr":"5","forecastPerSquareMeterIrr":"10"},
            "breakdown":[],"topPriceVariances":[],"topQuantityVariances":[],"warnings":[],"calculationStatus":"complete","incompleteMetricKeys":[],"missingPriceCount":2,"missingEstimateLineCount":4,"excludedEstimateLineCount":3,
            "progressQuality":{"complete":False,"manualOverrideCount":1,"taskFallbackCount":0,"missingCount":1,
                "assignmentActualCount":2,"assignmentPercentFallbackCount":0,"mappedLineCount":3,
                "unmappedLineCount":1,"generalCostLineCount":1,"workAsQuantityCount":1,
                "unmappedAssignmentCount":1,"unmappedActivityCount":0}}
    async def list_snapshots(self,scope,page=1,page_size=50,reporting_date_from=None,reporting_date_to=None):
        self.list_call={"page":page,"page_size":page_size,"from":reporting_date_from,"to":reporting_date_to}
        return {"items":[{"reportSnapshotId":REPORT,"reportingDate":"2026-08-09",
                          "issuedAt":"2026-08-09T00:00:00Z","issuedBy":ACTOR,
                          "progressSnapshotId":SNAPSHOT,"invoiceCount":3,"priceVersionCount":2}],
                "page":page,"pageSize":page_size,"totalItems":9,"totalPages":1}
    async def get_snapshot(self,scope,report_id):
        return {"reportSnapshotId":report_id,"organizationId":scope.organization_id,"projectId":scope.project_id,
            "reportingDate":"2026-08-09","issuedAt":"2026-08-09T00:00:00Z","issuedBy":ACTOR,"progressSnapshotId":SNAPSHOT,
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
        # The projection is the whole reason finance.view may call this route: it must not
        # widen into reporting-only fields that finance_report.view is supposed to gate.
        self.assertEqual(OVERVIEW_KEYS,set(overview.json()))

    def test_operational_projection_exposes_the_agreed_fields_and_nothing_reporting_only(self):
        self.assertEqual(("reporting_date","progress_snapshot_id","host_snapshot_id","metrics","breakdown","top_price_variances",
            "top_quantity_variances","warnings","calculation_status","incomplete_metric_keys",
            "missing_price_count","missing_estimate_line_count","excluded_estimate_line_count",
            "progress_quality"),
            FinanceLiveReportService.OVERVIEW_FIELDS)
        self.assertEqual(set(OperationalOverviewResponse.model_fields),set(FinanceLiveReportService.OVERVIEW_FIELDS))
        # progressQuality is aggregate counts and joins the other counters that qualify these
        # metrics. excludedEstimateLineIds still names individual estimate lines, so it is the
        # one reporting-only field that must never reach this projection.
        self.assertNotIn("excluded_estimate_line_ids",FinanceLiveReportService.OVERVIEW_FIELDS)
        self.assertNotIn("excluded_estimate_line_ids",OperationalOverviewResponse.model_fields)

    def test_the_operational_projection_carries_counts_but_never_a_record_id(self):
        with client(("finance.view",)) as api:
            overview=api.get(f"/api/projects/{PROJECT}/finance/overview",
                params={"reportingDate":"2026-08-09"}).json()
        quality=overview["progressQuality"]
        self.assertEqual({"complete","manualOverrideCount","taskFallbackCount","missingCount",
            "assignmentActualCount","assignmentPercentFallbackCount","mappedLineCount",
            "unmappedLineCount","generalCostLineCount","workAsQuantityCount",
            "unmappedAssignmentCount","unmappedActivityCount"},set(quality))
        # Carried through the projection rather than defaulted away: the service reported one
        # of its two assignment actuals as work effort, and finance.view is told so.
        self.assertEqual((2,1),(quality["assignmentActualCount"],quality["workAsQuantityCount"]))
        # Every value is a count or a flag; nothing here identifies a row.
        self.assertTrue(all(isinstance(value,(int,bool)) for value in quality.values()))
        self.assertNotIn("excludedEstimateLineIds",overview)

    def test_projection_carries_the_counters_the_dashboard_banner_reads(self):
        # finance-home-page.js renders "N قیمت و M ردیف ... لحاظ نشده" from these two.
        # Dropping them would leave the banner truthfully flagged but reporting 0 and 0.
        with client(("finance.view",)) as api:
            overview=api.get(f"/api/projects/{PROJECT}/finance/overview",params={"reportingDate":"2026-08-09"}).json()
        self.assertEqual((2,3),(overview["missingPriceCount"],overview["excludedEstimateLineCount"]))


    def test_the_snapshot_listing_needs_report_view_and_summarises_rather_than_pins(self):
        with client(("finance_report.view",)) as api:
            listed=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots",
                params={"reportingDateFrom":"2026-08-01","reportingDateTo":"2026-08-31","page":1,"pageSize":50})
        self.assertEqual(200,listed.status_code)
        payload=listed.json()
        self.assertEqual({"items","page","pageSize","totalItems","totalPages"},set(payload))
        # The whole match, not the page: a client cannot page through a total it never sees.
        self.assertEqual(9,payload["totalItems"])
        row=payload["items"][0]
        self.assertEqual({"reportSnapshotId","reportingDate","issuedAt","issuedBy",
                          "progressSnapshotId","invoiceCount","priceVersionCount"},set(row))
        # The pinned arrays belong to the detail endpoint; they grow with the project.
        for field in ("invoiceIds","priceVersionIds","resourceVersionIds","calculatedMetrics"):
            self.assertNotIn(field,row)

    def test_finance_view_alone_cannot_list_issued_reports(self):
        with client(("finance.view",)) as api:
            denied=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots")
        self.assertEqual(403,denied.status_code)
        self.assertEqual("FINANCE_FORBIDDEN",denied.json()["error"]["code"])

    def test_the_issued_report_says_which_date_it_is_about(self):
        with client(("finance_report.view",)) as api:
            issued=api.get(f"/api/projects/{PROJECT}/finance/report-snapshots/{REPORT}")
        self.assertEqual(200,issued.status_code)
        # issuedAt says when it was drawn; reportingDate says what it describes.
        self.assertEqual("2026-08-09",issued.json()["reportingDate"])


class InvoicePermissionIsEnforcedInTheBackendTests(unittest.TestCase):
    """The host was explicit: hiding the button is not the control.

    "Only make sure this permission is checked in the backend too, and do not rely on
    hiding or showing the button in the frontend." So the check is asserted against the
    ROUTER SOURCE rather than against a test double -- a double can be wired to agree with
    whatever the code does, and the question here is what the code says.

    Decision pack D-2, settled: the submitter-only rule stays removed. Anyone holding
    `finance.manage_invoice` may confirm any invoice in the project, their own or another
    person's. That is a rule about WHO may act, and it does not weaken WHAT is required --
    which is exactly what these three routes state.
    """

    ROUTER = (Path(__file__).resolve().parents[1]
              / "app" / "finance" / "router.py").read_text(encoding="utf-8")

    #: The three the host named. Each must demand the invoice permission and nothing less.
    GUARDED = ("/invoices/{invoiceId}/confirm",
               "/invoices/{invoiceId}/void",
               "/invoices/{invoiceId}/corrective")

    def handler_of(self, route):
        """The source of the handler registered for one route path."""
        marker = '@router.post("%s"' % route
        self.assertIn(marker, self.ROUTER, "no POST is registered for %s" % route)
        start = self.ROUTER.index(marker)
        following = self.ROUTER.find("@router.", start + 1)
        return self.ROUTER[start:following if following != -1 else len(self.ROUTER)]

    def test_each_of_the_three_demands_finance_manage_invoice(self):
        for route in self.GUARDED:
            with self.subTest(route=route):
                body = self.handler_of(route)
                self.assertIn('"finance.manage_invoice"', body)

    def test_none_of_the_three_accepts_finance_edit_instead(self):
        # The failure this guards is a caller who may author baselines quietly gaining the
        # ability to confirm money out of the door.
        for route in self.GUARDED:
            with self.subTest(route=route):
                self.assertNotIn('"finance.edit"', self.handler_of(route))

    def test_no_route_anywhere_accepts_either_of_the_two(self):
        """A temporary bridge -- "manage_invoice OR edit" -- would defeat the whole point.

        None exists today. If one is ever added it must be a named constant with its own
        test and a recorded removal date, and this assertion is what forces that
        conversation instead of letting the pair appear inline.
        """
        for line in self.ROUTER.splitlines():
            if "finance.manage_invoice" in line and "finance.edit" in line:
                self.fail("a route names both permissions on one line: %s" % line.strip())

    def test_the_ai_path_still_belongs_to_whoever_uploaded_the_file(self):
        """FR-063 is untouched by D-2: confirming an EXTRACTION is the uploader's alone.

        Different question from confirming an invoice. The extraction is a draft of what a
        photograph said, and only the person who supplied the photograph can say whether it
        was read correctly.
        """
        extractions = (Path(__file__).resolve().parents[1]
                       / "app" / "finance" / "services" / "extractions.py"
                       ).read_text(encoding="utf-8")
        self.assertIn("only the uploader can confirm this extraction", extractions)
        self.assertIn("ExtractionForbidden", extractions)


if __name__=="__main__":unittest.main()
