"""Keep the sheet's weight number alongside the optional normalized kilograms.

Revision ID: 0035
Revises: 0034

0034 preserved historical source values in metadata._legacyWeight. This forward
revision restores them to the existing canonical source-attribute name without
altering weight_kg, price observations, or any other financial record.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE provider_items ADD COLUMN weight_value numeric(18, 6);

UPDATE provider_items
   SET weight_value = (metadata -> '_legacyWeight' ->> 'value')::numeric
 WHERE metadata ? '_legacyWeight'
   AND weight_value IS NULL
   AND metadata -> '_legacyWeight' ->> 'value' IS NOT NULL;

ALTER TABLE provider_items DROP CONSTRAINT provider_items_measures_positive;
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

COMMENT ON COLUMN provider_items.weight_value IS
    'Numeric weight as stated by the source sheet. Its unit may be unknown; '
    'weight_kg is independently derived only with unit evidence. Historical '
    'values were restored from metadata._legacyWeight, which remains intact.';
"""


DOWNGRADE_SQL = r"""
UPDATE provider_items
   SET metadata = coalesce(metadata, '{}'::jsonb) ||
       jsonb_build_object('_legacyWeight',
           jsonb_build_object('value', weight_value::text, 'unit', NULL))
 WHERE weight_value IS NOT NULL
   AND NOT metadata ? '_legacyWeight';

ALTER TABLE provider_items DROP CONSTRAINT provider_items_measures_positive;
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

ALTER TABLE provider_items DROP COLUMN weight_value;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
