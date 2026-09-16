"""an estimate line says whether the schedule accounts for it

Revision ID: 0030
Revises: 0029

WHAT WAS WRONG

`estimate_lines` had no way to say where a row came from. `source_assignment_uid` and
`source_task_uid` were nullable and nothing required either, so a row created through
`POST /estimate-lines` carried neither and was indistinguishable, in every query that
matters, from a row the MPP import wrote.

On the audited project that is 120 rows out of 835. They are not a rounding error in the
audit sense -- they are 1,615,000,000 IRR of the reported initial estimate, against
3,605,823,967,776 IRR from the 715 rows the schedule does account for. The report summed
all of them together because its query had no predicate that could tell them apart.

WHAT THIS ADDS, AND WHY IT IS A COLUMN RATHER THAN A PREDICATE

"Has no MPP uid" is already derivable, and a derivable fact does not need a column. What
is NOT derivable is the DECISION: the approved model excludes these rows from MPP-derived
totals "unless an approved exception exists", and an exception is something a person
grants. There is nowhere in the schema to record that, so:

    legacy_status IS NULL          the schedule accounts for this row
    'legacy_unlinked'              it does not, and it is excluded from MPP-derived totals
    'approved_exception'           it does not, and somebody decided it counts anyway

Three constraints hold the shape:

    1. A row with an MPP uid can NEVER be marked legacy. The marker describes the absence
       of provenance, and letting it sit on a row that has some would let a real
       assignment be excluded by editing one column.
    2. Every row is one or the other. This is what stops the 121st source-less row: an
       INSERT with no uid and no marker is refused by the database, not only by the
       service.
    3. The vocabulary is closed.

THE BACKFILL IS TRUTHFUL AND IS NOT AN IDENTITY

It writes `legacy_unlinked` on exactly the rows whose own two uid columns are NULL. That
is a restatement of what the row already says, not a claim about where it came from. No
MPP resource uid, assignment uid or task uid is invented, and nothing is linked by name.

NOTHING IS DELETED AND NOTHING IS DEACTIVATED

All 120 rows stay live, readable and revisable. Two of them are named by invoice lines --
«برآورد مصالح مورد نياز» and «بتن ريزي سقف» -- and an invoice is evidence that a person
did something, which outlives any opinion about the row's provenance. The marker changes
which TOTAL a row enters. It does not change whether the row exists.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE estimate_lines
    ADD COLUMN IF NOT EXISTS legacy_status text;

COMMENT ON COLUMN estimate_lines.legacy_status IS
    'NULL when the row is MPP-derived. ''legacy_unlinked'' when it names no MPP '
    'assignment or task and is therefore kept out of MPP-derived totals. '
    '''approved_exception'' when somebody decided such a row counts anyway. It describes '
    'the ABSENCE of schedule provenance and may never sit on a row that has some.';

-- TRUTHFUL BACKFILL. Every row whose own uid columns are both NULL is restated as what it
-- already is. No identity is invented, and no row is matched by name.
UPDATE estimate_lines
   SET legacy_status = 'legacy_unlinked'
 WHERE legacy_status IS NULL
   AND source_assignment_uid IS NULL
   AND source_task_uid IS NULL;

-- 1. A closed vocabulary.
ALTER TABLE estimate_lines
    ADD CONSTRAINT estimate_lines_legacy_status_vocabulary CHECK (
        legacy_status IS NULL
        OR legacy_status IN ('legacy_unlinked', 'approved_exception'));

-- 2. The marker only ever describes a row with no schedule provenance.
ALTER TABLE estimate_lines
    ADD CONSTRAINT estimate_lines_legacy_status_has_no_uid CHECK (
        legacy_status IS NULL
        OR (source_assignment_uid IS NULL AND source_task_uid IS NULL));

-- 3. Every row is one or the other. This is the one that stops the next source-less row
--    at the database, whatever route reaches it.
ALTER TABLE estimate_lines
    ADD CONSTRAINT estimate_lines_state_their_provenance CHECK (
        source_assignment_uid IS NOT NULL
        OR source_task_uid IS NOT NULL
        OR legacy_status IS NOT NULL);

COMMENT ON CONSTRAINT estimate_lines_state_their_provenance ON estimate_lines IS
    'A line is either accounted for by the schedule -- it names an MPP assignment or an '
    'MPP task -- or it is explicitly marked legacy. There is no third state, because the '
    'third state was a row that entered the project total and no file could explain.';

-- "Which lines may enter an MPP-derived total" -- asked by the report on every load.
CREATE INDEX IF NOT EXISTS ix_estimate_lines_mpp_derived
    ON estimate_lines (organization_id, project_id)
 WHERE deleted_at IS NULL AND legacy_status IS NULL;
"""


DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ix_estimate_lines_mpp_derived;
ALTER TABLE estimate_lines
    DROP CONSTRAINT IF EXISTS estimate_lines_state_their_provenance;
ALTER TABLE estimate_lines
    DROP CONSTRAINT IF EXISTS estimate_lines_legacy_status_has_no_uid;
ALTER TABLE estimate_lines
    DROP CONSTRAINT IF EXISTS estimate_lines_legacy_status_vocabulary;
ALTER TABLE estimate_lines
    DROP COLUMN IF EXISTS legacy_status;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
