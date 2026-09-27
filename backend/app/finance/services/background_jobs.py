# -*- coding: utf-8 -*-
"""The durable executor and the worker that drains it.

TWO HALVES

`DurableBackgroundExecutor.submit(spec)` is what the route calls: it writes the job and
returns. It is the `finance_background_executor` the composition root publishes, and the
async extraction route answers 202 only once it exists (or, on a development host, once
the ephemeral flag is set instead).

`BackgroundWorker` runs in the same process, on the event loop, and drains the queue: claim
one job, dispatch it by kind to a registered handler, record the outcome, repeat. It is
started by the composition root's lifespan and cancelled on shutdown. Several processes
may each run one; the claim statement keeps them from sharing a job.

WHAT A HANDLER PROMISES

A handler is `async (scope, payload) -> None`. It raises `JobRefused` for a failure a retry
cannot fix (the uploader is gone, the file was deleted) and anything else for one it might
(a model that would not load, a database that was away). The worker retries the second
kind up to `max_attempts` and fails the first at once. Whatever the handler does to its
OWN records -- moving a file to `failed`, say -- it does itself; the worker only records
the job.
"""
import asyncio
import logging
from datetime import timedelta
from inspect import isawaitable
from uuid import UUID

from ..domain.background_jobs import (DEFAULT_LEASE, JobRefused, JobScope, JobSpec,
                                      KIND_EXTRACTION)
from ..domain.errors import FinanceDomainError

LOG = logging.getLogger("finance.background")


class DurableBackgroundExecutor:
    """`submit(spec)`: the job is a row before this returns."""

    def __init__(self, repository):
        self.repository = repository

    async def submit(self, spec):
        row = await self.repository.enqueue(spec)
        LOG.info("job queued id=%s kind=%s project=%s", row["id"], spec.kind, spec.project_id)
        return row


def _scope_of(row):
    payload = row.get("payload") or {}
    actor = payload.get("actorUserId")
    return JobScope(organization_id=row["organization_id"], project_id=row["project_id"],
                    actor_user_id=UUID(actor) if actor else None,
                    locale=payload.get("locale") or "fa")


class BackgroundWorker:
    """Drains the queue. `run_once` for tests and for a cron; `run_forever` for a host."""

    def __init__(self, repository, handlers, *, name="worker", poll_interval=2.0,
                 lease=DEFAULT_LEASE):
        self.repository = repository
        self.handlers = dict(handlers)
        self.name = name
        self.poll_interval = poll_interval
        self.lease = lease if isinstance(lease, timedelta) else timedelta(seconds=lease)

    async def run_once(self):
        """Claim and run at most one job. Returns the finished row, or None when idle."""
        job = await self.repository.claim(self.name, self.lease)
        if job is None:
            return None
        handler = self.handlers.get(job["kind"])
        if handler is None:
            # Not retried: the code that could run it is not in this process, and will not
            # be in two minutes either.
            LOG.error("job %s: no handler for kind %r", job["id"], job["kind"])
            return await self.repository.finish(job["id"], job["organization_id"], error="no handler for kind %r" % job["kind"])
        try:
            result = handler(_scope_of(job), job.get("payload") or {})
            if isawaitable(result):
                await result
        except JobRefused as refused:
            LOG.warning("job %s refused: %s", job["id"], refused)
            return await self.repository.finish(job["id"], job["organization_id"], error=str(refused))
        except Exception as error:  # noqa: BLE001 -- the outcome is recorded, never lost
            exhausted = job["attempts"] >= job["max_attempts"]
            LOG.exception("job %s attempt %d/%d failed: %s", job["id"], job["attempts"],
                          job["max_attempts"], type(error).__name__)
            message = "%s: %s" % (type(error).__name__, error)
            return await self.repository.finish(job["id"], job["organization_id"], error=message[:2000], retry=not exhausted)
        LOG.info("job %s done", job["id"])
        return await self.repository.finish(job["id"], job["organization_id"])

    async def run_forever(self, stop=None):
        """Poll until cancelled (or `stop` is set). A failure in one tick never ends it."""
        while stop is None or not stop.is_set():
            try:
                busy = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 -- a broken database round trip is a log line
                LOG.exception("worker %s: tick failed", self.name)
                busy = None
            if busy is None:
                await asyncio.sleep(self.poll_interval)


def extraction_handler(extraction_service):
    """The handler for KIND_EXTRACTION: run `start` on the file named in the payload.

    `claimed=True`, because the route already moved the file to `processing` when it
    accepted the job; `force_new=True`, because the job exists precisely to make a new
    draft. `start` moves the file to `failed` itself on a provider failure and raises a
    FinanceDomainError -- which is reported as the job's error and NOT retried: the file
    is already `failed`, retryable by the person, and a second silent attempt would race
    them. Anything else (the database away, a storage backend down) is a retry.
    """
    async def run(scope, payload):
        attachment_id = UUID(payload["attachmentId"])
        try:
            await extraction_service.start(scope, attachment_id, payload.get("hints") or {},
                                           force_new=True, claimed=True)
        except FinanceDomainError as error:
            raise JobRefused("%s: %s" % (type(error).__name__, error)) from error
    return run


def extraction_job(scope, attachment_id, hints=None):
    """The spec the async route enqueues for one file."""
    return JobSpec(kind=KIND_EXTRACTION, organization_id=scope.organization_id,
                   project_id=scope.project_id, created_by=scope.actor_user_id,
                   payload={"attachmentId": str(attachment_id),
                            "actorUserId": str(scope.actor_user_id) if scope.actor_user_id else None,
                            "locale": getattr(scope, "locale", "fa"),
                            "hints": dict(hints or {})})


def default_handlers(extraction_service):
    return {KIND_EXTRACTION: extraction_handler(extraction_service)}
