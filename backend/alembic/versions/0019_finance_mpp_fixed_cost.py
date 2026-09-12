"""The task cost the file states and nothing read

MS Project puts money in two places on a task: on its assignments, and on the task itself
as Fixed Cost -- an amount that belongs to the activity rather than to any resource on it.
The reader has stored the second one since 0012, in `finance_mpp_rows.source_fixed_cost`,
and nothing in `app/finance/` has ever read it. Fifty-one billion rials of this project's
schedule sat in a column no calculation opened.

Two things were missing, and this adds both.

THE AMOUNT IN THE UNIT FINANCE COUNTS IN
`source_fixed_cost` holds the file's own number, exactly as `source_cost` and
`source_actual_cost` do -- the prefix says whose number it is and the absent `_irr` says it
is not rials. This project's file is denominated in toman, so reading that column as money
would be wrong by a factor of ten in the direction nobody notices. `source_fixed_cost_irr`
is the same figure through the same currency decision the assignment cost already passes
through (`_currency_scale` in coreint/finance_mpp_sync.py), so the two costs on one row are
finally in one unit. The raw column stays exactly as it is: it is the file's answer, and
the file's answer should still be readable after this.

Existing rows get the new column by a `refresh` sync, which exists for this: it re-reads an
unchanged file and replaces the rows of its version without touching the version row, so
every pinned report still resolves. Issued reports are frozen payloads and are not affected
either way.

THE TWO IDENTITIES A FIXED COST NEEDS
A fixed cost belongs to a TASK, not to an assignment, so the identity the mapper already
keys on (`ux_estimate_lines_source_assignment`) cannot hold it. The second index below is
its counterpart: one estimate line per task, among the lines that name a task and no
assignment. Nothing today is in that state -- every mapped line carries both uids and every
imported line carries neither -- so the index starts empty and only ever constrains the
lines this feature creates.

And a fixed cost names no resource, because there is none: the money is the activity's.
Finance still requires an estimate line to point at a financial item, so the mapper creates
one general cost item per project to carry them, and the first index is what makes creating
it idempotent. It is deliberately narrow -- one code, in one project -- rather than a
uniqueness rule over every resource code, which is a larger claim about existing data than
this change has any business making.

REVISION NUMBERING
This follows 0018, which is the correction of 0017's CHECK vocabulary that
`origin/backend-finance` wrote. For a while 0018 was not in this branch at all and this
revision hung off 0017 with the gap documented; the file has since been brought in and the
parent corrected, so the chain is linear again.

The two are independent as SCHEMA: 0018 replaces a CHECK on
`progress_snapshot_refs.snapshot_status`, and nothing here touches that table. The order is
therefore a bookkeeping choice rather than a requirement, and linear is what this
repository keeps -- see `tests/test_migrations.py`, which refuses a second head and says
why. Correcting the parent was safe because a census of every local database put the
presentation database at 0016 and this revision in throwaway copies only.
"""

from alembic import op
from sqlalchemy.schema import DDL

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_mpp_rows
    ADD COLUMN source_fixed_cost_irr numeric;

COMMENT ON COLUMN finance_mpp_rows.source_fixed_cost_irr IS
    'The task''s own Fixed Cost in rials -- the file''s `source_fixed_cost` through the '
    'same currency decision the assignment cost passes through. Repeated on every row of '
    'the task, exactly as `source_cost` is, so it must be de-duplicated by task uid before '
    'it is summed. NULL when the file states none.';

-- One general cost item per project to carry the schedule's fixed costs. Narrow on
-- purpose: it constrains the one code this feature owns and says nothing about any other.
CREATE UNIQUE INDEX ux_finance_resources_schedule_fixed_cost
    ON finance_resources (organization_id, project_id)
    WHERE code = 'MPP-FIXEDCOST' AND deleted_at IS NULL;

-- One estimate line per task, among the lines that name a task and no assignment. The
-- assignment-keyed index cannot serve this: a fixed cost has no assignment to key on.
CREATE UNIQUE INDEX ux_estimate_lines_source_task_fixed_cost
    ON estimate_lines (organization_id, project_id, source_task_uid)
    WHERE source_task_uid IS NOT NULL
      AND source_assignment_uid IS NULL
      AND deleted_at IS NULL;
"""

DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ux_estimate_lines_source_task_fixed_cost;
DROP INDEX IF EXISTS ux_finance_resources_schedule_fixed_cost;
ALTER TABLE finance_mpp_rows DROP COLUMN IF EXISTS source_fixed_cost_irr;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
