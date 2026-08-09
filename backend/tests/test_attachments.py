import sys
import unittest
import inspect
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.attachments import require_file_transition
from app.finance.schemas.attachments import AttachmentResponse
from app.finance.security.guards import FinanceScope
from app.finance.services.attachments import (
    AttachmentTooLarge, DuplicateAttachment, FinanceAttachmentService,
    UnsupportedAttachment, safe_filename, validate_file,
)
from app.finance.repositories.attachments import PsycopgAttachmentRepository
from app.finance.router import list_finance_files

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"content"
JPEG = b"\xff\xd8\xff" + b"content"
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"content"
MP3 = b"ID3" + b"content"
M4A = b"\x00\x00\x00\x18ftypM4A " + b"content"
WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"content"
OGG = b"OggS" + b"content"


class FakeStorage:
    def __init__(self): self.puts = []
    async def put(self, metadata, content):
        self.puts.append((metadata, content)); return f"private/{metadata.stored_name}"


class FakeAttachmentRepo:
    def __init__(self): self.value = None; self.accesses = 0
    async def get_by_hash(self, _scope, _digest): return self.value
    async def create(self, _scope, value): self.value = value; return value
    async def get(self, scope, file_id):
        if self.value is None or self.value.file_id != file_id or self.value.organization_id != scope.organization_id or self.value.project_id != scope.project_id: return None
        return self.value
    async def record_access(self, _scope, _file_id, _audit_id, _at): self.accesses += 1
    async def transition(self, _scope, value, target):
        from dataclasses import replace
        self.value = replace(value, processing_status=target); return self.value
    async def list(self, scope, page, page_size, logical_type=None, file_category=None, processing_status=None, uploader_id=None):
        values = [] if self.value is None else [self.value]
        values = [item for item in values if item.organization_id == scope.organization_id and item.project_id == scope.project_id]
        if logical_type: values = [item for item in values if item.logical_type == logical_type]
        if file_category: values = [item for item in values if item.logical_type == ("invoice_image" if file_category == "image" else "invoice_voice")]
        if processing_status: values = [item for item in values if item.processing_status == processing_status]
        if uploader_id: values = [item for item in values if item.uploaded_by == uploader_id]
        return values[(page-1)*page_size:page*page_size], len(values)


class AttachmentValidationTests(unittest.TestCase):
    def test_safe_name_removes_paths_and_control_characters(self):
        self.assertEqual("evil_name.png", safe_filename("../../evil\x00name.png"))

    def test_extension_mime_and_magic_must_all_match(self):
        self.assertEqual(("image/png", "png"), validate_file("invoice_image", "bill.png", "image/png", PNG))
        for name, mime, content in (("bill.svg", "image/svg+xml", b"<svg>"), ("bill.jpg", "image/jpeg", PNG), ("bill.png", "text/html", PNG)):
            with self.subTest(name=name), self.assertRaises(UnsupportedAttachment): validate_file("invoice_image", name, mime, content)

    def test_all_prd_image_and_voice_formats_are_accepted(self):
        cases = (
            ("invoice_image", "bill.jpg", "image/jpeg", JPEG),
            ("invoice_image", "bill.png", "image/png", PNG),
            ("invoice_image", "bill.webp", "image/webp", WEBP),
            ("invoice_voice", "bill.mp3", "audio/mpeg", MP3),
            ("invoice_voice", "bill.m4a", "audio/mp4", M4A),
            ("invoice_voice", "bill.wav", "audio/wav", WAV),
            ("invoice_voice", "bill.ogg", "audio/ogg", OGG),
        )
        for logical_type,name,mime,content in cases:
            with self.subTest(name=name): self.assertEqual(mime,validate_file(logical_type,name,mime,content)[0])

    def test_fixed_image_limit_and_processing_transitions(self):
        with self.assertRaises(AttachmentTooLarge): validate_file("invoice_image", "bill.png", "image/png", b"x" * (10 * 1024 * 1024 + 1))
        for current, target in (("uploaded", "processing"), ("processing", "ready"), ("processing", "failed"), ("failed", "processing")): require_file_transition(current, target)
        with self.assertRaises(ValueError): require_file_transition("ready", "processing")

    def test_fixed_voice_limit_and_invalid_magic(self):
        with self.assertRaises(AttachmentTooLarge): validate_file("invoice_voice", "bill.mp3", "audio/mpeg", b"x" * (25 * 1024 * 1024 + 1))
        with self.assertRaises(UnsupportedAttachment): validate_file("invoice_voice", "bill.mp3", "audio/mpeg", b"not audio")


class AttachmentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_stores_private_bytes_and_returns_kit_metadata(self):
        repo, storage = FakeAttachmentRepo(), FakeStorage()
        service = FinanceAttachmentService(repo, storage, id_factory=lambda: FILE_ID, clock=lambda: NOW)
        value = await service.upload(FinanceScope(ORG, "p1", ACTOR), "invoice_image", "../bill.png", "image/png", PNG)
        payload = AttachmentResponse.from_domain(value).model_dump(by_alias=True, mode="json")
        self.assertEqual(("bill.png", "uploaded", len(PNG)), (payload["originalNameSafe"], payload["processingStatus"], payload["sizeBytes"]))
        self.assertEqual(PNG, storage.puts[0][1]); self.assertNotIn("storageKey", payload)

    async def test_duplicate_hash_is_blocked_before_second_storage_write(self):
        repo, storage = FakeAttachmentRepo(), FakeStorage(); service = FinanceAttachmentService(repo, storage, id_factory=lambda: FILE_ID, clock=lambda: NOW); scope = FinanceScope(ORG, "p1", ACTOR)
        await service.upload(scope, "invoice_image", "bill.png", "image/png", PNG)
        with self.assertRaises(DuplicateAttachment): await service.upload(scope, "invoice_image", "copy.png", "image/png", PNG)
        self.assertEqual(1, len(storage.puts))

    async def test_cross_scope_file_is_hidden_and_authorized_metadata_access_is_audited(self):
        repo, storage = FakeAttachmentRepo(), FakeStorage(); service = FinanceAttachmentService(repo, storage, id_factory=lambda: FILE_ID, clock=lambda: NOW)
        await service.upload(FinanceScope(ORG, "p1", ACTOR), "invoice_image", "bill.png", "image/png", PNG)
        with self.assertRaises(Exception): await service.get(FinanceScope(ORG, "p2", ACTOR), FILE_ID)
        await service.get(FinanceScope(ORG, "p1", ACTOR), FILE_ID)
        self.assertEqual(1, repo.accesses)

    async def test_list_is_scoped_filterable_and_does_not_audit_browsing(self):
        repo, storage = FakeAttachmentRepo(), FakeStorage(); service = FinanceAttachmentService(repo, storage, id_factory=lambda: FILE_ID, clock=lambda: NOW)
        scope=FinanceScope(ORG,"p1",ACTOR)
        await service.upload(scope,"invoice_image","bill.png","image/png",PNG)
        items,total=await service.list(scope,1,50,file_category="image",processing_status="uploaded",uploader_id=ACTOR)
        self.assertEqual((1,FILE_ID,0),(total,items[0].file_id,repo.accesses))
        self.assertEqual(([],0),await service.list(FinanceScope(ORG,"p2",ACTOR),1,50))


class AttachmentRepositoryContractTests(unittest.TestCase):
    def test_list_applies_scope_filters_order_and_database_pagination(self):
        source=inspect.getsource(PsycopgAttachmentRepository.list)
        for fragment in ("organization_id=%s","project_id=%s","deleted_at IS NULL","COUNT(*)","ORDER BY uploaded_at DESC,id DESC","LIMIT %s OFFSET %s"):
            self.assertIn(fragment,source)

    def test_list_endpoint_uses_view_permission_and_bounded_query_contract(self):
        source=inspect.getsource(list_finance_files)
        self.assertIn('"finance.view"',source)
        route=next(route for route in list_finance_files.__globals__["router"].routes
            if route.path.endswith("/files") and "GET" in route.methods)
        parameters=route.dependant.query_params
        constraints={item.name:(item.field_info.default,item.field_info.metadata) for item in parameters}
        self.assertEqual(1,constraints["page"][0])
        self.assertEqual(50,constraints["pageSize"][0])

    def test_public_attachment_contract_never_exposes_storage_reference(self):
        fields=set(AttachmentResponse.model_json_schema(by_alias=True)["properties"])
        self.assertFalse({"storageKey","storagePath","storedPath"} & fields)
