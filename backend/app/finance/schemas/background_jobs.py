from datetime import datetime
from typing import Literal

from .base import ApiModel


class BackgroundJobResponse(ApiModel):
    """One durable job, as the queue holds it. What a client polls to learn why a file
    is still «در حال پردازش», or why it ended `failed`."""

    job_id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    attempts: int
    max_attempts: int
    #: The last failure the worker recorded, in the words the run raised. Null while it
    #: is still to run and after it succeeded.
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
