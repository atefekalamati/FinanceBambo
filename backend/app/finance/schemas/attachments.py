from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict

from .base import ApiModel


class AttachmentResponse(ApiModel):
    file_id: UUID
    organization_id: UUID
    project_id: str
    logical_type: Literal["invoice_image", "invoice_voice"]
    original_name_safe: str
    stored_name: str
    mime_type: Literal[
        "image/jpeg", "image/png", "image/webp",
        "audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg",
    ]
    size_bytes: int
    sha256: str
    uploaded_by: UUID
    uploaded_at: datetime
    processing_status: Literal["uploaded", "processing", "ready", "failed"]

    @classmethod
    def from_domain(cls, value):
        return cls(**{name: getattr(value, name) for name in cls.model_fields})


class AttachmentListResponse(ApiModel):
    model_config = ConfigDict(json_schema_extra={"examples":[{"items":[],"page":1,"pageSize":50,"totalCount":0,"totalPages":0}]})
    items: list[AttachmentResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int
