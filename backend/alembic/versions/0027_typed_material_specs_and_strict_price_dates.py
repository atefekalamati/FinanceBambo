"""typed product specifications, and a price that must state whose and when

Revision ID: 0027
Revises: 0026

WHY COLUMNS AND NOT A TABLE PER CATEGORY

Eight categories share one identity, one price history and one import path. Splitting them
would multiply every join by eight and leave `category` meaning nothing. So the hybrid the
decision asks for: shared identity stays normal columns, the specifications a calculation
actually needs become typed columns, and everything rare or newly discovered stays in
`metadata` -- which is not deleted and does not stop being read.

WHAT THE REAL SHEETS SUPPORT, MEASURED BEFORE THIS WAS WRITTEN

Across all 3,707 listings, running the declared parser in `domain/material_specs.py`:

    dimensions_text 448   weight_value 415   weight_unit 373   length_value 266
    length_m 266          product_code 126   thickness_value 96  manufacturer 34
    branch_count 24

Three measurements decided the shape of this migration:

  1. «وزن» STATES ITS UNIT on brick and profile («گرم», «کیلو») and states NONE on angle and
     channel. So `weight_unit` is nullable and a missing unit stays missing. Defaulting to
     kilograms would be a guess worth a factor of a thousand.

  2. NO SHEET STATES A WEIGHT BASIS. Not one says whether 27 is per branch, per metre or
     per piece. `weight_basis` therefore defaults to nothing and is written as 'unknown',
     and an unknown basis may never enter a conversion. That is also why
     `weight_per_branch_kg` and its siblings are NOT in this migration: each would assert a
     basis nobody stated.

  3. «وزن - کیلوگرم» on ibeam holds a number on 69 rows and an ORIGIN on 34 -- «وارداتی»,
     «ترک-کره». A column named "weight - kilogram" containing "imported" is why the parser
     refuses text instead of coercing it, and why `manufacturer` exists.

WHAT THE PRICE MUST NOW STATE

An observation is evidence, and evidence that cannot say whose product it was or which day
it applied to is not evidence. So three immutable snapshots and a mandatory business date.

    A SNAPSHOT IS NOT A FOREIGN KEY. `provider_item_id` still says which listing this is
    today; `product_name_snapshot` says what it was CALLED when the price was read. A
    supplier renaming a product must not silently rewrite last month's evidence.

    THE BUSINESS DATE IS NOT A TIMESTAMP. `workflow_date_gregorian` is the day the price
    applied; `fetched_at` is the moment BAMBO received the row. Substituting one for the
    other is the failure the constraint below exists to make impossible.

    It is a CHECK against `validation_status`, not a column NOT NULL, and the difference
    matters: this table also holds REJECTED rows, kept as evidence of what a sheet
    contained, and a row rejected because its date was unreadable has no date to store. A
    column NOT NULL would have made that evidence unstorable and pushed the importer into
    inventing a date, which is the very thing being prevented.

NO BACKFILL LIVES HERE, AND ONE OF THEM IS IMPOSSIBLE BY DESIGN

The specification backfill needs the declared per-category parser, which is tested Python
and would be a second, drifting copy if it were rewritten as SQL regex. It runs as a
reviewed, idempotent operation in `scripts/ops/backfill_material_specs.py`.

The observation snapshots cannot be backfilled at all: `price_observations_immutable`
rejects every UPDATE on that table, which is what makes it evidence. The first draft of
this revision tried and was refused, and the refusal was right -- so the snapshots are
enforced on new rows through a NOT VALID constraint and the 3,821 existing rows keep the
NULLs that are the truth about them.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


#: Mass units a weight may be stated in. Registry codes, so a weight and a Finance
#: resource can only agree about a unit deliberately rather than by accident.
_MASS_UNITS = "'g', 'kg', 'ton'"
_LENGTH_UNITS = "'mm', 'cm', 'm'"

UPGRADE_SQL = r"""
-- ------------------------------------------------- 1. typed product specifications

ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS product_code text,
    ADD COLUMN IF NOT EXISTS manufacturer text,
    ADD COLUMN IF NOT EXISTS grade text,
    ADD COLUMN IF NOT EXISTS product_type text,
    ADD COLUMN IF NOT EXISTS dimensions_text text,

    ADD COLUMN IF NOT EXISTS length_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS length_unit text,
    ADD COLUMN IF NOT EXISTS length_m numeric(24, 8),

    ADD COLUMN IF NOT EXISTS width_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS width_unit text,

    ADD COLUMN IF NOT EXISTS height_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS height_unit text,

    ADD COLUMN IF NOT EXISTS thickness_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS thickness_unit text,

    ADD COLUMN IF NOT EXISTS diameter_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS diameter_unit text,

    ADD COLUMN IF NOT EXISTS weight_value numeric(24, 8),
    ADD COLUMN IF NOT EXISTS weight_unit text,
    ADD COLUMN IF NOT EXISTS weight_basis text,

    ADD COLUMN IF NOT EXISTS branch_count numeric(24, 8),
    ADD COLUMN IF NOT EXISTS pieces_per_package numeric(24, 8),
    ADD COLUMN IF NOT EXISTS coverage_m2 numeric(24, 8),
    ADD COLUMN IF NOT EXISTS volume_m3 numeric(24, 8),

    -- Which layer answered. A reader asking "where did this 27 come from" gets a name
    -- rather than a guess, and a value that came from metadata is marked as the legacy
    -- fallback it is.
    ADD COLUMN IF NOT EXISTS spec_source text,
    -- What an arriving sheet said that disagreed with what is stored. A specification is
    -- not append-only like a price, so a disagreement is recorded for a person instead of
    -- being applied: yesterday 22 and today 220 is a parser going wrong far more often
    -- than a product changing weight tenfold.
    ADD COLUMN IF NOT EXISTS spec_conflicts jsonb;

