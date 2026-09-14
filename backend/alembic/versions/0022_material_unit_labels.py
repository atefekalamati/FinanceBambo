"""what a person decides about a material listing: its unit, and its missing metadata

Revision ID: 0022
Revises: 0021

TWO KINDS OF DECISION, AND WHY THEY ARE NOT ONE TABLE

`material_unit_settings` already existed from 0021 and answered one question: which unit a
CATEGORY is displayed in. That is a broad decision -- all rebar in kilograms -- and it is
kept, widened, and still append-only.

What it cannot answer is the narrow one. The sheet states no unit for six of its seven
categories, so «لوله پلی اتیلن ۱۱۰» has a price and no basis at all, and no category-wide
setting can supply one: the row next to it might be sold by the branch. That is the gap
`provider_item_labels` fills. It is configuration a person writes ABOUT one listing --
what the thing is, what its price is per, what Finance resource it belongs to -- and it
never touches the imported row it describes.

Keeping them apart matters because they are superseded on different rhythms. A category's
unit changes when a team changes how it reports; a listing's label changes when somebody
looks at that listing and works out what it is.

APPEND-ONLY, LIKE EVERY OTHER DECISION IN THIS SCHEMA

Neither table is ever updated in place. A correction is a new version, the previous one
stays readable, and `superseded_at` is set on the row it replaced so "what did we believe
in Shahrivar" has an answer. `price_versions`, `unit_conversions` and
`estimate_revisions` all work this way and there is no reason for these to differ.

WHAT THIS REVISION DOES NOT DO

It writes no data. It creates no label, no unit setting and no factor -- every row in both
tables will have been put there by a person, which is the entire point of them. It does not
touch `price_observations`, `price_versions`, `estimate_lines`, `invoices` or
`report_snapshots`, and it disables no trigger.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- ------------------------------------------------------- the category-wide unit choice
-- 0021 created this with category, resource and display_unit. Three things were missing
-- and each one is a question somebody asks of a row they are looking at.
ALTER TABLE material_unit_settings
    -- Which listing, when the decision is about one rather than a whole category. Null
    -- means the setting is category-wide, which is what every 0021 row is.
    ADD COLUMN IF NOT EXISTS provider_item_id uuid,
    -- What the price was taken to be per, when a person had to say. Separate from
    -- display_unit because they are different claims: one is about the source, one is
    -- about the screen.
    ADD COLUMN IF NOT EXISTS source_unit text,
    ADD COLUMN IF NOT EXISTS source_basis text,
    -- 'dimension' when units alone can bridge it, 'product_factor' when a measurement of
    -- this product is required. Recorded rather than inferred so a reader can see which
    -- kind of conversion the decision assumed.
    ADD COLUMN IF NOT EXISTS conversion_mode text,
    -- From when this decision applies. Defaulted for the existing rows to the day they
    -- were created, which is what they meant.
    ADD COLUMN IF NOT EXISTS effective_from date,
    ADD COLUMN IF NOT EXISTS superseded_at timestamptz,
    ADD COLUMN IF NOT EXISTS superseded_by uuid;

ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_conversion_mode_check;
ALTER TABLE material_unit_settings
    ADD CONSTRAINT material_unit_settings_conversion_mode_check
    CHECK (conversion_mode IS NULL
        OR conversion_mode IN ('dimension', 'product_factor', 'none'));

ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_item_fk;
ALTER TABLE material_unit_settings
    ADD CONSTRAINT material_unit_settings_item_fk
    FOREIGN KEY (organization_id, project_id, provider_item_id)
        REFERENCES provider_items (organization_id, project_id, id) ON DELETE RESTRICT;

-- A setting is about a category, or a resource, or one listing -- never two at once.
ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_one_scope_check;
ALTER TABLE material_unit_settings
    ADD CONSTRAINT material_unit_settings_one_scope_check
    CHECK (num_nonnulls(resource_id, provider_item_id) <= 1);

CREATE UNIQUE INDEX IF NOT EXISTS ux_material_unit_settings_item_version
    ON material_unit_settings (organization_id, project_id, provider_item_id, version)
    WHERE provider_item_id IS NOT NULL;

-- ----------------------------------------------------------- what a person says a row IS
-- Configuration, not an observation. Nothing here is a price and nothing here can become
-- one: a label says what a thing is and what its price is per, and the price itself stays
-- exactly as it was imported.
CREATE TABLE IF NOT EXISTS provider_item_labels (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_item_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),

    -- What a person calls it, when the supplier's own name is not usable. The imported
    -- `external_name` is never overwritten; this sits beside it.
    label text CHECK (label IS NULL OR length(btrim(label)) > 0),
    display_name text CHECK (display_name IS NULL OR length(btrim(display_name)) > 0),
    category text CHECK (category IS NULL OR length(btrim(category)) > 0),
    product_type text CHECK (product_type IS NULL OR length(btrim(product_type)) > 0),

    -- The two unit facts a sheet row can be missing. `source_unit` is a Finance unit code;
    -- `source_basis` is the commercial basis in words when it is not a unit at all.
    source_unit text CHECK (source_unit IS NULL OR length(btrim(source_unit)) > 0),
    source_basis text CHECK (source_basis IS NULL OR length(btrim(source_basis)) > 0),
    target_unit text CHECK (target_unit IS NULL OR length(btrim(target_unit)) > 0),

    -- The Finance resource this listing is the market price OF. Unapproved by default:
    -- a mapping nobody confirmed must not silently become the source of a price.
    finance_resource_id uuid,
    mapping_approved boolean NOT NULL DEFAULT false,
    mapping_approved_by uuid,
    mapping_approved_at timestamptz,

    active boolean NOT NULL DEFAULT true,
    notes text,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superseded_at timestamptz,
    superseded_by uuid,

    -- An approval is a person and a moment, or it is not an approval.
    CHECK ((mapping_approved = false AND mapping_approved_by IS NULL
            AND mapping_approved_at IS NULL)
        OR (mapping_approved = true AND mapping_approved_by IS NOT NULL
            AND mapping_approved_at IS NOT NULL)),
    -- And an approved mapping has to name something to map to.
    CHECK (mapping_approved = false OR finance_resource_id IS NOT NULL),

    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, provider_item_id, version),
    FOREIGN KEY (organization_id, project_id, provider_item_id)
        REFERENCES provider_items (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, finance_resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_provider_item_labels_current
    ON provider_item_labels (organization_id, project_id, provider_item_id, version DESC);

CREATE INDEX IF NOT EXISTS ix_provider_item_labels_resource
    ON provider_item_labels (organization_id, project_id, finance_resource_id)
    WHERE finance_resource_id IS NOT NULL;

-- ----------------------------------------------------- product factors, made supersedable
-- 0021 versioned these but had no way to say a version had been withdrawn. A factor that
-- turns out to be wrong must be retractable without deleting the record that it was once
-- believed -- the whole reason these are append-only.
ALTER TABLE provider_item_unit_factors
    ADD COLUMN IF NOT EXISTS superseded_at timestamptz,
    ADD COLUMN IF NOT EXISTS superseded_by uuid,
    ADD COLUMN IF NOT EXISTS factor_type text,
    ADD COLUMN IF NOT EXISTS approved_by uuid,
    ADD COLUMN IF NOT EXISTS approved_at timestamptz;

ALTER TABLE provider_item_unit_factors
    DROP CONSTRAINT IF EXISTS provider_item_unit_factors_factor_type_check;
ALTER TABLE provider_item_unit_factors
    ADD CONSTRAINT provider_item_unit_factors_factor_type_check
    CHECK (factor_type IS NULL
        OR factor_type IN ('weight_per_piece', 'weight_per_branch', 'length_per_branch',
                           'mass_per_bag', 'area_per_piece', 'volume_per_piece', 'other'));
"""


