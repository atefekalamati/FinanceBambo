import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePath
from uuid import uuid4

from ..domain.attachments import (
    DuplicateAttachment,
    FinanceAttachment,
    require_file_transition,
)
from ..domain.errors import FinanceDomainError
from ..domain.resources import FinanceRecordNotFound


IMAGE_LIMIT = 10 * 1024 * 1024
VOICE_LIMIT = 25 * 1024 * 1024
ALLOWED = {
    "invoice_image": {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    },
    "invoice_voice": {
        "mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav", "ogg": "audio/ogg",
    },
}


class AttachmentValidationError(FinanceDomainError):
    status = 422
    code = "VALIDATION_ERROR"


class AttachmentTooLarge(FinanceDomainError):
    status = 413
    code = "FILE_TOO_LARGE"


class UnsupportedAttachment(FinanceDomainError):
    status = 415
    code = "UNSUPPORTED_MEDIA_TYPE"


class AttachmentStorageUnavailable(FinanceDomainError):
    status = 503
    code = "FINANCE_FILES_UNAVAILABLE"


def safe_filename(name: str) -> str:
    leaf = re.split(r"[\\/]", name)[-1]
    clean = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", leaf).strip(" .")
    return clean[:120] or "upload.bin"


def detect_file(content: bytes, logical_type: str) -> tuple[str, str]:
    if logical_type == "invoice_image":
        if content.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png", "png"
        if content.startswith(b"\xff\xd8\xff"): return "image/jpeg", "jpg"
        if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP": return "image/webp", "webp"
    elif logical_type == "invoice_voice":
        if content.startswith(b"OggS"): return "audio/ogg", "ogg"
        if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WAVE": return "audio/wav", "wav"
        if content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0): return "audio/mpeg", "mp3"
        if len(content) >= 12 and content[4:8] == b"ftyp": return "audio/mp4", "m4a"
    raise UnsupportedAttachment("file bytes do not match the selected logical type")


def validate_file(logical_type: str, original_name: str, declared_mime: str, content: bytes) -> tuple[str, str]:
    if logical_type not in ALLOWED: raise AttachmentValidationError("logical type must be invoice_image or invoice_voice")
    if not content: raise AttachmentValidationError("file is empty")
    limit = IMAGE_LIMIT if logical_type == "invoice_image" else VOICE_LIMIT
    if len(content) > limit: raise AttachmentTooLarge("file exceeds the MVP product limit")
    extension = PurePath(safe_filename(original_name)).suffix.lower().lstrip(".")
    if extension not in ALLOWED[logical_type]: raise UnsupportedAttachment("file extension is not allowed")
    detected_mime, stored_extension = detect_file(content, logical_type)
    if ALLOWED[logical_type][extension] != detected_mime or declared_mime != detected_mime:
        raise UnsupportedAttachment("extension, declared MIME, and file bytes must match")
    return detected_mime, stored_extension


def storage_name(value) -> str:
    """The key this attachment was actually PUT under.

    `upload` writes the file under `stored_name` -- `{file_id}.{extension}` -- and keeps
    whatever key the storage returned in `storage_key`. Reading it back by `file_id` alone
    asks for a name with no extension, which nothing was ever written to, so every
    retrieval raised FileNotFoundError: the preview endpoint answered 500, and the
    extraction service caught the same error in its broad `except Exception` and reported
    "extraction provider is unavailable" -- blaming a provider it had not reached.

    `storage_key` first, because it is what the storage itself answered with. `stored_name`
    is the fallback for a row written before that column was populated, and `file_id` the
    last resort so a storage that really does key by id still works.
    """
    return str(getattr(value, "storage_key", None)
               or getattr(value, "stored_name", None)
               or value.file_id)


class FinanceAttachmentService:
    def __init__(self, repository, storage, id_factory=uuid4, clock=lambda: datetime.now(timezone.utc)):
        self.repo, self.storage, self.ids, self.clock = repository, storage, id_factory, clock

    async def upload(self, scope, logical_type, original_name, declared_mime, content):
        if scope.actor_user_id is None: raise PermissionError("actor required")
        mime, extension = validate_file(logical_type, original_name, declared_mime, content)
        digest = hashlib.sha256(content).hexdigest()
        if await self.repo.get_by_hash(scope, digest) is not None: raise DuplicateAttachment("identical file already exists")
        file_id = self.ids()
        value = FinanceAttachment(file_id, scope.organization_id, scope.project_id, logical_type,
            safe_filename(original_name), f"{file_id}.{extension}", mime, len(content), digest,
            scope.actor_user_id, self.clock())
        try:
            stored = await self.storage.put(value, content)
        except Exception as error:
            raise AttachmentStorageUnavailable("file storage is unavailable") from error
        storage_key = stored if isinstance(stored, str) else stored.storage_key
        value = replace(value, storage_key=storage_key)
        return await self.repo.create(scope, value)

    async def get(self, scope, file_id):
        value = await self.repo.get(scope, file_id)
        if value is None: raise FinanceRecordNotFound("file not found")
        await self.repo.record_access(scope, value.file_id, self.ids(), self.clock())
        return value

    async def list(self, scope, page=1, page_size=50, logical_type=None,
                   file_category=None, processing_status=None, uploader_id=None):
        return await self.repo.list(scope, page, page_size, logical_type,
            file_category, processing_status, uploader_id)

    async def content(self, scope, file_id):
        value = await self.get(scope, file_id)
        try:
            stored = await self.storage.get(str(scope.organization_id), scope.project_id,
                                            storage_name(value))
        except FileNotFoundError as error:
            raise FinanceRecordNotFound("file content was not found") from error
        except Exception as error:
            raise AttachmentStorageUnavailable("file storage is unavailable") from error
        content = stored if isinstance(stored,(bytes,bytearray,memoryview)) else getattr(stored,"content",None)
        if not isinstance(content,(bytes,bytearray,memoryview)):
            raise AttachmentStorageUnavailable("file content is unavailable")
        return value, content

    async def transition(self, scope, file_id, target):
        value = await self.repo.get(scope, file_id)
        if value is None: raise FinanceRecordNotFound("file not found")
        require_file_transition(value.processing_status, target)
        return await self.repo.transition(scope, value, target)