COMMENT ON COLUMN provider_items.weight_basis IS
    'What the weight is PER: branch, meter, piece, package, bag, total, or unknown. No '
    'sheet read so far states one, so ''unknown'' is the honest value -- and an unknown '
    'basis must never be used in a conversion.';
COMMENT ON COLUMN provider_items.weight_unit IS
    'The unit the sheet stated beside the number, or NULL when it stated none. «وزن» gives '
    'a unit on brick and profile and gives none on angle and channel; assuming kilograms '
    'for the second case would be wrong by a factor of a thousand.';
COMMENT ON COLUMN provider_items.length_m IS
    'The length in metres, derived from length_value and length_unit through the '
    'registry''s own ratios. The only normalized column populated, because it is the only '
    'one whose relationship to its raw pair is arithmetic rather than assumed.';
COMMENT ON COLUMN provider_items.dimensions_text IS
    'Verbatim, e.g. «7×33×2.5». Never split into width, height and thickness: nobody has '
    'declared the order, and width-first versus thickness-first is the difference between '
    'a 7mm brick and a 2.5mm one.';
COMMENT ON COLUMN provider_items.metadata IS
    'Uncommon, provider-specific or newly discovered attributes, and the original value of '
    'anything a typed column now mirrors. Not deleted and not demoted: it is the layer a '
    'sheet''s next new column lands in before anybody declares what it means.';

