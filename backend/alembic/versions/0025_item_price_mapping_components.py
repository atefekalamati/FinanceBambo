"""the materials a person says an MSP activity consumes, and how much of each

Revision ID: 0025
Revises: 0024

THE PROBLEM THIS SOLVES

0024 gave an estimate line ONE market listing. That is right for a line which IS a material
-- «آرماتوربندی فونداسیون» is rebar -- and wrong for the activities that make up most of a
schedule. «کانال‌کنی» is 500 cubic metres of trenching. It consumes rebar and pipe and
brick, and the MPP file names none of them, because a schedule describes work and not a
bill of materials.

So a line is priced by a LIST of components. Each names a real listing, an official unit,
and how much of it this activity uses.

HOW MUCH, AND WHY THE MODE IS STORED

`usage_mode` says what `usage_quantity` means, and it cannot be inferred from the number:

    per_msp_unit    this much per 1 unit of the activity -- 80 kg of rebar per m3
    total_quantity  this much for the whole activity -- 1,200 m of pipe, however long

The same «500» is either 500 per cubic metre or 500 altogether, and on a 500 m3 trench
those differ by a factor of 500. Only the person entering it knows which, so the mode is
part of what they said.

A USAGE FACTOR IS NOT A UNIT CONVERSION

"80 kg per m3" looks like one and is not. A unit conversion is a fact about units -- a
kilogram is a thousandth of a tonne, on every project that ever runs. "80 kg of rebar per
cubic metre of trench" is a fact about how somebody designed THIS activity, true here and
false next door. `unit_conversions` is never consulted for it and could not answer.

WHAT THE STORED FIGURES ARE, AND ARE NOT

`converted_daily_unit_price_irr`, `component_quantity_decimal`, `component_daily_cost_irr`
and `status` are the figures AS AT APPROVAL. They are evidence of what was agreed, not the
answer to "what does this cost today" -- a daily price moves, which is the entire point of
it, and the read path recomputes from the newest observation. They are stored so a reader
can see that today's number differs from the approved one, and by how much.

VERSIONED, LIKE EVERY DECISION IN THIS SCHEMA

`component_id` is the stable identity of one material across its edits; `id` is one version
of it. Editing supersedes and inserts; deactivating supersedes and inserts a row with
`active = false`. Nothing is ever deleted and nothing is ever rewritten, because a report
issued last week was calculated against the version that was live then.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE TABLE IF NOT EXISTS finance_item_price_mapping_components (
    id uuid PRIMARY KEY,

    -- The stable identity of ONE material across every edit of it. The API's `componentId`.
    -- `id` changes with each version; this does not, which is what lets a user edit "the
    -- rebar line" rather than "version 3 of the rebar line".
    component_id uuid NOT NULL,

    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    estimate_line_id uuid NOT NULL,
    finance_resource_id uuid,

    -- WHICH market listing. The decision this table exists to record.
    provider_item_id uuid NOT NULL,
    -- What the listing was when it was chosen, recorded as read. Not authoritative -- the
    -- listing itself is -- but a sheet that re-categorises a product then disagrees with
    -- the row that approved it, visibly, instead of silently repricing.
    category text,
    provider_id uuid,
    product_type text,

    -- The OFFICIAL unit this component is calculated in, and what the price was stated in
    -- at the time.
    selected_unit text NOT NULL CHECK (btrim(selected_unit) <> ''),
    source_price_unit text,
    source_price_basis text,

    -- How much, and what the number means. See the module docstring.
    usage_mode text CHECK (usage_mode IN ('per_msp_unit', 'total_quantity')),
    -- Nullable: a component can be saved before somebody has measured the usage, and then
    -- reports «نیازمند مقدار مصرف مصالح» rather than being refused. NOT given a default --
    -- a default of 1 or 0 would be this table inventing the one number it must not.
    usage_quantity_decimal numeric(24, 8),
    -- The unit the usage is stated in. Normally `selected_unit`; kept separately because
    -- they are two statements and a later change to one must not silently move the other.
    usage_unit text,

    conversion_status text NOT NULL
        CHECK (conversion_status IN ('automatic', 'factor', 'incompatible', 'unknown')),
    conversion_factor_id uuid REFERENCES provider_item_unit_factors (id),

    -- AS AT APPROVAL. Never read as today's answer; see the module docstring.
    converted_daily_unit_price_irr numeric(24, 4),
    component_quantity_decimal numeric(24, 8),
    component_daily_cost_irr numeric(24, 4),
    status text,

    -- Required and non-blank, for the reason every other decision here carries one: a
    -- component nobody explained is a cost nobody can review.
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),

    -- False means a person retired this material from the line. The row stays, because a
    -- report issued while it was active was calculated with it.
    active boolean NOT NULL DEFAULT true,

    version integer NOT NULL CHECK (version > 0),
    effective_from date NOT NULL,
    superseded_at timestamptz,
    superseded_by uuid,

    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, component_id, version)
);

-- One live version per component. Partial, so superseded versions accumulate freely and
-- only the current one is constrained -- the same shape 0024 uses for its mappings.
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_component_live
    ON finance_item_price_mapping_components
       (organization_id, project_id, component_id)
 WHERE superseded_at IS NULL;

-- "Every material of this line", which is what the panel and the row total both ask.
CREATE INDEX IF NOT EXISTS ix_price_component_by_line
    ON finance_item_price_mapping_components
       (organization_id, project_id, estimate_line_id)
 WHERE superseded_at IS NULL;

-- "What is mapped to this listing" -- asked when a listing goes inactive or its unit moves.
CREATE INDEX IF NOT EXISTS ix_price_component_by_item
    ON finance_item_price_mapping_components
       (organization_id, project_id, provider_item_id)
 WHERE superseded_at IS NULL;

-- Every version of one component, newest first: the history endpoint.
CREATE INDEX IF NOT EXISTS ix_price_component_history
    ON finance_item_price_mapping_components
       (organization_id, project_id, component_id, version DESC);


-- The one UPDATE this table permits: stamping the supersede columns on a row that has
-- none. Everything else about a component is what a total was calculated from.
CREATE OR REPLACE FUNCTION finance_price_component_freeze() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'immutable finance history cannot be updated or deleted';
    END IF;
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION 'this component version is already superseded and cannot change';
    END IF;
    IF NEW.superseded_at IS NULL THEN
        RAISE EXCEPTION 'the only permitted update is superseding this component version';
    END IF;
    IF (NEW.id, NEW.component_id, NEW.organization_id, NEW.project_id,
        NEW.estimate_line_id, NEW.finance_resource_id, NEW.provider_item_id, NEW.category,
        NEW.provider_id, NEW.product_type, NEW.selected_unit, NEW.source_price_unit,
        NEW.source_price_basis, NEW.usage_mode, NEW.usage_quantity_decimal, NEW.usage_unit,
        NEW.conversion_status, NEW.conversion_factor_id,
        NEW.converted_daily_unit_price_irr, NEW.component_quantity_decimal,
        NEW.component_daily_cost_irr, NEW.status, NEW.reason, NEW.active, NEW.version,
        NEW.effective_from, NEW.created_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.id, OLD.component_id, OLD.organization_id, OLD.project_id,
        OLD.estimate_line_id, OLD.finance_resource_id, OLD.provider_item_id, OLD.category,
        OLD.provider_id, OLD.product_type, OLD.selected_unit, OLD.source_price_unit,
        OLD.source_price_basis, OLD.usage_mode, OLD.usage_quantity_decimal, OLD.usage_unit,
        OLD.conversion_status, OLD.conversion_factor_id,
        OLD.converted_daily_unit_price_irr, OLD.component_quantity_decimal,
        OLD.component_daily_cost_irr, OLD.status, OLD.reason, OLD.active, OLD.version,
        OLD.effective_from, OLD.created_by, OLD.created_at)
    THEN
        RAISE EXCEPTION 'a component is corrected by a new version, never by editing one';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER finance_price_component_freeze
    BEFORE UPDATE OR DELETE ON finance_item_price_mapping_components
    FOR EACH ROW EXECUTE FUNCTION finance_price_component_freeze();


-- Every existing one-product mapping becomes that line's first component.
--
-- `per_msp_unit` with a usage of 1 is EXACTLY what the one-product model meant: one unit of
-- the material per unit of the activity, so the cost was the line's quantity times the
-- converted price. The multi-component formula reduces to the same arithmetic, so no
-- existing row changes what it reports.
--
-- The mapping rows themselves are untouched. They stay as the header of their line and as
-- the record of what was decided before components existed.
INSERT INTO finance_item_price_mapping_components
    (id, component_id, organization_id, project_id, estimate_line_id,
     finance_resource_id, provider_item_id, selected_unit, source_price_unit,
     source_price_basis, usage_mode, usage_quantity_decimal, usage_unit,
     conversion_status, conversion_factor_id, reason, active, version, effective_from,
     created_by, created_at)
SELECT gen_random_uuid(), gen_random_uuid(), m.organization_id, m.project_id,
       m.estimate_line_id, m.finance_resource_id, m.provider_item_id, m.selected_unit,
       m.source_price_unit, m.source_price_basis,
       'per_msp_unit', 1, m.selected_unit,
       m.conversion_status, m.conversion_factor_id,
       'انتقال از اتصال تک‌محصولی: یک واحد مصالح به ازای هر واحد فعالیت',
       true, 1, m.effective_from, m.created_by, m.created_at
  FROM finance_item_price_mappings m
 WHERE m.superseded_at IS NULL
   AND m.estimate_line_id IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM finance_item_price_mapping_components c
        WHERE c.organization_id = m.organization_id
          AND c.project_id = m.project_id
          AND c.estimate_line_id = m.estimate_line_id
          AND c.superseded_at IS NULL);
"""


DOWNGRADE_SQL = r"""
DROP TRIGGER IF EXISTS finance_price_component_freeze
    ON finance_item_price_mapping_components;
DROP FUNCTION IF EXISTS finance_price_component_freeze();
DROP INDEX IF EXISTS ix_price_component_history;
DROP INDEX IF EXISTS ix_price_component_by_item;
DROP INDEX IF EXISTS ix_price_component_by_line;
DROP INDEX IF EXISTS ux_price_component_live;
DROP TABLE IF EXISTS finance_item_price_mapping_components;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
