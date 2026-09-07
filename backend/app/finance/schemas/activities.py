"""Project activity API DTOs consumed through host/progress adapters."""

from decimal import Decimal
from typing import Literal

from .base import ApiModel
from pydantic import Field, field_serializer, field_validator


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
    #: Additive and optional: the schedule's own cost for this task, in rials. It is NOT a
    #: Finance price and NOT an item cost -- a Finance price lives in `price_versions` and
    #: is entered by a person. A provider that reads no schedule leaves it None.
    mpp_task_cost_irr: Decimal | None = None

    @field_serializer("mpp_task_cost_irr")
    def serialize_cost(self, value: Decimal | None):
        # As a string, like every other money field: a large rial figure sent as a JSON
        # number is rounded by the reader before anyone can object.
        return None if value is None else format(value, "f")


class ActivityListResponse(ApiModel):
    items: list[ActivityResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
