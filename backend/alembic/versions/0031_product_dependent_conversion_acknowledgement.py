"""a broad rule about a product-dependent crossing says who claimed it

Revision ID: 0031
Revises: 0030

WHAT WAS REFUSED, AND WHY THE REFUSAL WAS RIGHT

`validate_scope` rejects any cross-dimension rule at a scope wider than one listing.
«1 ton = 1000 kg» is a fact about units and holds for everything; «1 branch = 22 kg» is a
weighing of one product, and writing it for a whole category asserts that every product in
that category weighs the same. The reasoning stands and is not being reversed.

WHY IT BECAME A DEAD END ANYWAY

The narrow scope the refusal points at -- `provider_item` -- cannot be written until a
listing is attached to the line. On the audited project 832 of 835 estimate lines have no
component at all, and the price sheet states a unit for 311 of 1,735 listings. So a
quantity surveyor holding an incomplete MSP file and an incomplete sheet was told to
record the rule somewhere it was not yet possible to record it, and the daily price stayed
out of reach.

WHAT THIS CHANGES: A REFUSAL BECOMES AN ADMISSION

The rule may now be stored at a wider scope, and only when somebody says in the request
that they know what they are claiming. Three columns record that:

    product_dependent_acknowledged      the claim was made
    product_dependent_acknowledged_by   by whom
    product_dependent_acknowledged_at   when

The CHECK is what stops the flag becoming decoration: acknowledged and nameless is not a
state this table will hold. An unacknowledged rule is refused exactly as before -- the
default is `false`, so every caller that is not updated behaves as it does today.

NO BACKFILL, AND NONE IS POSSIBLE

There are no broad cross-dimension rules to backfill: writing one has never been allowed,
so the table cannot contain one. Every existing row is either narrow or same-dimension and
`false` is the true answer for all of them.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_unit_conversion_rules
    ADD COLUMN IF NOT EXISTS product_dependent_acknowledged boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS product_dependent_acknowledged_by uuid,
    ADD COLUMN IF NOT EXISTS product_dependent_acknowledged_at timestamptz;

COMMENT ON COLUMN finance_unit_conversion_rules.product_dependent_acknowledged IS
    'True when this rule crosses dimensions at a scope wider than one listing and a '
    'person stated, in the request that created it, that they know the crossing depends '
    'on the product. False is the ordinary case and the only value a same-dimension or '
    'listing-scoped rule ever carries.';

COMMENT ON COLUMN finance_unit_conversion_rules.product_dependent_acknowledged_by IS
    'Who made the claim. The point of the acknowledgement is that it has a name on it: a '
    'flag nobody is attached to is indistinguishable from a default.';

-- Acknowledged and nameless is not a state. Without this the flag could be set by any
-- path that forgot the actor, and the record would assert that somebody took
-- responsibility while naming nobody.
ALTER TABLE finance_unit_conversion_rules
    ADD CONSTRAINT finance_conversion_rule_acknowledgement_complete CHECK (
        product_dependent_acknowledged = false
        OR (product_dependent_acknowledged_by IS NOT NULL
            AND product_dependent_acknowledged_at IS NOT NULL));
"""


DOWNGRADE_SQL = r"""
ALTER TABLE finance_unit_conversion_rules
    DROP CONSTRAINT IF EXISTS finance_conversion_rule_acknowledgement_complete;
ALTER TABLE finance_unit_conversion_rules
    DROP COLUMN IF EXISTS product_dependent_acknowledged_at,
    DROP COLUMN IF EXISTS product_dependent_acknowledged_by,
    DROP COLUMN IF EXISTS product_dependent_acknowledged;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