DOWNGRADE_SQL = r"""
ALTER TABLE provider_item_unit_factors
    DROP CONSTRAINT IF EXISTS provider_item_unit_factors_factor_type_check;
ALTER TABLE provider_item_unit_factors
    DROP COLUMN IF EXISTS approved_at,
    DROP COLUMN IF EXISTS approved_by,
    DROP COLUMN IF EXISTS factor_type,
    DROP COLUMN IF EXISTS superseded_by,
    DROP COLUMN IF EXISTS superseded_at;

DROP INDEX IF EXISTS ix_provider_item_labels_resource;
DROP INDEX IF EXISTS ix_provider_item_labels_current;
DROP TABLE IF EXISTS provider_item_labels;

DROP INDEX IF EXISTS ux_material_unit_settings_item_version;
ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_one_scope_check;
ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_item_fk;
ALTER TABLE material_unit_settings
    DROP CONSTRAINT IF EXISTS material_unit_settings_conversion_mode_check;
ALTER TABLE material_unit_settings
    DROP COLUMN IF EXISTS superseded_by,
    DROP COLUMN IF EXISTS superseded_at,
    DROP COLUMN IF EXISTS effective_from,
    DROP COLUMN IF EXISTS conversion_mode,
    DROP COLUMN IF EXISTS source_basis,
    DROP COLUMN IF EXISTS source_unit,
    DROP COLUMN IF EXISTS provider_item_id;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
