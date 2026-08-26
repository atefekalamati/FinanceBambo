"""report snapshot payload and pinned resources

snapshot_payload and resource_version_ids on report_snapshots.

The three-step order is load-bearing and is preserved exactly: add the columns nullable,
backfill every existing row, and only then set NOT NULL. Creating them NOT NULL up front
would fail on any database that already holds issued reports.

Converted from migrations/0004_report_snapshot_payload.up.sql and .down.sql, which Git history keeps.
The SQL is embedded unchanged apart from the outer BEGIN/COMMIT: Alembic owns the
transaction boundary, and opening a second one inside it is an error.

The SQL travels as a `DDL` construct rather than a plain string. `op.execute` on a string
parses it for `:name` bind parameters, which would misread PostgreSQL cast syntax and
dollar-quoted function bodies; `DDL` skips that parsing and passes the whole batch through
as it stood in the file. It also works in offline mode (`alembic upgrade head --sql`), where
the mock connection has no `exec_driver_sql` to call.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
from sqlalchemy import DDL

revision = "0004"
down_revision = '0003'
branch_labels = None
depends_on = None


UPGRADE_SQL = """\
ALTER TABLE report_snapshots
    ADD COLUMN IF NOT EXISTS snapshot_payload jsonb,
    ADD COLUMN IF NOT EXISTS resource_version_ids jsonb;

UPDATE report_snapshots
SET snapshot_payload = jsonb_build_object(
    'reportingDate', reporting_date,
    'calculatedMetrics', calculated_metrics
)
WHERE snapshot_payload IS NULL;

UPDATE report_snapshots
SET resource_version_ids = '[]'::jsonb
WHERE resource_version_ids IS NULL;

ALTER TABLE report_snapshots
    ALTER COLUMN snapshot_payload SET NOT NULL,
    ALTER COLUMN resource_version_ids SET NOT NULL;
"""


DOWNGRADE_SQL = """\
ALTER TABLE report_snapshots
    DROP COLUMN IF EXISTS snapshot_payload,
    DROP COLUMN IF EXISTS resource_version_ids;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
