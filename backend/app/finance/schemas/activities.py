"""Project activity API DTOs consumed through host/progress adapters."""

from typing import Literal

from .base import ApiModel
from pydantic import Field, field_validator


class ActivityCreate(ApiModel):
    title: str = Field(min_length=1)
    wbs_code: str | None = None
    parent_task_external_id: str | None = None

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip(): raise ValueError("title must not be blank")
        return value.strip()


class ActivityResponse(ApiModel):
    activity_external_id: str
    task_external_id: str | None = None
    title: str
    wbs_code: str | None = None
    status: Literal["active", "inactive"] = "active"


class ActivityListResponse(ApiModel):
    items: list[ActivityResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
