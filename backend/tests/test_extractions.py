import sys
import inspect
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.attachments import FinanceAttachment
from app.finance.adapters.ports import InvoiceImageExtractor, InvoiceVoiceExtractor
from app.finance.schemas.extractions import ExtractionDraftResponse
from app.finance.security.guards import FinanceScope
from app.finance.services.extractions import AIExtractionContentError, ExtractionForbidden, FinanceExtractionService

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
DRAFT_ID = UUID("55555555-5555-4555-8555-555555555555")
NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def attachment(logical_type="invoice_image", status="uploaded"):
    return FinanceAttachment(FILE_ID, ORG, "p1", logical_type, "bill.png", f"{FILE_ID}.png",
        "image/png", 10, "a" * 64, ACTOR, NOW, status, "private/key")


class FakeAttachments:
    def __init__(self, value): self.value=value; self.transitions=[]
    async def get(self, scope, file_id):
        if file_id != self.value.file_id or scope.project_id != self.value.project_id: return None
        return self.value
    async def transition(self, _scope, value, target):
        self.transitions.append((value.processing_status,target));self.value=replace(value,processing_status=target);return self.value


class FakeStorage:
    def __init__(self): self.calls=[]
    async def get(self, organization_id, project_id, file_id):
        self.calls.append((organization_id,project_id,file_id));return b"private-content"


class FakeExtractor:
    def __init__(self,name="approved-adapter",result=None):self.adapter_name=name;self.result=result or {"fields":[{"key":"invoiceNumber","extractedValue":"N-1","confirmedValue":None,"confidence":0.92,"editedByUser":False}]};self.calls=[]
    async def extract(self,file,hints):self.calls.append((file,hints));return self.result


class FakeExtractions:
    def __init__(self):self.value=None
    async def create_next(self,_scope,value):self.value=replace(value,version=1 if self.value is None else self.value.version+1);return self.value
    async def get(self,scope,draft_id):
        return self.value if self.value and self.value.draft_id==draft_id and self.value.project_id==scope.project_id else None


class ExtractionTests(unittest.IsolatedAsyncioTestCase):
    def test_image_and_voice_are_distinct_provider_neutral_ports(self):
        self.assertIsNot(InvoiceImageExtractor, InvoiceVoiceExtractor)
        self.assertEqual(("self","file","hints"),tuple(inspect.signature(InvoiceImageExtractor.extract).parameters))
        self.assertEqual(("self","file","hints"),tuple(inspect.signature(InvoiceVoiceExtractor.extract).parameters))
    def service(self,file_value=None,image=None,voice=None):
        self.repo=FakeExtractions();self.attachments=FakeAttachments(file_value or attachment());self.storage=FakeStorage();self.image=image or FakeExtractor("image-adapter");self.voice=voice or FakeExtractor("voice-adapter")
        return FinanceExtractionService(self.repo,self.attachments,self.storage,self.image,self.voice,id_factory=lambda:DRAFT_ID,clock=lambda:NOW)

    async def test_image_pipeline_creates_zero_effect_versioned_review_draft(self):
        draft=await self.service().start(FinanceScope(ORG,"p1",ACTOR),FILE_ID,{"locale":"fa-IR"})
        self.assertEqual([("uploaded","processing"),("processing","ready")],self.attachments.transitions)
        self.assertEqual(("awaitingReview","draft","image-adapter",0),(draft.review_status,draft.invoice_status,draft.provider_adapter,draft.financial_effect_irr))
        payload=ExtractionDraftResponse.from_domain(draft).model_dump(by_alias=True,mode="json")
        self.assertEqual("0",payload["financialEffectIRR"]);self.assertNotIn("financialEffectIrr",payload);self.assertEqual(0.92,payload["fields"][0]["confidence"])

    async def test_voice_uses_independent_adapter_and_scoped_storage(self):
        draft=await self.service(attachment("invoice_voice")).start(FinanceScope(ORG,"p1",ACTOR),FILE_ID)
        self.assertEqual("voice-adapter",draft.provider_adapter);self.assertEqual(1,len(self.voice.calls))
        self.assertEqual((str(ORG),"p1",str(FILE_ID)),self.storage.calls[0])

    async def test_invalid_provider_contract_marks_initial_file_failed(self):
        bad=FakeExtractor(result={"fields":[{"key":"amount","confidence":2}]})
        with self.assertRaises(AIExtractionContentError):await self.service(image=bad).start(FinanceScope(ORG,"p1",ACTOR),FILE_ID)
        self.assertEqual("failed",self.attachments.value.processing_status);self.assertIsNone(self.repo.value)

    async def test_retry_keeps_ready_file_lifecycle_independent_and_requires_uploader(self):
        service=self.service(attachment(status="ready"));current=await service.start(FinanceScope(ORG,"p1",ACTOR),FILE_ID);self.assertEqual([],self.attachments.transitions)
        with self.assertRaises(ExtractionForbidden):await service.retry(FinanceScope(ORG,"p1",OTHER),current.draft_id)
