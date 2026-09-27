# -*- coding: utf-8 -*-
"""Persistence for the durable job queue -- see domain/background_jobs.py.

CLAIMING is the one statement that matters. `FOR UPDATE SKIP LOCKED` hands each worker a
row no other worker holds, in one round trip, without a lock table: two workers asking at
once get two different jobs or one gets nothing, never the same job twice. The same
statement also takes back a `running` row whose lease has passed, so a job a dead worker
left behind is picked up by whichever worker looks next.
"""
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..domain.background_jobs import DEFAULT_LEASE, DONE, FAILED, QUEUED, RETRY_DELAY, RUNNING

_COLUMNS = ("id, organization_id, project_id, kind, payload, status, attempts, max_attempts, "
            "available_at, lease_until, started_at, finished_at, error, created_by, created_at")


class PsycopgBackgroundJobRepository:
    def __init__(self, db):
        self.db = db

    async def enqueue(self, spec):
        """One row, `queued`, available now. Returns it as stored."""
        job_id = uuid4()
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "INSERT INTO finance_background_jobs"
                " (id, organization_id, project_id, kind, payload, max_attempts, created_by)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING " + _COLUMNS,
                (job_id, spec.organization_id, spec.project_id, spec.kind, Jsonb(spec.payload),
                 spec.max_attempts, spec.created_by))
            return await c.fetchone()

    async def claim(self, worker, lease=DEFAULT_LEASE):
        """The next job this worker may run, marked `running` under its lease, or None.

        Eligible: `queued` and due, or `running` with an expired lease. Oldest first. The
        attempt is counted here, at the claim, so a run that dies before finishing still
        counts against `max_attempts` -- otherwise a job that crashes the worker would be
        retried forever.
        """
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as c:
                # DELIBERATELY ACROSS TENANTS: a worker serves every organization on
                # the host, so this is the one statement in the module that names no
                # single tenant. Everything the claim then does is scoped to the row's
                # own organization, and a handler runs under the scope stored on it.
                await c.execute(
                    "SELECT id, organization_id FROM finance_background_jobs"
                    " WHERE (status = %s AND available_at <= now())"
                    "    OR (status = %s AND lease_until < now())"
                    " ORDER BY available_at, created_at"
                    " LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (QUEUED, RUNNING))
                found = await c.fetchone()
                if found is None:
                    return None
                await c.execute(
                    "UPDATE finance_background_jobs"
                    " SET status = %s, attempts = attempts + 1, started_at = now(),"
                    "     lease_until = now() + %s, error = NULL"
                    " WHERE id = %s AND organization_id = %s RETURNING " + _COLUMNS,
                    (RUNNING, lease, found["id"], found["organization_id"]))
                return await c.fetchone()

    async def finish(self, job_id, organization_id, *, error=None, retry=False):
        """Record the outcome: done, queued again for a retry, or failed for good."""
        if error is None:
            status, available = DONE, "now()"
        elif retry:
            status, available = QUEUED, "now() + %s"
        else:
            status, available = FAILED, "now()"
        params = [status, error]
        if retry:
            params.append(RETRY_DELAY)
        params.extend([job_id, organization_id])
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "UPDATE finance_background_jobs"
                " SET status = %s, error = %s, lease_until = NULL,"
                "     finished_at = CASE WHEN %s IN ('done', 'failed') THEN now() END,"
                "     available_at = " + available +
                " WHERE id = %s AND organization_id = %s RETURNING " + _COLUMNS,
                [params[0], params[1], params[0]] + params[2:])
            return await c.fetchone()

    async def get(self, scope, job_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_background_jobs"
                " WHERE organization_id = %s AND project_id = %s AND id = %s",
                (scope.organization_id, scope.project_id, job_id))
            return await c.fetchone()

    async def latest_for_payload(self, scope, kind, key, value):
        """The newest job of `kind` whose payload's `key` is `value` -- a file's job."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_background_jobs"
                " WHERE organization_id = %s AND project_id = %s AND kind = %s"
                "   AND payload ->> %s = %s"
                " ORDER BY created_at DESC LIMIT 1",
                (scope.organization_id, scope.project_id, kind, key, str(value)))
            return await c.fetchone()
