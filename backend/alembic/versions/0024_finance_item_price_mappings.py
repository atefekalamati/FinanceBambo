"""which daily-price product a schedule item is actually priced from

Revision ID: 0024
Revises: 0023

THE PROBLEM THIS SOLVES

Two modules know different halves of one question. The MSP/MPP side knows that an activity
consumes «آرماتور» and how much of it. The daily-price side knows that «میلگرد ساده 25 یزد»
from Mashhad Foolad costs 101,460 toman per کیلو today. Nothing connects them, and nothing
should connect them by itself: the names do not match, one sheet lists 622 rebar products,
and picking by resemblance is how an estimate ends up priced from the wrong steel.

So the connection is a decision a person makes, and this table is where it is recorded.

WHAT ONE ROW SAYS

"For THIS estimate line, the material actually used is THAT provider listing, the official
unit for calculating it is this one, and here is the factor if the two units cross a
dimension." Four statements, one author, one moment, one reason.

WHY THE UNIT IS STORED HERE AND NOT DERIVED

`selected_unit` is the OFFICIAL CALCULATION UNIT: the unit the daily price is converted into
and the unit the quantity is read in. It is not the sheet's unit and not the schedule's --
either might be missing, wrong, or merely `initials`. It is a choice, and a choice that
changes what every figure downstream means has to be stored where it can be read back and
attributed.

`source_price_unit` and `source_price_basis` are recorded AS READ at the moment of mapping,
beside it. They are not used for arithmetic -- the live observation is -- they exist so a
later reader can see which crossing was approved. A sheet that silently changes its unit
then disagrees with the row that approved it, visibly, instead of quietly repricing.

VERSIONED, AND WHY UPDATE IS ALMOST ENTIRELY REFUSED

Changing a mapping changes what an item costs. The previous answer has to stay readable,
because a report issued last week was calculated against it. So a change is a NEW version
and the old row is superseded rather than edited.

`price_versions` and `unit_conversions` use `finance_reject_mutation`, which refuses UPDATE
outright -- but they carry no `superseded_at` to write. `provider_item_labels` and
`provider_item_unit_factors` do carry one, and carry no trigger at all, so any column on them
can be rewritten. This table takes the stricter half of each: it has the supersede columns
AND a trigger, and the trigger allows exactly one kind of UPDATE -- stamping `superseded_at`
and `superseded_by` on a row that has none. Every other column is frozen, and DELETE is
refused outright.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE TABLE IF NOT EXISTS finance_item_price_mappings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,

    -- WHAT is priced. Exactly one of the two, never both and never neither: a mapping for
    -- "this line" and a mapping for "this item everywhere" are different promises, and a
    -- row claiming both would be read differently by the two readers that want them.
    estimate_line_id uuid,
    finance_resource_id uuid,

    -- The schedule's own identifiers, copied where the row has them. Not a foreign key:
    -- they name a fact in a file, they survive a re-import that issues new database ids,
    -- and a mapping made against one source version stays legible against the next.
    source_assignment_uid integer,
    source_task_uid integer,
    source_resource_uid integer,

    -- WHICH listing it is priced from. The decision this table exists for.
    provider_item_id uuid NOT NULL,

    -- The OFFICIAL CALCULATION UNIT. Validated against the unit registry in the service,
    -- not here: the registry is one Python dict and a CHECK listing its members would be a
    -- second copy of it that could disagree.
    selected_unit text NOT NULL CHECK (btrim(selected_unit) <> ''),

    -- What the price was stated in when this mapping was approved, recorded as read.
    source_price_unit text,
    source_price_basis text,

    -- What the crossing needs. 'automatic' means the registry can do it; 'factor' means a
    -- product-specific measurement is required and `conversion_factor_id` names it;
    -- 'incompatible' records that somebody looked and the two cannot be crossed at all,
    -- which is worth storing so the same question is not reopened every day.
    conversion_status text NOT NULL
        CHECK (conversion_status IN ('automatic', 'factor', 'incompatible', 'unknown')),
    conversion_factor_id uuid REFERENCES provider_item_unit_factors (id),

    version integer NOT NULL CHECK (version > 0),
    effective_from date NOT NULL,
    superseded_at timestamptz,
    superseded_by uuid,

    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Required and non-blank, for the same reason `price_versions.reason` is: a decision
    -- nobody explained is a decision nobody can review.
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),

    -- One of the two subjects, never both.
    CONSTRAINT finance_item_price_mappings_one_subject CHECK (
        (estimate_line_id IS NOT NULL) <> (finance_resource_id IS NOT NULL)),
    -- A factor is named exactly when the status says one is needed.
    CONSTRAINT finance_item_price_mappings_factor_matches_status CHECK (
        (conversion_status = 'factor') = (conversion_factor_id IS NOT NULL)),

    UNIQUE (organization_id, project_id, id)
);

-- One live mapping per subject. Partial, so superseded rows accumulate freely and only the
-- current one is constrained -- the same shape `price_observations` uses for idempotence.
CREATE UNIQUE INDEX IF NOT EXISTS ux_item_price_mapping_current_line
    ON finance_item_price_mappings (organization_id, project_id, estimate_line_id)
 WHERE superseded_at IS NULL AND estimate_line_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_item_price_mapping_current_resource
    ON finance_item_price_mappings (organization_id, project_id, finance_resource_id)
 WHERE superseded_at IS NULL AND finance_resource_id IS NOT NULL;

-- Reading the table back: every version of one subject, newest first.
CREATE INDEX IF NOT EXISTS ix_item_price_mapping_history
    ON finance_item_price_mappings (organization_id, project_id, estimate_line_id,
                                    version DESC);

-- "What is mapped to this listing" -- asked when a listing goes inactive or its unit moves.
CREATE INDEX IF NOT EXISTS ix_item_price_mapping_by_item
    ON finance_item_price_mappings (organization_id, project_id, provider_item_id)
 WHERE superseded_at IS NULL;


-- The one UPDATE this table permits: stamping the supersede columns on a row that has
-- none. Everything else about a mapping is what a report was calculated against.
CREATE OR REPLACE FUNCTION finance_item_price_mapping_freeze() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'immutable finance history cannot be updated or deleted';
    END IF;
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION 'this mapping version is already superseded and cannot change';
    END IF;
    IF NEW.superseded_at IS NULL THEN
        RAISE EXCEPTION 'the only permitted update is superseding this mapping version';
    END IF;
    -- Every other column must be identical. Listed rather than compared as a whole row:
    -- `NEW IS DISTINCT FROM OLD` would also be true for the supersede itself.
    IF (NEW.id, NEW.organization_id, NEW.project_id, NEW.estimate_line_id,
        NEW.finance_resource_id, NEW.source_assignment_uid, NEW.source_task_uid,
        NEW.source_resource_uid, NEW.provider_item_id, NEW.selected_unit,
        NEW.source_price_unit, NEW.source_price_basis, NEW.conversion_status,
        NEW.conversion_factor_id, NEW.version, NEW.effective_from, NEW.created_by,
        NEW.created_at, NEW.reason)
       IS DISTINCT FROM
       (OLD.id, OLD.organization_id, OLD.project_id, OLD.estimate_line_id,
        OLD.finance_resource_id, OLD.source_assignment_uid, OLD.source_task_uid,
        OLD.source_resource_uid, OLD.provider_item_id, OLD.selected_unit,
        OLD.source_price_unit, OLD.source_price_basis, OLD.conversion_status,
        OLD.conversion_factor_id, OLD.version, OLD.effective_from, OLD.created_by,
        OLD.created_at, OLD.reason)
    THEN
        RAISE EXCEPTION 'a mapping is corrected by a new version, never by editing one';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER finance_item_price_mappings_freeze
    BEFORE UPDATE OR DELETE ON finance_item_price_mappings
    FOR EACH ROW EXECUTE FUNCTION finance_item_price_mapping_freeze();
"""


DOWNGRADE_SQL = r"""
DROP TRIGGER IF EXISTS finance_item_price_mappings_freeze ON finance_item_price_mappings;
DROP FUNCTION IF EXISTS finance_item_price_mapping_freeze();
DROP INDEX IF EXISTS ix_item_price_mapping_by_item;
DROP INDEX IF EXISTS ix_item_price_mapping_history;
DROP INDEX IF EXISTS ux_item_price_mapping_current_resource;
DROP INDEX IF EXISTS ux_item_price_mapping_current_line;
DROP TABLE IF EXISTS finance_item_price_mappings;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
