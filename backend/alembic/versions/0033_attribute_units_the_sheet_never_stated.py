"""five attribute-unit columns nobody wrote to, and the one that must stay

Revision ID: 0033
Revises: 0032

WHAT THIS REMOVES

`length_unit`, `width_unit`, `height_unit`, `thickness_unit`, `diameter_unit`.

0027 gave every measured attribute a `_value`/`_unit` pair, on the reasonable theory that a
sheet stating "12 m" should record both halves. The sheets do not work that way. Counted on
the 6,579 listings currently imported:

    width_unit         0 non-null
    height_unit        0 non-null
    thickness_unit     0 non-null
    diameter_unit      0 non-null
    length_unit      456 non-null, ONE distinct value: 'm'

Four of the five were never written to at all. The fifth says 'm' 456 times, and every one
of those rows also carries `length_m`, which equals `length_value` in all 456 -- because
`to_metres` normalises at import and `length_m` is what any conversion actually reads. So
the column is a constant beside a normalised value: dropping it removes a restatement, not
a fact.

WHAT THIS DELIBERATELY KEEPS, AND WHY IT IS NOT AN OVERSIGHT

`weight_unit` STAYS. It was asked for in the same breath as the others and it is the one
that carries information:

    brick                              g    232 rows
    Hollow structural section_table    kg   144 rows
    steel - I-beam                     kg   110 rows

Dropping it would make 232 brick weights read as kilograms. That is a factor of a thousand
in every weight-based unit conversion that touches brick, and it would be silent -- the
number stays, only its meaning changes. It can be removed once the values are normalised to
one unit, and not before.

That normalisation is not done here, for a reason the same count shows: 84 rows
(Channel_table 36, Angle iron-table 48) carry a `weight_value` with NO `weight_unit` at all.
Those cannot be converted without deciding what they meant, and deciding that is a reading
of the sheet, not a migration.

WHAT IT DOES NOT TOUCH

`source_unit` -- the unit the PRICE is per -- is a different column and a different concept,
and this revision does not go near it. See the report accompanying this change: it is
populated on 1,244 of 6,579 listings, all of them from `steel -Rebar`, and making it
mandatory is a decision about six worksheets' worth of data rather than a schema edit.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


#: The mass units 0027 allows. Repeated here rather than imported: a migration states the
#: vocabulary it writes, and reaching into an earlier revision's module would make this one
#: change meaning when that one is edited.
_MASS_UNITS = "'g', 'kg', 'ton'"

UPGRADE_SQL = r"""
ALTER TABLE provider_items
    DROP COLUMN IF EXISTS length_unit,
    DROP COLUMN IF EXISTS width_unit,
    DROP COLUMN IF EXISTS height_unit,
    DROP COLUMN IF EXISTS thickness_unit,
    DROP COLUMN IF EXISTS diameter_unit;

-- ------------------------------------------- the two guards, rebuilt around what is left
-- DROP COLUMN takes every CHECK that mentions the column with it, and 0027 wrote both of
-- these as ONE constraint spanning all six attributes. So dropping five of them silently
-- removed the rules protecting the sixth: after the DROP above, `weight_unit` could be set
-- with no weight beside it and could hold any string at all. The existing suite caught it,
-- which is the only reason this section is here rather than in a later bug report.
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_unit_needs_value CHECK (
        weight_unit IS NULL OR weight_value IS NOT NULL);

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_units_are_registry_codes CHECK (
        weight_unit IS NULL OR weight_unit IN (""" + _MASS_UNITS + r"""));

COMMENT ON COLUMN provider_items.weight_unit IS
    'The unit a weight_value is in. Kept where the other attribute units were dropped, '
    'because this one is the only one that varies: brick states weights in g and the '
    'steel worksheets state them in kg. Removing it would not lose a label, it would '
    'multiply 232 brick weights by a thousand, silently.';

COMMENT ON COLUMN provider_items.length_m IS
    'A length normalised to metres at import. Since 0033 this is the ONLY place a length '
    'unit is recorded: length_unit said ''m'' on every row that had one, and this column '
    'already carried the same number with its unit settled.';
"""


DOWNGRADE_SQL = r"""
-- The narrowed guards go first: 0032's shape had them spanning six columns, and the
-- columns being restored below must come back under the rules they left under.
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_units_are_registry_codes;
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_unit_needs_value;

-- The columns come back empty, and they come back nullable, which is how they were.
-- Four of them held nothing, so nothing is lost restoring them. `length_unit` held 'm' on
-- every row that had a length, and that statement survives in `length_m` -- refilling it
-- here would mean writing a unit back onto rows from a rule rather than from the sheet,
-- which is the kind of invention this schema exists to prevent.
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS length_unit text,
    ADD COLUMN IF NOT EXISTS width_unit text,
    ADD COLUMN IF NOT EXISTS height_unit text,
    ADD COLUMN IF NOT EXISTS thickness_unit text,
    ADD COLUMN IF NOT EXISTS diameter_unit text;

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_unit_needs_value CHECK (
        (length_unit    IS NULL OR length_value    IS NOT NULL) AND
        (width_unit     IS NULL OR width_value     IS NOT NULL) AND
        (height_unit    IS NULL OR height_value    IS NOT NULL) AND
        (thickness_unit IS NULL OR thickness_value IS NOT NULL) AND
        (diameter_unit  IS NULL OR diameter_value  IS NOT NULL) AND
        (weight_unit    IS NULL OR weight_value    IS NOT NULL));

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_units_are_registry_codes CHECK (
        (weight_unit    IS NULL OR weight_unit    IN (""" + _MASS_UNITS + r""")) AND
        (length_unit    IS NULL OR length_unit    IN ('mm', 'cm', 'm')) AND
        (width_unit     IS NULL OR width_unit     IN ('mm', 'cm', 'm')) AND
        (height_unit    IS NULL OR height_unit    IN ('mm', 'cm', 'm')) AND
        (thickness_unit IS NULL OR thickness_unit IN ('mm', 'cm', 'm')) AND
        (diameter_unit  IS NULL OR diameter_unit  IN ('mm', 'cm', 'm')));
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
