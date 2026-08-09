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


class ExampleDto(ApiModel):
    project_id: str


class WiringTests(unittest.TestCase):
    def test_application_factory_builds_fastapi_app(self):
        application = create_app()
        self.assertEqual("BAMBO Finance", application.title)

    def test_finance_router_uses_project_scoped_contract(self):
        self.assertEqual("/projects/{projectId}/finance", router.prefix)

    def test_application_exposes_only_approved_through_stage_nineteen_endpoints(self):
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
                ("/api/projects/{projectId}/finance/summary", "get"),
                ("/api/projects/{projectId}/finance/resources", "get"),
                ("/api/projects/{projectId}/finance/resources", "post"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}", "get"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}", "patch"),
                ("/api/projects/{projectId}/finance/estimate-lines", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines", "post"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/revisions", "post"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}/prices", "get"),
                ("/api/projects/{projectId}/finance/resources/{resourceId}/prices", "post"),
                ("/api/projects/{projectId}/finance/price-history", "get"),
                ("/api/projects/{projectId}/finance/unit-conversions", "get"),
                ("/api/projects/{projectId}/finance/unit-conversions", "post"),
                ("/api/projects/{projectId}/finance/unit-conversions/{conversionId}", "patch"),
                ("/api/projects/{projectId}/finance/progress-snapshots", "get"),
                ("/api/projects/{projectId}/finance/progress-snapshots/{snapshotId}/feed", "get"),
                ("/api/projects/{projectId}/finance/estimate-lines/{lineId}/progress-override", "post"),
                ("/api/projects/{projectId}/finance/imports/estimate/preview", "post"),
                ("/api/projects/{projectId}/finance/imports/estimate/commit", "post"),
                ("/api/projects/{projectId}/finance/imports/prices/preview", "post"),
                ("/api/projects/{projectId}/finance/imports/prices/commit", "post"),
                ("/api/projects/{projectId}/finance/invoices", "get"),
                ("/api/projects/{projectId}/finance/invoices", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}", "get"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}", "patch"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/confirm", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/void", "post"),
                ("/api/projects/{projectId}/finance/invoices/{invoiceId}/corrective", "post"),
                ("/api/projects/{projectId}/finance/files", "post"),
                ("/api/projects/{projectId}/finance/files/{fileId}", "get"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}/retry", "post"),
                ("/api/projects/{projectId}/finance/extractions/{draftId}/confirm", "post"),
                ("/api/projects/{projectId}/finance/reports/live", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots", "post"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}/csv", "get"),
                ("/api/projects/{projectId}/finance/report-snapshots/{reportId}/xlsx", "get"),
            },
            business_operations,
        )

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
            {**valid, "locale": "en-US"},
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
