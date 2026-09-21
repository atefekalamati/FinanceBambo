"""a number the sheet stated is not deleted because we could not label it

Revision ID: 0035
Revises: 0034

WHAT 0034 GOT WRONG

0034 replaced `weight_value` + `weight_unit` with a single `weight_kg`, on the reasoning
that one column in one unit cannot be misread. That reasoning was right about the unit and
wrong about the number.

For the 486 rows whose unit was provable it worked: 1100 g became 1.1 kg, 18 kg stayed 18.
For the 84 whose unit was not -- Angle 48, Channel 36, where the sheet cell holds a bare
`32.0` -- it left `weight_kg` NULL, which is still the correct refusal, AND removed the 32
along with it. The listing went from "weighs 32 of something" to "weighs nothing recorded",
and a screen reading that column could no longer show what the workbook plainly says.

The number was not lost -- 0034 wrote every original pair into `metadata._legacyWeight`
before dropping the columns -- but an audit record is not a product attribute. Nothing
selects it, the API does not publish it, and a reader cannot be asked to open the audit
trail to find out what a thing weighs.

WHAT THIS RESTORES, AND WHAT IT DOES NOT

`weight_value` comes back as the first-class source attribute. `weight_unit` does NOT: the
generic attribute-unit model 0033 removed stays removed, and the sheet's unit evidence is
still spent on computing `weight_kg` rather than stored beside the number.

    weight_value   what the sheet said          -- always, when it said a number
    weight_kg      what that is in kilograms    -- only when the unit was provable

The name is the one that was already there. The parser's declaration table never stopped
calling this column `weight_value`; 0034 only discarded it at the last step. And every
surviving sibling -- `length_value`, `width_value`, `height_value`, `thickness_value`,
`diameter_value` -- carries the same suffix, so a `weight` would have been the one
attribute spelled differently from the rest.

THE BACKFILL, AND WHY IT READS THE AUDIT RECORD

Every one of the 570 rows is restored from `metadata._legacyWeight.value`, which is the
number as it was parsed from the sheet, before any conversion. All 570 are readable
numbers; none had to be reconstructed.

It is NOT computed back out of `weight_kg`, and that is the whole point: 1.1 kg would give
back 1.1, and the sheet said 1100. Multiplying by a thousand to undo a division would be
inventing the source from the derivative, which is exactly the direction of reasoning this
revision exists to stop.

`metadata._legacyWeight` is left in place. It now records something the columns cannot --
which unit the conversion was made on -- and nothing is served by deleting the evidence
that this backfill was itself derived from.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE provider_items ADD COLUMN IF NOT EXISTS weight_value numeric(18, 6);

-- The sheet's own number, back where a reader can reach it. From the audit record rather
-- than from weight_kg: see the note above about 1.1 and 1100.
UPDATE provider_items
   SET weight_value = (metadata -> '_legacyWeight' ->> 'value')::numeric
 WHERE metadata ? '_legacyWeight'
   AND (metadata -> '_legacyWeight' ->> 'value') IS NOT NULL;

-- ------------------------------------------------------------------ the guards again
-- Both of these have to name the new column, and `weight_has_basis` moves BACK onto the
-- source value where it was before 0034. "What is this weight per" is a question about the
-- number the sheet stated, not about whether we managed to convert it -- and the 84 rows
-- prove the difference: they have a weight and no kilograms, and they must still be
-- required to say what the weight is per.
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
        (weight_kg       IS NULL OR (weight_kg       > 0 AND weight_kg       <> 'NaN')) AND
        (coverage_m2     IS NULL OR (coverage_m2     > 0 AND coverage_m2     <> 'NaN')) AND
        (volume_m3       IS NULL OR (volume_m3       > 0 AND volume_m3       <> 'NaN')));

ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_weight_has_basis;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_weight_has_basis CHECK (
        weight_value IS NULL OR weight_basis IS NOT NULL);

-- A derived value with no source would mean the conversion outlived the number it was
-- made from, which cannot happen through the importer and must not happen through a
-- hand-written UPDATE either.
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_kilograms_need_their_source CHECK (
        weight_kg IS NULL OR weight_value IS NOT NULL);

COMMENT ON COLUMN provider_items.weight_value IS
    'The weight the sheet stated, as a number, in whatever unit the sheet was using. This '
    'is SOURCE data: it is what a reader is shown, and it survives whether or not the '
    'backend could work out what unit it is in. 84 Angle and Channel listings have one of '
    'these and no weight_kg, because their cell is a bare number with no unit anywhere on '
    'the row -- the value is real, only its unit is unknown.';

COMMENT ON COLUMN provider_items.weight_kg IS
    'weight_value expressed in kilograms, and NULL when that could not be proven. DERIVED: '
    'never shown in place of weight_value, and never used to reconstruct it. A calculation '
    'that needs a mass reads this one and gets nothing where nothing was provable, which '
    'is the refusal that keeps a 32 of unknown unit out of an estimate.';
"""


DOWNGRADE_SQL = r"""
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_kilograms_need_their_source;

ALTER TABLE provider_items DROP CONSTRAINT IF EXISTS provider_items_weight_has_basis;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_weight_has_basis CHECK (
        weight_kg IS NULL OR weight_basis IS NOT NULL);

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

-- Safe to drop: `metadata._legacyWeight` still holds every one of these numbers, which is
-- where this column was filled from in the first place.
ALTER TABLE provider_items DROP COLUMN IF EXISTS weight_value;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
