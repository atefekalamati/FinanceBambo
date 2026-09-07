"""Where a Finance record records which MPP row it came from

Revision ID: 0013
Revises: 0012

Finance can read a schedule and keep it (0011, 0012), but nothing yet turns those rows into
the financial records a report is built from -- the resources and the estimate lines. Doing
that needs one thing the schema does not have: somewhere to write WHICH row of the file a
Finance record came from, so that reading the same file twice recognises what it already
made instead of making it again.

WHY NOT THE COLUMNS THAT LOOK LIKE THEY WOULD DO
`finance_resources.external_resource_id` and `estimate_lines.assignment_external_id` are
the obvious candidates and both are traps, because on this database they already hold
something else. The legacy seed wrote MSP TASK uids into them, and those numbers overlap
the file's RESOURCE and ASSIGNMENT uids:

    MPP resource 157 is «آبپاش» -- a sprinkler
    external_resource_id "157" is MSP-T157 «ساخت و نصب وال پست دیوار» -- a wall post

Five of the file's sixty-eight resources collide that way, and five of its seven hundred
assignments do the same on the estimate side. Reusing those columns would either fail on
the existing partial unique index or, far worse, silently pair a sprinkler with a wall
post -- the exact accidental mapping this work exists to end. So the file's identifiers get
columns of their own, and the legacy columns keep their legacy meaning untouched.

WHAT THE UNIQUE INDEXES DECIDE
  * one Finance resource per MPP resource, per project -- scoped to the project and NOT to
    the source version, because «بتن ۴۰۰» in this month's file and in next month's is one
    financial item with one price history, not two.
  * one estimate line per MPP assignment, per project -- an assignment is exactly "this
    resource, on this activity", which is what an estimate line is. Re-reading an unchanged
    file therefore matches every line instead of duplicating it.

Both are PARTIAL: a Finance resource typed in by hand has no MPP identity, and many such
rows must be able to coexist. NULL means "not from a file", not "unknown file row".

`source_task_uid` on the estimate line is carried for corroboration only -- it lets a
re-sync notice that an assignment has moved to a different task, which is a change worth
seeing rather than silently absorbing. Nothing keys on it.

No column here holds a quantity, a price, a progress figure or a cost. This migration adds
identity and nothing else.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- The MPP resource this financial item was created from. NULL for anything not read from
-- a schedule, which is every resource entered by hand.
ALTER TABLE finance_resources ADD COLUMN source_resource_uid integer;

COMMENT ON COLUMN finance_resources.source_resource_uid IS
    'The MPP Resource UID this item came from, or NULL when it did not come from a file. '
    'NOT external_resource_id: that column holds a legacy value with a different meaning.';

-- One financial item per schedule resource, per project. Deliberately not scoped to the
-- source version: the same resource across two versions of a file is one item.
CREATE UNIQUE INDEX ux_finance_resources_source_resource
    ON finance_resources (organization_id, project_id, source_resource_uid)
    WHERE source_resource_uid IS NOT NULL AND deleted_at IS NULL;

-- The MPP assignment this estimate line was created from: "this resource, on this
-- activity", which is exactly what a line is.
ALTER TABLE estimate_lines
    ADD COLUMN source_assignment_uid integer,
    -- Carried for corroboration, never keyed on: it makes an assignment that has moved to
    -- another task visible instead of silently absorbed.
    ADD COLUMN source_task_uid integer;

COMMENT ON COLUMN estimate_lines.source_assignment_uid IS
    'The MPP Assignment UID this line came from, or NULL when the line was not read from a '
    'file. NOT assignment_external_id: that column holds a legacy value.';

CREATE UNIQUE INDEX ux_estimate_lines_source_assignment
    ON estimate_lines (organization_id, project_id, source_assignment_uid)
    WHERE source_assignment_uid IS NOT NULL AND deleted_at IS NULL;
"""


DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ux_estimate_lines_source_assignment;
ALTER TABLE estimate_lines
    DROP COLUMN source_task_uid,
    DROP COLUMN source_assignment_uid;

DROP INDEX IF EXISTS ux_finance_resources_source_resource;
ALTER TABLE finance_resources DROP COLUMN source_resource_uid;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
