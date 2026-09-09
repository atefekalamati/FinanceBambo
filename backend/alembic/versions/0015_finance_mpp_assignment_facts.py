"""What the file says about one assignment, kept

Revision ID: 0015
Revises: 0014

`finance_mpp_rows` records a schedule row, and until now it recorded the TASK's figures on
every one of them: `finance_mpp_sync` builds one dict per task and copies it onto each of
that task's assignments, so a task with seven assignments stores its total seven times. The
file states more than that. `assignment.getUnits()` and `assignment.getCost()` are read for
every one of the 727 assignments and then discarded, and the numbers they carry are the
ones a person sees in MS Project's own Task Information dialog:

    task 1821 «اصلاح هندسی بلوار شاهنامه»
      خاکبرداری     560 مترمکعب     72,800,000
      زیر اساس      240 مترمکعب    156,000,000
      اساس          240 مترمرکعب   288,000,000
      قیر محلول   1,920 کیلوگرم    115,200,000
      آسفالت توپکا 9,600 مترمربع   720,000,000
                                 ------------
                                 1,352,000,000  <- which is what source_cost holds, on all five rows

TWO THINGS ARE NORMALISED ON THE WAY IN, AND NEITHER IS A GUESS
  * Units. MPXJ returns 56000.0 where the file shows 560 -- units come back scaled by a
    hundred. The stored number is the one the file shows.
  * Currency. The file states `currencySymbol = تومان` and `currencyCode = IRR`, which
    contradict each other; its amounts match the toman figures above. Finance stores rials
    everywhere, so the amount is multiplied by ten on the way in and the column says `_irr`
    because that is then true of it. Dividing by ten recovers the file's own number.

WHAT THIS IS NOT
`source_assignment_units` is NOT `quantity`. `quantity` is the approved financial quantity
and stays NULL until a person approves one; the schedule's units are the schedule's, and
the two live in different columns precisely so that nothing can quietly read one as the
other. For the same reason the assignment's cost is not a price: a price is per unit and
somebody enters it, and this is a total the schedule computed.

`normalized_unit` is the registry code the raw unit was recognised as, `unit_source` says
what recognised it, and `unit_confidence` is how sure that was. A unit nothing recognised
stays NULL at low confidence rather than being invented -- an unreadable unit is a thing to
report, not a thing to fill in.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_mpp_rows
    -- The assignment's own units, as the file shows them (MPXJ's value divided by 100).
    ADD COLUMN source_assignment_units numeric,
    -- The assignment's own cost, in rials: the file's toman amount multiplied by ten.
    ADD COLUMN source_assignment_cost_irr numeric,
    -- What `resource_unit` was recognised as, and how.
    ADD COLUMN normalized_unit text,
    ADD COLUMN unit_source text,
    ADD COLUMN unit_confidence text;

COMMENT ON COLUMN finance_mpp_rows.source_assignment_units IS
    'The units the file states for THIS assignment, on the file''s own scale. Not a '
    'financial quantity: `quantity` is that, and it stays NULL until a person approves one.';

COMMENT ON COLUMN finance_mpp_rows.source_assignment_cost_irr IS
    'The cost the file states for THIS assignment, in rials (the file''s toman amount x10). '
    'Not a price and not an actual cost: a price is per unit and entered by a person, and '
    'an actual cost comes from a confirmed invoice.';

COMMENT ON COLUMN finance_mpp_rows.normalized_unit IS
    'The unit-registry code `resource_unit` was recognised as, or NULL when nothing '
    'recognised it. NULL is an answer here, not a gap to fill.';

COMMENT ON COLUMN finance_mpp_rows.unit_confidence IS
    'How the unit was arrived at: `exact` when the file named a registry unit, `alias` when '
    'a known spelling of one, `low` when nothing recognised it.';

-- Reading "the assignments of this task, with their own figures" is what every consumer of
-- these columns does.
CREATE INDEX IF NOT EXISTS ix_finance_mpp_rows_assignment_facts
    ON finance_mpp_rows (source_version_id, source_assignment_uid)
    WHERE source_assignment_uid IS NOT NULL;
"""


DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ix_finance_mpp_rows_assignment_facts;
ALTER TABLE finance_mpp_rows
    DROP COLUMN unit_confidence,
    DROP COLUMN unit_source,
    DROP COLUMN normalized_unit,
    DROP COLUMN source_assignment_cost_irr,
    DROP COLUMN source_assignment_units;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
