from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


FILE_TRANSITIONS = {
    "uploaded": {"processing"},
    "processing": {"ready", "failed"},
    "failed": {"processing"},
    "ready": set(),
}


def require_file_transition(current: str, target: str) -> None:
    if target not in FILE_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid file transition: {current} -> {target}")


@dataclass(frozen=True)
class FinanceAttachment:
    file_id: UUID
    organization_id: UUID
    project_id: str
    logical_type: str
    original_name_safe: str
    stored_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_by: UUID
    uploaded_at: datetime
    processing_status: str = "uploaded"
    storage_key: str | None = None
    invoice_id: UUID | None = None
