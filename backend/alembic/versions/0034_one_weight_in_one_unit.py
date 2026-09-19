"""a weight in kilograms, and the 84 that never said what they were in

Revision ID: 0034
Revises: 0033

WHAT REPLACES WHAT

`weight_value` + `weight_unit` become `weight_kg`. One column, one unit, no pairing for a
reader to get wrong.

The pair was the last of the attribute-unit model 0033 removed, and it was kept then
because it carried information the others did not: brick states weights in g and the steel
worksheets state them in kg. That information does not disappear here -- it is APPLIED, and
then the column that carried it is no longer needed.

    g    ->  value / 1000
    kg   ->  value
    ton  ->  value * 1000        (vocabulary allows it; no row uses it today)

THE 84 THAT ARE NOT CONVERTED

Counted before writing anything:

    kg     254 rows   (Hollow 144, I-beam 110)
    g      232 rows   (brick)
    NULL    84 rows   (Angle 48, Channel 36)

The 84 were traced to their source before this revision was written. Their sheet cells hold
a BARE NUMBER -- '32.0', '7.0', '24.0' -- with no unit anywhere on the row, in the column
heading, or in the product name; the parser reads them under the `BARE_NUMBER` shape, which
is why no unit was ever stored. There is nothing to recover.

So `weight_kg` stays NULL for all 84. A weight whose unit nobody wrote down is not a weight
this system can convert, and choosing kilograms for it because the neighbouring worksheets
use kilograms is the exact guess the whole unit model exists to prevent: it would be wrong
by a thousand wherever it was wrong, and it would look like every other number.

WHERE THE EVIDENCE GOES

Before the columns are dropped, each row's original pair is written into `metadata` under
`_legacyWeight`. That is not decoration. Brick's weights came from a backfill of an older
sheet revision (`spec_source = 'legacy_metadata'`) and its current worksheet carries no
weight column at all, so after the drop the pair would exist nowhere else and 232 rows would
lose the record of what they were stated in. The raw statement survives the column.

WHAT THIS DOES NOT TOUCH

`source_unit` -- the commercial basis a price is PER -- is a different column answering a
different question, and nothing here reads or writes it. `weight_kg` is a physical fact
about a product; `source_unit` is a fact about how it is sold. Conflating them is how a
price per branch gets multiplied by a weight per metre.

`price_observations` is not touched at all: it is append-only and holds no weight.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE provider_items ADD COLUMN IF NOT EXISTS weight_kg numeric(18, 6);

-- ------------------------------------------------- the raw statement, before it is gone
-- Written for every row that has a weight, including the 84 with no unit: "a number and no
-- unit" is itself the fact a later reader needs, and it is the fact that explains why
-- weight_kg is null on those rows.
UPDATE provider_items
   SET metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
           '_legacyWeight', jsonb_build_object('value', weight_value::text,
                                               'unit', weight_unit))
 WHERE weight_value IS NOT NULL;

-- --------------------------------------------------------------------- the conversion
UPDATE provider_items SET weight_kg = weight_value / 1000 WHERE weight_unit = 'g';
UPDATE provider_items SET weight_kg = weight_value        WHERE weight_unit = 'kg';
UPDATE provider_items SET weight_kg = weight_value * 1000 WHERE weight_unit = 'ton';
-- No branch for weight_unit IS NULL, deliberately. Those rows keep weight_kg NULL.

-- ------------------------------------------------------------- the guards, moved across
-- Both of these named `weight_value`, so DROP COLUMN would take them away. They are
-- rebuilt on `weight_kg` first, so there is no moment at which the rule is absent.
ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_measures_positive;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_measures_positive CHECK (
        (length_m        IS NULL OR (length_m        > 0 AND length_m        <> 'NaN')) AND
        (length_value    IS NULL OR (length_value    > 0 AND length_value    <> 'NaN')) AND
        (width_value     IS NULL OR (width_value     > 0 AND width_value     <> 'NaN')) AND
        (height_value    IS NULL OR (height_value    > 0 AND height_value    <> 'NaN')) AND
        (thickness_value IS NULL OR (thickness_value > 0 AND thickness_value <> 'NaN')) AND
        (diameter_value  IS NULL OR (diameter_value  > 0 AND diameter_value  <> 'NaN')) AND
        (weight_kg       IS NULL OR (weight_kg       > 0 AND weight_kg       <> 'NaN')) AND
        (coverage_m2     IS NULL OR (coverage_m2     > 0 AND coverage_m2     <> 'NaN')) AND
        (volume_m3       IS NULL OR (volume_m3       > 0 AND volume_m3       <> 'NaN')));

-- A weight with no basis is a number nobody can convert: 27 kg per WHAT. The rule is the
-- same as before and now reads the column that survives.
ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_weight_has_basis;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_weight_has_basis CHECK (
        weight_kg IS NULL OR weight_basis IS NOT NULL);

-- ------------------------------------------------------------------------ the removal
-- This also removes `provider_items_unit_needs_value` and
-- `provider_items_units_are_registry_codes`, which 0033 had narrowed to weight alone.
-- Both only ever said "if there is a unit, it must be sane"; with no unit column there is
-- nothing left for them to say.
ALTER TABLE provider_items
    DROP COLUMN IF EXISTS weight_value,
    DROP COLUMN IF EXISTS weight_unit;

COMMENT ON COLUMN provider_items.weight_kg IS
    'A product weight in kilograms, always. It replaced a weight_value/weight_unit pair '
    'in 0034; g was divided by 1000 and kg carried across unchanged. NULL where the '
    'source stated a bare number with no unit -- 84 Angle and Channel listings -- because '
    'a weight whose unit nobody wrote down cannot be converted, and the original pair is '
    'kept in metadata._legacyWeight for every row that had one. This is a PHYSICAL '
    'attribute and has nothing to do with source_unit, which is what a price is per.';
"""


