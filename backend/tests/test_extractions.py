import sys
import inspect
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.attachments import FinanceAttachment
from app.finance.domain.invoices import Invoice
from app.finance.adapters.ports import InvoiceImageExtractor, InvoiceVoiceExtractor
from app.finance.schemas.extractions import ExtractionConfirm, ExtractionDraftResponse
from app.finance.security.guards import FinanceScope
from app.finance.services.extractions import AIExtractionContentError, ExtractionConflict, ExtractionForbidden, FinanceExtractionService

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
OTHER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
DRAFT_ID = UUID("55555555-5555-4555-8555-555555555555")
INVOICE_ID = UUID("66666666-6666-4666-8666-666666666666")
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
    async def confirm_with_invoice(self,_scope,draft,confirmed_fields,invoice,_extraction_audit,_invoice_audit,at):
        self.value=replace(draft,review_status="accepted",invoice_status="confirmed",fields=confirmed_fields,
            file=replace(draft.file,invoice_id=invoice.id),confirmed_by=ACTOR,confirmed_at=at)
        self.invoices.store(invoice);return invoice
    async def get_linked_invoice_id(self,_scope,attachment_id):
        return self.value.file.invoice_id if self.value and self.value.file.file_id==attachment_id else None


class FakeInvoices:
    def __init__(self):self.by_id={};self.by_key={}
    def store(self,value):self.by_id[value.id]=value;self.by_key[value.idempotency_key]=value
    async def get(self,_scope,invoice_id):return self.by_id[invoice_id]
    async def get_by_idempotency(self,_scope,key):return self.by_key.get(key)
    async def prepare_extracted(self,scope,command,source,key,at):
        return Invoice(INVOICE_ID,scope.organization_id,scope.project_id,command.invoice_number,command.invoice_date,
            command.vendor_name,command.description,source,"confirmed",command.discount_irr,command.tax_irr,
            command.shipping_irr,command.other_costs_irr,Decimal(100),key,1,scope.actor_user_id,
            scope.actor_user_id,at,at,[])


class ExtractionTests(unittest.IsolatedAsyncioTestCase):
    def test_image_and_voice_are_distinct_provider_neutral_ports(self):
        self.assertIsNot(InvoiceImageExtractor, InvoiceVoiceExtractor)
        self.assertEqual(("self","file","hints"),tuple(inspect.signature(InvoiceImageExtractor.extract).parameters))
        self.assertEqual(("self","file","hints"),tuple(inspect.signature(InvoiceVoiceExtractor.extract).parameters))

    def test_atomic_repository_records_both_review_and_invoice_audits(self):
        from app.finance.repositories.extractions import PsycopgExtractionRepository
        source=inspect.getsource(PsycopgExtractionRepository.confirm_with_invoice)
        self.assertIn("extraction.accepted",source);self.assertIn("invoice.confirmed",source)
    def service(self,file_value=None,image=None,voice=None):
        self.repo=FakeExtractions();self.attachments=FakeAttachments(file_value or attachment());self.storage=FakeStorage();self.image=image or FakeExtractor("image-adapter");self.voice=voice or FakeExtractor("voice-adapter")
        self.invoices=FakeInvoices();self.repo.invoices=self.invoices
        return FinanceExtractionService(self.repo,self.attachments,self.storage,self.image,self.voice,self.invoices,id_factory=lambda:DRAFT_ID,clock=lambda:NOW)

    @staticmethod
    def confirmation(key="confirm-ai-1",version=1,field_key="invoiceNumber"):
        return ExtractionConfirm(expectedVersion=version,idempotencyKey=key,
            fieldConfirmations=[{"key":field_key,"confirmedValue":"N-2"}],
            invoice={"invoiceDate":"2026-08-09","vendorName":"Vendor","lines":[{
                "resourceId":"77777777-7777-4777-8777-777777777777","unitPriceIrr":"100"}]})

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

    async def test_human_confirmation_atomically_accepts_fields_and_confirms_linked_invoice(self):
        service=self.service();scope=FinanceScope(ORG,"p1",ACTOR);draft=await service.start(scope,FILE_ID)
        invoice=await service.confirm(scope,draft.draft_id,self.confirmation())
        self.assertEqual(("image","confirmed",ACTOR),(invoice.source,invoice.status,invoice.confirmed_by))
        self.assertEqual(("accepted","confirmed",INVOICE_ID),(self.repo.value.review_status,self.repo.value.invoice_status,self.repo.value.file.invoice_id))
        field=self.repo.value.fields[0];self.assertEqual(("N-1","N-2",True),(field.extracted_value,field.confirmed_value,field.edited_by_user))

    async def test_confirmation_is_idempotent_and_rejects_competing_key(self):
        service=self.service();scope=FinanceScope(ORG,"p1",ACTOR);draft=await service.start(scope,FILE_ID);command=self.confirmation()
        first=await service.confirm(scope,draft.draft_id,command);second=await service.confirm(scope,draft.draft_id,command)
        self.assertIs(first,second)
        with self.assertRaises(ExtractionConflict):await service.confirm(scope,draft.draft_id,self.confirmation(key="other-key"))

    async def test_confirmation_rejects_unknown_field_stale_version_and_other_user(self):
        service=self.service();scope=FinanceScope(ORG,"p1",ACTOR);draft=await service.start(scope,FILE_ID)
        with self.assertRaises(AIExtractionContentError):await service.confirm(scope,draft.draft_id,self.confirmation(field_key="unknown"))
        with self.assertRaises(ExtractionConflict):await service.confirm(scope,draft.draft_id,self.confirmation(version=2))
        with self.assertRaises(ExtractionForbidden):await service.confirm(FinanceScope(ORG,"p1",OTHER),draft.draft_id,self.confirmation())
