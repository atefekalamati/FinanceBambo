"""The rest of what Finance actually reads from a schedule

Revision ID: 0012
Revises: 0011

0011 gave Finance its own copy of the schedule, but only of the numbers a calculation
consumes. The progress page reads more than that, and every field it reads was arriving
null from the Finance source while the Core source filled it -- so the same page looked
complete on one snapshot and empty on another. This adds exactly the fields with a real
consumer, and nothing else.

WHAT WAS ADDED AND WHO ASKED FOR IT
  * `task_start` / `task_finish` -- the progress page renders them as "شروع" / "پایان".
    Stored as text, exactly as `msp_tasks` stores them and exactly as the file states
    them: a schedule writes wall-clock dates with no zone, and turning them into
    timestamptz would mean choosing a timezone the file never named.
  * `resource_type` -- the page shows what kind of resource a row is.
  * `resource_unit` -- the page shows the resource's own unit. This is NOT the approved
    quantity's unit: `quantity_unit` stays the unit of a stated quantity, and the two are
    different claims about different numbers.
  * `progress_variance` -- already declared in the feed's metrics contract, and answered
    null by the Finance source alone.

WHAT WAS DELIBERATELY NOT ADDED
  * Work (planned/actual/remaining) and the assignment's work-complete percent. The page
    does display them, but `resolve_progress_quantity` treats reported work as an executed
    QUANTITY for a labour or equipment resource. Persisting work here would re-open that
    path for the Finance source and start moving money, which is a financial decision and
    not this migration's business. The columns can be added the day that decision is made.
  * `outline_number` / `outline_level`. WBS parentage is derived from the code string
    itself (`domain/wbs.py::parent_of`), so no outline column is read by anything.

RENAMED, BECAUSE THE OLD NAMES WERE A TRAP
`cost`, `actual_cost` and `fixed_cost` are the SCHEDULE's own figures. Finance's actual
cost comes from confirmed invoices and from nowhere else, and a column called `actual_cost`
sitting in a Finance table invites exactly the confusion the PRD warns about. They become
`source_cost`, `source_actual_cost`, `source_fixed_cost`: the prefix says whose number it
is. Renames, not new columns, so the 727 stored values move with their meaning intact.

`quantity` gains its declared precision, numeric(18,4). Every stored value is NULL today,
so nothing is rounded by the change.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_mpp_rows
    -- Text, like msp_tasks and like the file: a schedule states wall-clock dates and
    -- names no timezone, so none is invented here.
    ADD COLUMN task_start text,
    ADD COLUMN task_finish text,
    ADD COLUMN resource_type text,
    -- The RESOURCE's own unit. `quantity_unit` remains the unit of an approved quantity;
    -- a row can state one without the other, and they are not interchangeable.
    ADD COLUMN resource_unit text,
    ADD COLUMN progress_variance numeric;

COMMENT ON COLUMN finance_mpp_rows.task_start IS
    'Schedule start as the file states it. Text, because the file names no timezone.';
COMMENT ON COLUMN finance_mpp_rows.resource_unit IS
    'The resource''s own unit of measure. NOT the unit of an approved quantity -- that is '
    'quantity_unit.';

-- The schedule's cost figures, renamed so nothing can mistake them for Finance money.
-- Finance actual cost comes from confirmed invoices; these are what the plan said.
ALTER TABLE finance_mpp_rows RENAME COLUMN cost TO source_cost;
ALTER TABLE finance_mpp_rows RENAME COLUMN actual_cost TO source_actual_cost;
ALTER TABLE finance_mpp_rows RENAME COLUMN fixed_cost TO source_fixed_cost;

COMMENT ON COLUMN finance_mpp_rows.source_cost IS
    'The SCHEDULE''s cost for this task. Not a Finance figure: Finance actual cost comes '
    'from confirmed invoices.';

-- The precision the PRD declares for a quantity. Free today: every value is NULL.
ALTER TABLE finance_mpp_rows ALTER COLUMN quantity TYPE numeric(18,4);
"""


DOWNGRADE_SQL = r"""
ALTER TABLE finance_mpp_rows ALTER COLUMN quantity TYPE numeric;

ALTER TABLE finance_mpp_rows RENAME COLUMN source_fixed_cost TO fixed_cost;
ALTER TABLE finance_mpp_rows RENAME COLUMN source_actual_cost TO actual_cost;
ALTER TABLE finance_mpp_rows RENAME COLUMN source_cost TO cost;

ALTER TABLE finance_mpp_rows
    DROP COLUMN progress_variance,
    DROP COLUMN resource_unit,
    DROP COLUMN resource_type,
    DROP COLUMN task_finish,
    DROP COLUMN task_start;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
