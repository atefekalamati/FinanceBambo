import sys
import unittest
from pathlib import Path

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))


class DeliveryGateTests(unittest.TestCase):
    def test_multipart_dependency_contains_security_fixes(self):
        requirements=(BACKEND_ROOT/"requirements.txt").read_text(encoding="utf-8")
        self.assertIn("python-multipart==0.0.31",requirements)

    def test_integration_guide_names_every_route_service(self):
        guide=(BACKEND_ROOT/"INTEGRATION_GUIDE_FA.md").read_text(encoding="utf-8")
        for service in ("finance_settings_service","finance_resources_service","finance_price_service",
                        "unit_conversion_service","progress_service","finance_import_service","invoice_service",
                        "finance_attachment_service","finance_extraction_service","finance_live_report_service",
                        "finance_audit_service"):
            self.assertIn(service,guide)

    def test_production_code_has_no_mock_auth_header(self):
        sources="\n".join(path.read_text(encoding="utf-8") for path in (BACKEND_ROOT/"app").rglob("*.py"))
        self.assertNotIn("X-Mock-User",sources)


if __name__=="__main__":unittest.main()