DOWNGRADE_SQL = r"""
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS weight_value numeric(18, 6),
    ADD COLUMN IF NOT EXISTS weight_unit text;

-- Restored from the record this revision deliberately kept, rather than by dividing
-- weight_kg back out: the stored pair is what the source said, and reconstructing it from
-- the converted number would invent a unit for the 84 rows that never had one.
UPDATE provider_items
   SET weight_value = (metadata -> '_legacyWeight' ->> 'value')::numeric,
       weight_unit  =  metadata -> '_legacyWeight' ->> 'unit'
 WHERE metadata ? '_legacyWeight';

UPDATE provider_items
   SET metadata = metadata - '_legacyWeight'
 WHERE metadata ? '_legacyWeight';

ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_weight_has_basis;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_weight_has_basis CHECK (
        weight_value IS NULL OR weight_basis IS NOT NULL);

ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_measures_positive;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_measures_positive CHECK (
        (length_m        IS NULL OR (length_m        > 0 AND length_m        <> 'NaN')) AND
        (length_value    IS NULL OR (length_value    > 0 AND length_value    <> 'NaN')) AND
        (width_value     IS NULL OR (width_value     > 0 AND width_value     <> 'NaN')) AND
        (height_value    IS NULL OR (height_value    > 0 AND height_value    <> 'NaN')) AND
        (thickness_value IS NULL OR (thickness_value > 0 AND thickness_value <> 'NaN')) AND
        (diameter_value  IS NULL OR (diameter_value  > 0 AND diameter_value  <> 'NaN')) AND
        (weight_value    IS NULL OR (weight_value    > 0 AND weight_value    <> 'NaN')) AND
        (coverage_m2     IS NULL OR (coverage_m2     > 0 AND coverage_m2     <> 'NaN')) AND
        (volume_m3       IS NULL OR (volume_m3       > 0 AND volume_m3       <> 'NaN')));

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_unit_needs_value CHECK (
        weight_unit IS NULL OR weight_value IS NOT NULL);

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_units_are_registry_codes CHECK (
        weight_unit IS NULL OR weight_unit IN ('g', 'kg', 'ton'));

ALTER TABLE provider_items DROP COLUMN IF EXISTS weight_kg;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
