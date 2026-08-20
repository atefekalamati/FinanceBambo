from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, model_validator

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
    # totalItems is the canonical name across Finance list envelopes; totalCount is kept
    # so existing clients keep working and is mirrored from it.
    total_items: int | None = None

    @model_validator(mode="after")
    def mirror_total(self):
        if self.total_items is None:
            object.__setattr__(self, "total_items", self.total_count)
        return self
