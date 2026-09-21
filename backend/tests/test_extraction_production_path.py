# -*- coding: utf-8 -*-
"""Production invoice extraction flow up to a reviewable draft.

No network and no database are used here. The point is the contract boundary:
OCR text is preserved, the deterministic parser runs first, the configurable LLM fills
only the gaps when enabled, and nothing in this path confirms a financial invoice.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.main import create_app
from app.finance.domain.attachments import FinanceAttachment
from app.finance.domain.extractions import ExtractionDraft, ExtractionField
from app.finance.schemas.extractions import ProviderExtractionResult
from app.finance.security.context import AuthContext
from extraction.adapters import RAW_TEXT_KEY, _as_contract
from extraction.providers.llm_invoice import (ExtractionProviderResponseInvalid,
                                              LLMInvoiceExtractionProvider, parse_candidate)


def keys(payload):
    return [field["key"] for field in payload["fields"]]


class FlexibleExtractionPathTests(unittest.TestCase):
    def setUp(self):
        self.saved = {name: os.environ.get(name) for name in (
            "FINANCE_AI_EXTRACTION_ENABLED",
            "FINANCE_AI_PROVIDER",
            "FINANCE_AI_API_KEY",
            "FINANCE_AI_MODEL",
        )}
        from extraction import adapters
        self._adapters = adapters
        self._original_build_provider = adapters.build_extraction_provider
        os.environ.pop("AVALAI_API_KEY", None)

    def tearDown(self):
        self._adapters.build_extraction_provider = self._original_build_provider
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def enable_ai(self, answer):
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "true"
        os.environ["FINANCE_AI_PROVIDER"] = "openai"
        os.environ["FINANCE_AI_API_KEY"] = "test-key"
        os.environ["FINANCE_AI_MODEL"] = "test-model"

        body = {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}]}

        def post(*_a):
            return 200, json.dumps(body, ensure_ascii=False).encode("utf-8")

        self._adapters.build_extraction_provider = lambda: LLMInvoiceExtractionProvider(
            key="test-key", model="test-model", post=post, sleep=lambda _s: None)

    def result(self, text, confidence=0.9):
        payload = _as_contract({"text": text, "confidence": confidence})
        ProviderExtractionResult.model_validate(payload)
        return payload

    def test_a_standard_table_invoice_uses_rule_parser_first(self):
        text = "\n".join([
            "شماره فاکتور: F-100",
            "تاریخ: 1403/08/15",
            "مبلغ کل",
            "قیمت واحد",
            "واحد",
            "تعداد",
            "شرح کالا",
            "120000000",
            "1200000",
            "پاکت",
            "100",
            "سیمان تیپ 2 پاکتی",
            "جمع کل: 120000000 ریال",
        ])
        payload = self.result(text)
        values = {field["key"]: field["extractedValue"] for field in payload["fields"]}
        self.assertIn(RAW_TEXT_KEY, values)
        self.assertEqual("F-100", values["invoiceNumber"])
        self.assertEqual("120000000", values["totalAmount"])
        self.assertEqual(1, len(values["items"]))
        self.assertNotIn("extractionSource", values, "AI is not called when parser succeeds")

    def test_different_headers_fall_back_to_ai_when_enabled(self):
        self.enable_ai({
            "invoice": {"supplier": "فراز سازه پارس", "customer": None,
                        "invoice_number": "1403/1125", "invoice_date": "1403/08/15",
                        "currency": "IRR", "total_amount": "566500000"},
            "items": [{"description": "میلگرد آجدار 14", "quantity": "5000",
                       "unit": "کیلوگرم", "unit_price": "72000",
                       "total_price": "360000000"}],
            "confidence": 0.91,
            "warnings": [],
        })
        # Intentionally uses labels the old fixed header detector does not fully accept.
        payload = self.result("کالا\nمقدار\nفی\nجمع\nمیلگرد آجدار 14\n5000\n72000\n360000000")
        values = {field["key"]: field["extractedValue"] for field in payload["fields"]}
        self.assertEqual("openai", values["extractionSource"])
        self.assertEqual("1403/1125", values["invoiceNumber"])
        self.assertEqual("میلگرد آجدار 14", values["items"][0]["description"])

    def test_no_table_invoice_can_become_review_warning_draft(self):
        self.enable_ai({
            "invoice": {"supplier": "شرکت بتن نمونه", "customer": None,
                        "invoice_number": None, "invoice_date": "1403/08/20",
                        "currency": "IRR", "total_amount": "85000000"},
            "items": [],
            "confidence": 0.74,
            "warnings": ["No item table was visible."],
        })
        payload = self.result("پرداخت بابت بتن آماده پروژه. مبلغ کل 85000000 ریال")
        values = {field["key"]: field["extractedValue"] for field in payload["fields"]}
        self.assertEqual("85000000", values["totalAmount"])
        self.assertIn("aiWarnings", values)
        self.assertNotIn("items", values)

    def test_corrupted_ocr_with_low_ai_confidence_preserves_raw_text_only(self):
        self.enable_ai({"invoice": {"supplier": "حدس اشتباه"}, "items": [],
                        "confidence": 0.31, "warnings": ["OCR text is corrupted."]})
        payload = self.result("سـمـن ؟؟ ۱۲abc مبلغ x")
        values = {field["key"]: field["extractedValue"] for field in payload["fields"]}
        self.assertIn(RAW_TEXT_KEY, values)
        self.assertIn("aiWarnings", values)
        self.assertNotIn("supplierName", values)

    def test_manual_draft_is_allowed_when_ai_is_disabled_and_no_lines_are_read(self):
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "false"
        payload = self.result("رسید دستی خوانا نیست. کاربر بعداً خطوط را وارد می‌کند.")
        self.assertEqual([RAW_TEXT_KEY, "validationStatus", "parserWarnings"], keys(payload))

    def test_ai_disabled_fallback_never_calls_the_llm(self):
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "false"
        os.environ["FINANCE_AI_PROVIDER"] = "openai"
        os.environ["FINANCE_AI_API_KEY"] = "test-key"
        payload = self.result("کالا\nمقدار\nفی\nآجر\n10\n100")
        self.assertNotIn("extractionSource", keys(payload))

    def test_ai_response_missing_fields_uses_null_semantics_without_invention(self):
        candidate = parse_candidate({"invoice": {"supplier": None}, "items": [],
                                     "confidence": 0.88, "warnings": []})
        self.assertIsNone(candidate.invoice["supplier"])
        self.assertEqual([], candidate.items)

    def test_ai_invalid_json_is_reported_as_provider_response_error(self):
        body = {"choices": [{"message": {"content": "not json"}}]}

        def post(*_a):
            return 200, json.dumps(body).encode("utf-8")

        provider = LLMInvoiceExtractionProvider(key="test-key", model="test", post=post)
        with self.assertRaises(ExtractionProviderResponseInvalid):
            provider.extract_invoice("جمع کل 1000")


ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"


class _Auth:
    async def current(self, _request):
        return AuthContext(
            user_id=ACTOR,
            organization_id=ORG,
            project_id=PROJECT,
            organization_role="finance_manager",
            project_role="manager",
            permission_codes=("finance.view", "finance.manage_invoice"),
            timezone="Asia/Tehran",
        )


class _Scope:
    async def require_organization(self, _context, organization_id):
        if str(organization_id) != str(ORG):
            raise PermissionError("organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if str(organization_id) != str(ORG) or project_id != PROJECT:
            raise PermissionError("project denied")


class _Permission:
    async def require(self, context, permission):
        if permission not in context.permission_codes:
            raise PermissionError("permission denied")


class _AttachmentService:
    def __init__(self):
        self.file = None

    async def upload(self, scope, logical_type, original_name, mime_type, content):
        self.file = FinanceAttachment(
            file_id=uuid4(),
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            logical_type=logical_type,
            original_name_safe=original_name,
            stored_name="stored-%s" % original_name,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256="0" * 64,
            uploaded_by=scope.actor_user_id,
            uploaded_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
            processing_status="ready",
        )
        return self.file


class _ExtractionService:
    def __init__(self, attachments):
        self.attachments = attachments
        self.draft = None

    async def start(self, scope, file_id, hints):
        assert self.attachments.file.file_id == file_id
        fields = [
            ExtractionField(RAW_TEXT_KEY, "جمع کل 1000 ریال", None, 0.9),
            ExtractionField("totalAmount", "1000", None, 0.9),
            ExtractionField("extractionSource", "rule-parser", None, 1.0),
        ]
        self.draft = ExtractionDraft(
            draft_id=uuid4(),
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            file=self.attachments.file,
            version=1,
            review_status="awaitingReview",
            invoice_status="draft",
            provider_adapter="paddleocr-local",
            fields=fields,
            submitted_by=scope.actor_user_id,
            created_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
            financial_effect_irr=Decimal(0),
        )
        return self.draft

    async def get(self, _scope, draft_id):
        assert self.draft.draft_id == draft_id
        return self.draft


class SwaggerExtractionRouteTests(unittest.TestCase):
    def test_upload_extract_get_returns_reviewable_draft_without_financial_effect(self):
        app = create_app()
        attachments = _AttachmentService()
        app.state.auth_context_provider = _Auth()
        app.state.scope_authorizer = _Scope()
        app.state.permission_authorizer = _Permission()
        app.state.finance_attachment_service = attachments
        app.state.finance_extraction_service = _ExtractionService(attachments)

        with TestClient(app) as api:
            upload = api.post(
                f"/api/projects/{PROJECT}/finance/files",
                data={"logicalType": "invoice_image"},
                files={"file": ("invoice.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")},
            )
            self.assertEqual(201, upload.status_code, upload.text)
            file_id = upload.json()["fileId"]

            extraction = api.post(
                f"/api/projects/{PROJECT}/finance/files/{file_id}/extractions",
                json={"hints": {"locale": "fa-IR"}},
            )
            self.assertEqual(201, extraction.status_code, extraction.text)
            draft = extraction.json()
            self.assertEqual("awaitingReview", draft["reviewStatus"])
            self.assertEqual("draft", draft["invoiceStatus"])
            self.assertEqual("0", draft["financialEffectIRR"])
            self.assertIn(RAW_TEXT_KEY, [field["key"] for field in draft["fields"]])

            fetched = api.get(f"/api/projects/{PROJECT}/finance/extractions/{draft['draftId']}")
            self.assertEqual(200, fetched.status_code, fetched.text)
            self.assertEqual(draft["draftId"], fetched.json()["draftId"])


if __name__ == "__main__":
    unittest.main()
