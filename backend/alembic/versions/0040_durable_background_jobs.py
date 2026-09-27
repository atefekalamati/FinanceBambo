# -*- coding: utf-8 -*-
"""durable background jobs

Revision ID: 0040
Revises: 0039

Reading an invoice from an image or a recording takes seconds to a minute. The route
answers 202 at once and the work runs afterwards -- and until now "afterwards" meant a
callback inside the web process, which a restart, a crash or a deploy took with it: the
file stayed «در حال پردازش» forever and nobody could tell. The production composition
therefore refused the route outright (503 "durable extraction execution is not
configured"), which is the state the first site deployment is in.

This table IS the queue. A job is a row; `submit` writes it and the request returns; a
worker in the same process claims rows with `FOR UPDATE SKIP LOCKED`, runs them, and
records the outcome. A worker that dies mid-job leaves the row `running` past its lease,
and the next worker takes it back. No broker, no second service: the database the
module already depends on.

No row is written by this revision.
"""
from alembic import op
from sqlalchemy import DDL

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS finance_background_jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    -- What to do. The worker dispatches on it; an unknown kind fails the job rather
    -- than being guessed at.
    kind text NOT NULL CHECK (btrim(kind) <> ''),
    -- What to do it TO: ids and options only, never a callable. A row that could not be
    -- rebuilt after a restart would not be durable.
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    -- Not before this moment. A retry is scheduled a little later, not immediately.
    available_at timestamptz NOT NULL DEFAULT now(),
    -- The claim: who is running it and until when. A `running` row past its lease was
    -- claimed by a worker that never finished, and is fair game again.
    lease_until timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    -- The last failure, in the words the run raised. Never a path or a credential.
    error text,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_finance_background_jobs_claim
    ON finance_background_jobs (status, available_at);

CREATE INDEX IF NOT EXISTS ix_finance_background_jobs_scope
    ON finance_background_jobs (organization_id, project_id, created_at DESC);
"""

DOWNGRADE_SQL = """
DROP INDEX IF EXISTS ix_finance_background_jobs_scope;
DROP INDEX IF EXISTS ix_finance_background_jobs_claim;
DROP TABLE IF EXISTS finance_background_jobs;
"""


def upgrade():
    op.execute(DDL(UPGRADE_SQL))


def downgrade():
    op.execute(DDL(DOWNGRADE_SQL))