-- Every measurement is positive, finite, and accompanied by its unit when it has one.
-- `numeric` accepts 'NaN' -- and NaN = NaN is TRUE for numeric, unlike float -- so the
-- refusal has to be written out rather than assumed.
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_measures_positive CHECK (
        (length_value    IS NULL OR (length_value    > 0 AND length_value    <> 'NaN'::numeric)) AND
        (length_m        IS NULL OR (length_m        > 0 AND length_m        <> 'NaN'::numeric)) AND
        (width_value     IS NULL OR (width_value     > 0 AND width_value     <> 'NaN'::numeric)) AND
        (height_value    IS NULL OR (height_value    > 0 AND height_value    <> 'NaN'::numeric)) AND
        (thickness_value IS NULL OR (thickness_value > 0 AND thickness_value <> 'NaN'::numeric)) AND
        (diameter_value  IS NULL OR (diameter_value  > 0 AND diameter_value  <> 'NaN'::numeric)) AND
        (weight_value    IS NULL OR (weight_value    > 0 AND weight_value    <> 'NaN'::numeric)) AND
        (coverage_m2     IS NULL OR (coverage_m2     > 0 AND coverage_m2     <> 'NaN'::numeric)) AND
        (volume_m3       IS NULL OR (volume_m3       > 0 AND volume_m3       <> 'NaN'::numeric))),

    ADD CONSTRAINT provider_items_counts_positive CHECK (
        (branch_count       IS NULL OR (branch_count       > 0 AND branch_count       <> 'NaN'::numeric)) AND
        (pieces_per_package IS NULL OR (pieces_per_package > 0 AND pieces_per_package <> 'NaN'::numeric))),

    -- A unit with no value is a statement about nothing. Rejected rather than normalised
    -- away, so an importer that loses the number finds out instead of storing half a fact.
    ADD CONSTRAINT provider_items_unit_needs_value CHECK (
        (length_unit    IS NULL OR length_value    IS NOT NULL) AND
        (width_unit     IS NULL OR width_value     IS NOT NULL) AND
        (height_unit    IS NULL OR height_value    IS NOT NULL) AND
        (thickness_unit IS NULL OR thickness_value IS NOT NULL) AND
        (diameter_unit  IS NULL OR diameter_value  IS NOT NULL) AND
        (weight_unit    IS NULL OR weight_value    IS NOT NULL)),

    ADD CONSTRAINT provider_items_units_are_registry_codes CHECK (
        (weight_unit    IS NULL OR weight_unit    IN (""" + _MASS_UNITS + r""")) AND
        (length_unit    IS NULL OR length_unit    IN (""" + _LENGTH_UNITS + r""")) AND
        (width_unit     IS NULL OR width_unit     IN (""" + _LENGTH_UNITS + r""")) AND
        (height_unit    IS NULL OR height_unit    IN (""" + _LENGTH_UNITS + r""")) AND
        (thickness_unit IS NULL OR thickness_unit IN (""" + _LENGTH_UNITS + r""")) AND
        (diameter_unit  IS NULL OR diameter_unit  IN (""" + _LENGTH_UNITS + r"""))),

    ADD CONSTRAINT provider_items_weight_basis_known CHECK (
        weight_basis IS NULL OR weight_basis IN
            ('branch', 'meter', 'piece', 'package', 'bag', 'total', 'unknown')),

    -- A weight with no basis is a number nobody can convert. Recording 'unknown' is what
    -- makes that explicit rather than leaving the column silently empty.
    ADD CONSTRAINT provider_items_weight_has_basis CHECK (
        weight_value IS NULL OR weight_basis IS NOT NULL),

    ADD CONSTRAINT provider_items_spec_source_known CHECK (
        spec_source IS NULL OR spec_source IN
            ('dedicated_column', 'approved_label', 'legacy_metadata', 'unresolved'));


-- ------------------------------------------- 2. what a price observation must state

ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS product_external_id text,
    ADD COLUMN IF NOT EXISTS product_name_snapshot text,
    ADD COLUMN IF NOT EXISTS provider_name_snapshot text;

COMMENT ON COLUMN price_observations.product_name_snapshot IS
    'What the product was CALLED when this price was read. Not a replacement for '
    'provider_item_id, which still says which listing it is today: a supplier renaming a '
    'product must not silently rewrite last month''s evidence. NULL on rows imported '
    'before this revision -- see the NOT VALID constraint below.';

-- NO BACKFILL, AND THE REASON IS THE TABLE ITSELF.
--
-- `price_observations_immutable` rejects every UPDATE and DELETE on this table: it is
-- append-only financial evidence. The first draft of this revision tried to fill the three
-- snapshots from the rows they snapshot, and the trigger refused -- correctly. Disabling it
-- to write history is exactly the operation that protection exists to prevent, so the
-- snapshots begin with new imports instead.
--
-- 3,821 existing observations therefore carry NULL snapshots. They lose nothing: each
-- still names its provider and its listing by foreign key, and those rows still resolve --
-- a preflight confirmed 0 unresolvable of 3,821. What they cannot say is what the product
-- was CALLED that day, and no honest source for that exists now that the name may have
-- changed since.
--
-- So the constraint is phased, as the strategy for untrustworthy history prescribes:
-- NOT VALID enforces it on every row written from here on while leaving the existing rows
-- alone. It can be VALIDATEd the day none of them remains.
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_states_its_identity CHECK (
        product_external_id IS NOT NULL
        AND btrim(product_external_id) <> ''
        AND product_name_snapshot IS NOT NULL
        AND btrim(product_name_snapshot) <> ''
        AND provider_name_snapshot IS NOT NULL
        AND btrim(provider_name_snapshot) <> '') NOT VALID;

