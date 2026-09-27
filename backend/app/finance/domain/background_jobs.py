# -*- coding: utf-8 -*-
"""The vocabulary of a durable background job, stated once.

A job is DATA -- a kind and a payload of ids and options -- never a callable. The route
that accepts the work writes a row and answers; a worker reads the row later, possibly in
another process after a restart, and rebuilds the call from the payload. That is the
whole difference between this and a callback in the web worker, which dies with it.

STATES
    queued   waiting; `available_at` says from when
    running  claimed by a worker, until `lease_until`
    done     finished; nothing more will happen to it
    failed   gave up, after `max_attempts` tries or on a refusal that a retry cannot fix

A `running` job whose lease has passed was claimed by a worker that did not finish -- a
crash, a deploy -- and is queued again by the next worker that looks. That is what makes
the queue survive the process.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
STATUSES = (QUEUED, RUNNING, DONE, FAILED)

#: The one kind today: read an invoice file. Others register a handler under their name.
KIND_EXTRACTION = "extraction"

#: How long a claim holds before another worker may take the job back. Longer than any
#: honest run -- a voice transcription measured at forty seconds -- and short enough that
#: a file does not sit «در حال پردازش» for an afternoon after a crash.
DEFAULT_LEASE = timedelta(minutes=5)

#: How many times a job is tried before it is given up on.
DEFAULT_MAX_ATTEMPTS = 3

#: How long a failed attempt waits before the next one.
RETRY_DELAY = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """What to enqueue: the kind, the scope it runs under, and ids and options only."""

    kind: str
    organization_id: UUID
    project_id: str
    payload: dict = field(default_factory=dict)
    created_by: UUID | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


@dataclass(frozen=True, slots=True)
class JobScope:
    """The scope a job runs under, rebuilt from its row. Shaped like FinanceScope, which
    every service reads, so a service cannot tell a worker's call from a request's."""

    organization_id: UUID
    project_id: str
    actor_user_id: UUID | None = None
    locale: str = "fa"
    organization_role: str | None = None
    permission_codes: tuple = ()


class JobRefused(Exception):
    """A job the worker will not retry: the refusal names why."""
