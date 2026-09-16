"""a rejected row may not be able to say what it was, and that is the point of it

Revision ID: 0029
Revises: 0028

WHAT 0027 GOT WRONG

It required `product_external_id`, `product_name_snapshot` and `provider_name_snapshot` on
EVERY row of `price_observations`. That is right for a row anybody may price from and wrong
for the ones beside them: this table also holds REJECTED rows, kept as evidence of what a
sheet actually contained, and a row rejected for `missing_product_id` has no product id to
state. The constraint would have made that evidence unstorable and pushed the importer
toward inventing an identifier -- the same failure the date constraint was already fixed to
avoid, in the same table, one constraint apart.

So the requirement is written against the status, exactly as the price and the date already
are. Three rules, one shape:

    validation_status = 'valid'  ->  states its price, its business date AND its identity
    anything else                ->  keeps whatever the sheet gave, including nothing

WHY IT IS STILL NOT VALID, AND WHEN IT COULD BECOME VALID

All 3,821 existing observations are 'valid' and none carries a snapshot: they were written
before the columns existed, and `price_observations_immutable` refuses every UPDATE to that
table, which is what makes it evidence rather than a cache.

    There is NO truthful path to validating this constraint over those rows.

    Not "not yet" -- none. Filling them would mean asserting what a product was CALLED on a
    day nobody recorded it, and the only sources available are today's names, which have
    had a year to change. Observations are append-only and are never deleted, so the rows
    will not age out either.

    The constraint can be validated on the day no pre-0027 observation remains, and that
    day does not arrive by itself. It is recorded here so nobody later reads NOT VALID as a
    task somebody forgot to finish.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- SCHEMA DRIFT, CORRECTED.
--
-- An earlier draft of 0027 made `workflow_date_gregorian` NOT NULL, and was amended to a
-- status-scoped CHECK before it was merged -- but the amendment reached the UPGRADE and
-- the DOWNGRADE did not drop what the first draft had already set. Any database that ran
-- the first draft therefore carries a NOT NULL the migration chain no longer declares,
-- while a database built fresh from the chain does not. `bambo_canonical_test` is one of
-- the former; this audit found it by inserting a REJECTED row and being refused for the
-- wrong reason.
--
-- Dropping it here brings both back into step. On a database that never had it, this is a
-- no-op. The requirement itself has not moved: it is the status-scoped CHECK, because a
-- row rejected for an unreadable date has no date to store.
ALTER TABLE price_observations
    ALTER COLUMN workflow_date_gregorian DROP NOT NULL;

ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_states_its_identity;

ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_valid_row_states_identity CHECK (
        validation_status <> 'valid'
        OR (product_external_id IS NOT NULL
            AND btrim(product_external_id) <> ''
            AND product_name_snapshot IS NOT NULL
            AND btrim(product_name_snapshot) <> ''
            AND provider_name_snapshot IS NOT NULL
            AND btrim(provider_name_snapshot) <> '')) NOT VALID;

COMMENT ON CONSTRAINT price_observations_valid_row_states_identity ON price_observations IS
    'Every row anybody may price from says which product and supplier it was, as imported. '
    'NOT VALID because the 3,821 observations written before these columns existed cannot '
    'be repaired truthfully -- the table is append-only by trigger, and today''s names are '
    'not evidence of what a product was called a year ago. It applies to every new row: a '
    'NOT VALID check skips existing rows and nothing else.';
"""


DOWNGRADE_SQL = r"""
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_valid_row_states_identity;

ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_states_its_identity CHECK (
        product_external_id IS NOT NULL
        AND btrim(product_external_id) <> ''
        AND product_name_snapshot IS NOT NULL
        AND btrim(product_name_snapshot) <> ''
        AND provider_name_snapshot IS NOT NULL
        AND btrim(provider_name_snapshot) <> '') NOT VALID;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
