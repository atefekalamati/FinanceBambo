import sys
import inspect
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.router import router
from app.finance.adapters.ports import FileStorage
from app.finance.repositories.ports import FinanceRepository
from app.finance.schemas.base import ApiModel
from app.finance.security.context import AuthContext
from app.version import VERSION


class ExampleDto(ApiModel):
    project_id: str


class WiringTests(unittest.TestCase):
    def test_application_factory_builds_fastapi_app(self):
        application = create_app()
        self.assertEqual("BAMBO Finance", application.title)

    def test_finance_router_uses_project_scoped_contract(self):
        self.assertEqual("/projects/{projectId}/finance", router.prefix)

    def test_application_exposes_only_approved_through_stage_twenty_endpoints(self):
        application = create_app()
        paths = application.openapi()["paths"]
        business_operations = {
            (path, method)
            for path, operations in paths.items()
            if path.startswith("/api/")
            for method in operations
        }
        self.assertEqual(
            {
                ("/api/projects/{projectId}/finance/settings", "get"),
                ("/api/projects/{projectId}/finance/settings", "patch"),
                ("/api/projects/{projectId}/finance/settings/revisions", "get"),
                ("/api/projects/{projectId}/finance/summary", "get"),
                ("/api/projects/{projectId}/finance/resources", "get"),
                ("/api/projects/{projectId}/finance/resources", "post"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}", "get"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}", "patch"),
                ("/api/projects/{projectId}/finance/unit-registry", "get"),
                ("/api/projects/{projectId}/finance/activities", "get"),
                ("/api/projects/{projectId}/finance/activities", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/revisions", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/progress-overrides", "get"),
                ("/api/projects/{projectId}/finance/task-resource-mappings", "get"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}/prices", "get"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}/prices", "post"),
                ("/api/projects/{projectId}/finance/price-history", "get"),
                ("/api/projects/{projectId}/finance/prices/current", "get"),
                ("/api/projects/{projectId}/finance/unit-conversions", "get"),
                ("/api/projects/{projectId}/finance/unit-conversions", "post"),
                ("/api/projects/{projectId}/finance/unit-conversions/{conversionId}", "patch"),
                ("/api/projects/{projectId}/finance/progress-snapshots", "get"),
                ("/api/projects/{projectId}/finance/progress-snapshots/{snapshotId}", "get"),
                ("/api/projects/{projectId}/finance/progress-snapshots/{snapshotId}/feed", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/progress-override", "post"),
                ("/api/projects/{projectId}/finance/imports/estimate/preview", "post"),
                ("/api/projects/{projectId}/finance/imports/estimate/commit", "post"),
                ("/api/projects/{projectId}/finance/imports/prices/preview", "post"),
                ("/api/projects/{projectId}/finance/imports/estimate/preview-link", "post"),
                ("/api/projects/{projectId}/finance/imports/prices/preview-link", "post"),
                ("/api/projects/{projectId}/finance/imports/prices/commit", "post"),
                ("/api/projects/{projectId}/finance/invoices", "get"),
                ("/api/projects/{projectId}/finance/invoices", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}", "get"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}", "patch"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/confirm", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/void", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/corrective", "post"),
                ("/api/projects/{projectId}/finance/files", "post"),
                ("/api/projects/{projectId}/finance/files", "get"),
                ("/api/projects/{projectId}/finance/files/{fileId}", "get"),
                ("/api/projects/{projectId}/finance/files/{fileId}/content", "get"),
                ("/api/projects/{projectId}/finance/files/{fileId}/extractions", "post"),
                ("/api/projects/{projectId}/finance/extractions", "get"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}", "get"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}/reject", "post"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}/retry", "post"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}/confirm", "post"),
                ("/api/projects/{projectId}/finance/overview", "get"),
                ("/api/projects/{projectId}/finance/reports/live", "get"),
                ("/api/projects/{projectId}/finance/reports/monthly", "get"),
                ("/api/projects/{projectId}/finance/reports/live/variances", "get"),
                ("/api/projects/{projectId}/finance/reports/live/by-wbs", "get"),
                ("/api/projects/{projectId}/finance/files/{fileId}/extractions/async", "post"),
                ("/api/projects/{projectId}/finance/report-snapshots", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots", "post"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}/csv", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}/xlsx", "get"),
                ("/api/projects/{projectId}/finance/audit-events", "get"),
                # Material prices, stage twenty-one. Read-only against the database;
                # the one write is a person choosing the unit a category is shown in.
                # No endpoint here reaches Google Sheets -- the import is a job.
                ("/api/projects/{projectId}/finance/material-prices/categories", "get"),
                ("/api/projects/{projectId}/finance/material-prices/current", "get"),
                ("/api/projects/{projectId}/finance/material-prices/runs", "get"),
                ("/api/projects/{projectId}/finance/material-prices/invalid-rows", "get"),
                ("/api/projects/{projectId}/finance/material-prices/unit-settings", "get"),
                ("/api/projects/{projectId}/finance/material-prices/unit-settings", "post"),
                ("/api/projects/{projectId}/finance/material-prices/{providerItemId}/history", "get"),
                # Labels and factors, stage twenty-two. Reading is finance.view;
                # writing a label, a mapping approval or a measured factor is
                # finance.edit, the same permission a price version already needs.
                ("/api/projects/{projectId}/finance/material-prices/labels", "get"),
                ("/api/projects/{projectId}/finance/material-prices/unresolved", "get"),
                # The bridge between the schedule and the market price. Read endpoints are
                # finance.view; the one that writes a mapping is finance.edit.
                ("/api/projects/{projectId}/finance/item-price-mappings/status", "get"),
                ("/api/projects/{projectId}/finance/item-price-mappings/candidates", "get"),
                ("/api/projects/{projectId}/finance/item-price-mappings/filters", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/history", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-preview", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/components", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/components", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/components/history", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/components/{componentId}", "patch"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-component-preview", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/price-total-preview", "get"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions", "get"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions", "post"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions/{ruleId}", "get"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions/{ruleId}/history", "get"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions/{ruleId}/preview", "get"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions/{ruleId}/approve", "post"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversions/{ruleId}/supersede", "post"),
                ("/api/projects/{projectId}/finance/finance-settings/unit-conversion-issues", "get"),
                ("/api/projects/{projectId}/finance/material-prices/{providerItemId}/labels", "get"),
                ("/api/projects/{projectId}/finance/material-prices/{providerItemId}/labels", "post"),
                ("/api/projects/{projectId}/finance/material-prices/{providerItemId}/factors", "get"),
                ("/api/projects/{projectId}/finance/material-prices/{providerItemId}/factors", "post"),
            },
            business_operations,
        )

    def test_openapi_matches_runtime_pagination_filters_and_new_dto_fields(self):
        spec=create_app().openapi();paths=spec["paths"];schemas=spec["components"]["schemas"]
        self.assertEqual(VERSION, spec["info"]["version"])
        self.assertIn("opaque session", spec["info"]["description"])
        attachment_content = paths["/api/projects/{projectId}/finance/files/{fileId}/content"]["get"]["responses"]["200"]["content"]
        self.assertIn("image/png", attachment_content)
        csv_content = paths["/api/projects/{projectId}/finance/report-snapshots/{reportId}/csv"]["get"]["responses"]["200"]["content"]
        xlsx_content = paths["/api/projects/{projectId}/finance/report-snapshots/{reportId}/xlsx"]["get"]["responses"]["200"]["content"]
        self.assertEqual({"text/csv"}, set(csv_content))
        self.assertEqual({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}, set(xlsx_content))
        file_params={item["name"]:item["schema"] for item in paths["/api/projects/{projectId}/finance/files"]["get"]["parameters"]}
        extraction_params={item["name"]:item["schema"] for item in paths["/api/projects/{projectId}/finance/extractions"]["get"]["parameters"]}
        invoice_params={item["name"]:item["schema"] for item in paths["/api/projects/{projectId}/finance/invoices"]["get"]["parameters"]}
        for params in (file_params,extraction_params,invoice_params):
            self.assertEqual((50,200),(params["pageSize"]["default"],params["pageSize"]["maximum"]))
        self.assertTrue({"reviewStatus","source","fileId","linkedInvoiceId"}<=set(extraction_params))
        self.assertTrue({"query","status","source","invoiceDateFrom","invoiceDateTo"}<=set(invoice_params))
        # The issued-report listing pages like every other list and filters on the date
        # the report describes, not the moment it was drawn.
        snapshot_params={item["name"] for item in paths["/api/projects/{projectId}/finance/report-snapshots"]["get"]["parameters"]}
        self.assertTrue({"page","pageSize","reportingDateFrom","reportingDateTo"}<=snapshot_params)
        self.assertTrue({"items","page","pageSize","totalItems","totalPages"}<=set(schemas["ReportSnapshotListResponse"]["properties"]))
        summary=set(schemas["ReportSnapshotSummary"]["properties"])
        self.assertTrue({"reportSnapshotId","reportingDate","issuedAt","issuedBy",
                         "progressSnapshotId","invoiceCount","priceVersionCount"}<=summary)
        # A listing must not carry arrays that grow with the project.
        self.assertTrue({"invoiceIds","priceVersionIds","resourceVersionIds","calculatedMetrics"}.isdisjoint(summary))
        # issuedAt alone cannot say what a report is about.
        self.assertIn("reportingDate",schemas["ReportSnapshotReference"]["properties"])
        self.assertTrue({"version","createdAt","linkedInvoiceId"}<=set(schemas["ExtractionDraftResponse"]["properties"]))
        self.assertIn("lineAmountIrr",schemas["InvoiceLineCreate"]["properties"])
        self.assertIn("examples",schemas["ExtractionStart"])
        self.assertIn("examples",schemas["InvoiceListResponse"])
        self.assertIn("409",paths["/api/projects/{projectId}/finance/extractions/{draftId}/reject"]["post"]["responses"])
        preview=schemas["ImportPreviewResponse"]
        self.assertTrue({"previewId","kind","rowCount","validCount","invalidCount","rows","errors","canCommit"}<=set(preview["properties"]))
        # The import screens branch on duplicateFile and name the earlier import from
        # duplicateCommittedAt; renaming either would silently degrade the notice.
        self.assertTrue({"duplicateFile","duplicateOfImportId","duplicateCommittedAt"}<=set(preview["properties"]))
        # A repeated file is refused at commit with 409, so the spec has to say so.
        for kind in ("estimate","prices"):
            commit=paths["/api/projects/{projectId}/finance/imports/%s/commit" % kind]["post"]
            self.assertIn("409",commit["responses"])
        self.assertTrue({"rowNumber","status","errors","resourceCode","resourceId","resourceTitle","baseUnit"}<=set(schemas["ImportPreviewRow"]["properties"]))
        self.assertTrue({"revision","revisions"}<=set(schemas["EstimateLineResponse"]["properties"]))
        self.assertTrue({"activityTitle","wbsCode"}<=set(schemas["EstimateLineResponse"]["properties"]))
        self.assertTrue({"items","page","pageSize","totalItems","totalPages"}<=set(schemas["ActivityListResponse"]["properties"]))
        self.assertTrue({"code","labelFa","dimension","dimensionLabelFa","decimalPrecision","active"}<=set(schemas["UnitDefinitionResponse"]["properties"]))
        self.assertTrue({"organizationPriceIrr","organizationEffectiveFrom","projectPriceIrr","projectEffectiveFrom","currentEffectiveFrom"}<=set(schemas["CurrentPriceTrendResponse"]["properties"]))
        # The price import form carries the file alone: normalization reads each row's own
        # mandatory currency column, so no batch-level currency unit is asked for.
        price_import=schemas[paths["/api/projects/{projectId}/finance/imports/prices/preview"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].rsplit("/",1)[-1]]
        self.assertEqual(["file"],price_import["required"])
        self.assertEqual({"file"},set(price_import["properties"]))
        # Variance rows are discriminated, so a mixed page cannot validate into the wrong shape.
        self.assertEqual("varianceKind",
            schemas["ReportVarianceListResponse"]["properties"]["items"]["items"]["discriminator"]["propertyName"])
        self.assertEqual("price",schemas["PriceVariance"]["properties"]["varianceKind"]["const"])
        self.assertEqual("quantity",schemas["QuantityVariance"]["properties"]["varianceKind"]["const"])
        # Audit history is paged like every other list, and filters run server-side.
        audit=paths["/api/projects/{projectId}/finance/audit-events"]["get"]
        audit_params={item["name"] for item in audit["parameters"]}
        self.assertTrue({"page","pageSize","action","entityType","occurredFrom","occurredTo","query"}<=audit_params)
        self.assertTrue({"items","page","pageSize","totalItems","totalPages"}<=set(schemas["AuditEventListResponse"]["properties"]))
        # totalItems is the canonical count name; totalCount stays for existing clients.
        for name in ("AttachmentListResponse","ExtractionListResponse"):
            self.assertTrue({"totalItems","totalCount"}<=set(schemas[name]["properties"]),name)
        # sortBy is bound to numeric columns; an arbitrary column would crash the sort.
        variance_params={item["name"]:item["schema"] for item in paths["/api/projects/{projectId}/finance/reports/live/variances"]["get"]["parameters"]}
        self.assertIn("varianceIrr",str(variance_params["sortBy"]))
        self.assertNotIn("resourceCode",str(variance_params["sortBy"]))

    def test_error_envelope_uses_public_camel_case_request_id(self):
        # The envelope is built in one helper shared by every handler, so inspect the module.
        source=inspect.getsource(sys.modules[create_app.__module__])
        self.assertIn('"requestId"',source)
        self.assertNotIn('"request_id"',source)

    def test_dto_serializes_camel_case_and_rejects_unknown_fields(self):
        dto = ExampleDto(projectId="sample_site_01")
        self.assertEqual({"projectId": "sample_site_01"}, dto.model_dump(by_alias=True))
        with self.assertRaises(ValueError):
            ExampleDto(projectId="sample_site_01", organizationId="untrusted")

    def test_auth_context_matches_public_host_shape(self):
        context = AuthContext(
            userId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            organizationId="11111111-1111-4111-8111-111111111111",
            projectId="sample_site_01",
            organizationRole="org_chief",
            projectRole="project_admin",
            permissionCodes=["finance.view"],
            locale="fa-IR",
            timezone="Asia/Tehran",
        )
        self.assertEqual("sample_site_01", context.project_id)
        self.assertEqual(("finance.view",), context.permission_codes)
        self.assertEqual("fa", context.locale)

    def test_auth_context_accepts_host_owned_fa_en_ar_locale_and_fallbacks_invalid(self):
        valid = {
            "userId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            "organizationId": "11111111-1111-4111-8111-111111111111",
            "projectId": "sample_site_01",
            "organizationRole": "org_chief",
            "projectRole": "project_admin",
            "permissionCodes": ["finance.view"],
            "timezone": "Asia/Tehran",
        }
        self.assertEqual("fa", AuthContext(**valid, locale="fa").locale)
        self.assertEqual("fa", AuthContext(**valid, locale="fa-IR").locale)
        self.assertEqual("en", AuthContext(**valid, locale="en-US").locale)
        self.assertEqual("ar", AuthContext(**valid, locale="ar-SA").locale)
        self.assertEqual("fa", AuthContext(**valid, locale="de-DE").locale)

    def test_auth_context_enforces_host_schema(self):
        valid = {
            "userId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            "organizationId": "11111111-1111-4111-8111-111111111111",
            "projectId": "sample_site_01",
            "organizationRole": "org_chief",
            "projectRole": "project_admin",
            "permissionCodes": ["finance.view"],
            "locale": "fa-IR",
            "timezone": "Asia/Tehran",
        }
        invalid_cases = (
            {**valid, "userId": "not-a-uuid"},
            {**valid, "projectId": "unsafe/project"},
            {**valid, "permissionCodes": ["finance.view", "finance.view"]},
            {**valid, "permissionCodes": ["Finance.View"]},
            {**valid, "timezone": "UTC"},
        )
        for payload in invalid_cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                AuthContext(**payload)

    def test_file_storage_get_requires_dual_scope(self):
        parameters = tuple(inspect.signature(FileStorage.get).parameters)
        self.assertEqual(
            ("self", "organization_id", "project_id", "file_id"), parameters
        )

    def test_repository_port_does_not_invent_health_contract(self):
        self.assertFalse(hasattr(FinanceRepository, "ping"))


if __name__ == "__main__":
    unittest.main()
