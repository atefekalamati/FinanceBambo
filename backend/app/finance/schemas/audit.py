from datetime import datetime
from typing import Any
from uuid import UUID

from .base import ApiModel


class AuditEventResponse(ApiModel):
    id:UUID
    organization_id:UUID
    project_id:str
    actor_user_id:UUID
    # What the host calls that actor, filled at the boundary and never stored. None whenever
    # the host has no directory or does not know this id; the reader then sees the id, which
    # is what it saw before. See `app.finance.domain.actors`.
    actor_user_name:str|None=None
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
