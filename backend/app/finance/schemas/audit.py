from datetime import datetime
from typing import Any
from uuid import UUID

from .base import ApiModel


class AuditEventResponse(ApiModel):
    id:UUID
    organization_id:UUID
    project_id:str
    actor_user_id:UUID
    action:str
    entity_type:str
    entity_id:UUID
    reason:str|None=None
    before_values:dict[str,Any]|None=None
    after_values:dict[str,Any]|None=None
    occurred_at:datetime


class AuditEventListResponse(ApiModel):
    """Paged envelope so a client filtering by date cannot mistake an unfetched page for an empty history."""

    items:list[AuditEventResponse]
    page:int
    page_size:int
    total_items:int
    total_pages:int