-- The business date is mandatory FOR A VALID OBSERVATION, and the distinction is the
-- point. A column-level NOT NULL was the first draft and it was wrong: this table also
-- holds rows the importer REJECTED, kept as evidence of what a sheet actually contained,
-- and a row rejected precisely BECAUSE its date could not be read has no date to store.
-- NOT NULL would have made the evidence unstorable and pushed the importer into inventing
-- one -- the exact failure this is meant to prevent.
--
-- So the requirement is written against the status: every row anybody may price from
-- states its day, and a rejected row keeps its unreadable original in workflow_date_raw.
-- Validated immediately, because all 3,821 existing rows are valid and all state one.
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_valid_row_has_business_date CHECK (
        validation_status <> 'valid' OR workflow_date_gregorian IS NOT NULL);

COMMENT ON COLUMN price_observations.workflow_date_gregorian IS
    'The day the price applied, canonically. NOT the day it was fetched: fetched_at is '
    'when BAMBO received the row and may be months later. A row that states no business '
    'date is rejected at import rather than given one.';

-- A row the importer accepted as valid must carry a usable price. Rejected rows keep their
-- raw evidence and are not valid observations, so the constraint is written against the
-- status rather than against the column alone -- and it is validated immediately because
-- all 3,821 rows comply.
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_valid_row_has_price CHECK (
        validation_status <> 'valid'
        OR (normalized_price_irr IS NOT NULL
            AND normalized_price_irr >= 0
            AND normalized_price_irr <> 'NaN'::numeric));
"""


DOWNGRADE_SQL = r"""
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_valid_row_has_price,
    DROP CONSTRAINT IF EXISTS price_observations_valid_row_has_business_date,
    DROP CONSTRAINT IF EXISTS price_observations_states_its_identity;
ALTER TABLE price_observations
    DROP COLUMN IF EXISTS provider_name_snapshot,
    DROP COLUMN IF EXISTS product_name_snapshot,
    DROP COLUMN IF EXISTS product_external_id;

ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_spec_source_known,
    DROP CONSTRAINT IF EXISTS provider_items_weight_has_basis,
    DROP CONSTRAINT IF EXISTS provider_items_weight_basis_known,
    DROP CONSTRAINT IF EXISTS provider_items_units_are_registry_codes,
    DROP CONSTRAINT IF EXISTS provider_items_unit_needs_value,
    DROP CONSTRAINT IF EXISTS provider_items_counts_positive,
    DROP CONSTRAINT IF EXISTS provider_items_measures_positive;

ALTER TABLE provider_items
    DROP COLUMN IF EXISTS spec_conflicts,
    DROP COLUMN IF EXISTS spec_source,
    DROP COLUMN IF EXISTS volume_m3,
    DROP COLUMN IF EXISTS coverage_m2,
    DROP COLUMN IF EXISTS pieces_per_package,
    DROP COLUMN IF EXISTS branch_count,
    DROP COLUMN IF EXISTS weight_basis,
    DROP COLUMN IF EXISTS weight_unit,
    DROP COLUMN IF EXISTS weight_value,
    DROP COLUMN IF EXISTS diameter_unit,
    DROP COLUMN IF EXISTS diameter_value,
    DROP COLUMN IF EXISTS thickness_unit,
    DROP COLUMN IF EXISTS thickness_value,
    DROP COLUMN IF EXISTS height_unit,
    DROP COLUMN IF EXISTS height_value,
    DROP COLUMN IF EXISTS width_unit,
    DROP COLUMN IF EXISTS width_value,
    DROP COLUMN IF EXISTS length_m,
    DROP COLUMN IF EXISTS length_unit,
    DROP COLUMN IF EXISTS length_value,
    DROP COLUMN IF EXISTS dimensions_text,
    DROP COLUMN IF EXISTS product_type,
    DROP COLUMN IF EXISTS grade,
    DROP COLUMN IF EXISTS manufacturer,
    DROP COLUMN IF EXISTS product_code;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
