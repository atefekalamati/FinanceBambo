import sys
import unittest
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

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"content"


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


class AttachmentValidationTests(unittest.TestCase):
    def test_safe_name_removes_paths_and_control_characters(self):
        self.assertEqual("evil_name.png", safe_filename("../../evil\x00name.png"))

    def test_extension_mime_and_magic_must_all_match(self):
        self.assertEqual(("image/png", "png"), validate_file("invoice_image", "bill.png", "image/png", PNG))
        for name, mime, content in (("bill.svg", "image/svg+xml", b"<svg>"), ("bill.jpg", "image/jpeg", PNG), ("bill.png", "text/html", PNG)):
            with self.subTest(name=name), self.assertRaises(UnsupportedAttachment): validate_file("invoice_image", name, mime, content)

    def test_fixed_image_limit_and_processing_transitions(self):
        with self.assertRaises(AttachmentTooLarge): validate_file("invoice_image", "bill.png", "image/png", b"x" * (10 * 1024 * 1024 + 1))
        for current, target in (("uploaded", "processing"), ("processing", "ready"), ("processing", "failed"), ("failed", "processing")): require_file_transition(current, target)
        with self.assertRaises(ValueError): require_file_transition("ready", "processing")


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
