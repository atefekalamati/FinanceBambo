"""the quantity a schedule states today, and the rules that let a price be read in it

Revision ID: 0026
Revises: 0025

THREE THINGS, AND WHY THEY ARRIVE TOGETHER

They are one workflow. A line has a quantity and a unit; a product has a price and another
unit; and between them sits either a rule or an unanswered question. Splitting them across
migrations would leave a schema that can pose the question and not record the answer.

1. THE DAILY QUANTITY, ON THE SOURCE ROW

`finance_mpp_rows` already holds what the file said about one assignment, versioned by
`source_version_id`. The daily quantity is another thing the file says, so it belongs
there: re-reading the same bytes rewrites the same version and a past version keeps what it
always said.

It is NULLABLE with NO DEFAULT, and that is load-bearing. A default of zero would make
every line's daily estimate zero on the day this migration ran, and zero is a figure a
reader acts on.

    WHAT «۰» MEANS IN AN MS PROJECT NUMBER COLUMN

    Measured on this project's own schedule: the three columns whose names promise a
    volume -- «حجم اولیه», «احجام کاری», «حجم انجام شده» -- are stated on all 328 tasks and
    are ZERO on all 328. MS Project writes 0.0 into every Number column nobody filled, and
    MPXJ hands that back indistinguishably from a deliberate zero.

    So the importer records a daily quantity only where the column states something OTHER
    than zero, and a zero there is recorded as "the file said nothing". A zero somebody
    types through the API is a different fact and is kept as the zero it is. Doing
    otherwise would read an empty column as "this line uses none today" and take every
    daily estimate on the project to zero.

2. THE CONVERSION RULES

`unit_conversions` is project-scoped with no approval; `provider_item_unit_factors` is
product-scoped with approval but cannot express a category, a provider or a site-wide
statement. Neither can say "1 branch = 22 kg, for THIS product, approved by that person,
superseded on that date" alongside "1 ton = 1000 kg, everywhere, forever".

So one table with an explicit `scope_type`, and a check that the scope columns match it.
Both existing tables stay exactly as they are and keep being read; this is the layer above
them, not a replacement.

    THE RULE IS A STATEMENT ABOUT QUANTITY: `1 from_unit = factor to_unit`.

    The price arithmetic is derived from it in one domain function. Storing "the price
    multiplier" instead would let one call site multiply where another divides, and on the
    reference product that is a factor of 484.

    FORMULA-READY, NOT FORMULA-EXECUTING. `conversion_method` admits 'formula' and
    `formula_definition` is jsonb, so a future thickness-times-density rule has somewhere
    to live. Nothing evaluates one, and no column here ever holds text that anything
    executes.

3. THE UNRESOLVED MISMATCHES

A mismatch that exists only in an API response is a question nobody can be assigned. This
table makes it a record with a first sighting, a last sighting, a count and a resolution.

    ONE OPEN ISSUE PER LINE, PRODUCT AND UNIT PAIR. A partial unique index enforces it, so
    a preview refreshed two hundred times leaves one row with `occurrence_count = 200`
    rather than two hundred rows. Resolved rows are never deleted and never re-opened: a
    later mismatch of the same shape is a new row, because it happened at a different time
    for a different reason.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- ------------------------------------------------------------------ 1. daily quantity

ALTER TABLE finance_mpp_rows
    ADD COLUMN IF NOT EXISTS source_daily_quantity numeric(24, 8),
    ADD COLUMN IF NOT EXISTS source_daily_quantity_field text;

COMMENT ON COLUMN finance_mpp_rows.source_daily_quantity IS
    'The quantity the schedule states for TODAY, from its own dedicated column. NULL means '
    'the file states none -- never zero-by-default. A zero read from an MS Project Number '
    'column is indistinguishable from an empty one, so the importer records only a '
    'non-zero value here; a zero entered by a person is a different fact and is kept.';

COMMENT ON COLUMN finance_mpp_rows.source_daily_quantity_field IS
    'The planner''s own ALIAS for the column the value came from, never the NumberN index: '
    'the same meaning lands on a different index in the next file, so the alias is the '
    'contract and is recorded with the value.';


-- --------------------------------------------------------------- 2. conversion rules

CREATE TABLE IF NOT EXISTS finance_unit_conversion_rules (
    id uuid PRIMARY KEY,

    -- Tenancy. `project_id` is NULL for a rule that outlives any one project; the check
    -- below ties which of these may be null to the declared scope.
    organization_id uuid NOT NULL,
    project_id text,

    -- What the rule is about, narrowing left to right. The resolver reads them in this
    -- order and the most specific approved rule wins.
    provider_item_id uuid,
    provider_id uuid,
    category text,

    scope_type text NOT NULL CHECK (scope_type IN
        ('global', 'organization', 'project', 'provider', 'category', 'provider_item')),

    -- `1 from_unit = factor_value to_unit`. One direction, stated once. See the docstring.
    from_unit text NOT NULL CHECK (btrim(from_unit) <> ''),
    to_unit text NOT NULL CHECK (btrim(to_unit) <> ''),
    CONSTRAINT finance_conversion_rule_units_differ CHECK (from_unit <> to_unit),

    conversion_method text NOT NULL DEFAULT 'factor'
        CHECK (conversion_method IN ('factor', 'formula')),
    -- Strictly positive: a zero or negative factor is not a conversion, and a zero would
    -- be a division by zero the moment a price went through it.
    factor_value numeric(32, 12) CHECK (factor_value IS NULL OR factor_value > 0),
    formula_definition jsonb,
    formula_schema_version text,

    -- Recorded rather than inferred, so a reader never has to work out which way round the
    -- number goes. 'quantity' is the only value the domain applies today.
    direction_definition text NOT NULL DEFAULT 'one_from_unit_equals_factor_to_unit',

    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'rejected', 'superseded')),

    version integer NOT NULL CHECK (version > 0),
    effective_from date NOT NULL,
    effective_to date,
    supersedes_rule_id uuid REFERENCES finance_unit_conversion_rules (id),

    -- Where the number came from. A factor with no evidence is somebody's memory.
    evidence_source text,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),

    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_by uuid,
    approved_at timestamptz,

    -- A factor rule needs a factor; a formula rule needs a formula. Neither may pretend.
    CONSTRAINT finance_conversion_rule_method_payload CHECK (
        (conversion_method = 'factor' AND factor_value IS NOT NULL)
     OR (conversion_method = 'formula' AND formula_definition IS NOT NULL)),

    -- The scope columns must say what the scope type says. A 'provider_item' rule without
    -- a provider item is a product rule that applies to every product.
    CONSTRAINT finance_conversion_rule_scope_columns CHECK (
        CASE scope_type
            WHEN 'global' THEN project_id IS NULL AND provider_item_id IS NULL
                           AND provider_id IS NULL AND category IS NULL
            WHEN 'organization' THEN project_id IS NULL AND provider_item_id IS NULL
                                 AND provider_id IS NULL AND category IS NULL
            WHEN 'project' THEN project_id IS NOT NULL AND provider_item_id IS NULL
                            AND provider_id IS NULL AND category IS NULL
            WHEN 'provider' THEN provider_id IS NOT NULL AND provider_item_id IS NULL
            WHEN 'category' THEN category IS NOT NULL AND provider_item_id IS NULL
            WHEN 'provider_item' THEN provider_item_id IS NOT NULL
            ELSE false
        END),

    -- An approved rule records who approved it. Approval with no approver is a status
    -- somebody set, not a decision somebody made.
    CONSTRAINT finance_conversion_rule_approval CHECK (
        (status <> 'approved') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),

    CONSTRAINT finance_conversion_rule_effective_order CHECK (
        effective_to IS NULL OR effective_to >= effective_from)
);

-- One ACTIVE rule per exact scope and unit pair. Partial over the approved-and-open rows,
-- so superseded versions accumulate freely and only the live one is constrained. Without
-- it, two approved rules could answer the same question differently and which one applied
-- would depend on row order.
CREATE UNIQUE INDEX IF NOT EXISTS ux_finance_conversion_rule_active
    ON finance_unit_conversion_rules
       (organization_id, scope_type,
        coalesce(project_id, ''), coalesce(provider_item_id, '00000000-0000-0000-0000-000000000000'::uuid),
        coalesce(provider_id, '00000000-0000-0000-0000-000000000000'::uuid),
        coalesce(category, ''), from_unit, to_unit)
 WHERE status = 'approved' AND effective_to IS NULL;

-- The resolver's own lookup: "which approved rule crosses these two units for me".
CREATE INDEX IF NOT EXISTS ix_finance_conversion_rule_lookup
    ON finance_unit_conversion_rules
       (organization_id, from_unit, to_unit, scope_type)
 WHERE status = 'approved';

CREATE INDEX IF NOT EXISTS ix_finance_conversion_rule_history
    ON finance_unit_conversion_rules (organization_id, supersedes_rule_id, version DESC);

COMMENT ON TABLE finance_unit_conversion_rules IS
    'Scoped, approved, versioned statements of the form `1 from_unit = factor to_unit`. '
    'The price conversion is DERIVED from this in the domain, never stored, so no call '
    'site can get the direction backwards. Formula-ready and formula-executing are '
    'different things: conversion_method admits formula and nothing evaluates one.';

COMMENT ON COLUMN finance_unit_conversion_rules.scope_type IS
    'How broadly this rule may be believed. `global` is not a synonym for safe: kg to ton '
    'is a fact about units and is safe everywhere; branch to kg is a fact about one '
    'product and must be scoped to it.';


-- ---------------------------------------------------------- 3. unresolved mismatches

CREATE TABLE IF NOT EXISTS finance_unit_conversion_issues (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,

    estimate_line_id uuid,
    finance_resource_id uuid,
    provider_item_id uuid,

    -- The schedule's own identifiers, carried so the issue stays legible after a re-import
    -- has issued new database ids.
    source_task_uid integer,
    source_assignment_uid integer,
    source_resource_uid integer,

    resource_unit text,
    daily_price_unit text,

    error_code text NOT NULL CHECK (btrim(error_code) <> ''),
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved', 'obsolete')),

    first_detected_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_detected_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),

    resolved_at timestamptz,
    resolved_by uuid,
    resolution_rule_id uuid REFERENCES finance_unit_conversion_rules (id),

    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT finance_conversion_issue_resolution CHECK (
        (status <> 'resolved') OR resolved_at IS NOT NULL)
);

-- One OPEN issue per line, product and unit pair. A preview refreshed two hundred times
-- leaves one row counting to two hundred, not two hundred rows.
CREATE UNIQUE INDEX IF NOT EXISTS ux_finance_conversion_issue_open
    ON finance_unit_conversion_issues
       (organization_id, project_id,
        coalesce(estimate_line_id, '00000000-0000-0000-0000-000000000000'::uuid),
        coalesce(provider_item_id, '00000000-0000-0000-0000-000000000000'::uuid),
        coalesce(resource_unit, ''), coalesce(daily_price_unit, ''), error_code)
 WHERE status = 'open';

CREATE INDEX IF NOT EXISTS ix_finance_conversion_issue_by_project
    ON finance_unit_conversion_issues (organization_id, project_id, status, last_detected_at DESC);

CREATE INDEX IF NOT EXISTS ix_finance_conversion_issue_by_line
    ON finance_unit_conversion_issues (organization_id, project_id, estimate_line_id);

COMMENT ON TABLE finance_unit_conversion_issues IS
    'Unit mismatches that blocked a daily estimate, as records rather than as messages. '
    'Append-and-update, never delete: a resolved issue is the evidence that somebody '
    'answered the question, and deleting it loses why the figure changed.';
"""


DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ix_finance_conversion_issue_by_line;
DROP INDEX IF EXISTS ix_finance_conversion_issue_by_project;
DROP INDEX IF EXISTS ux_finance_conversion_issue_open;
DROP TABLE IF EXISTS finance_unit_conversion_issues;

DROP INDEX IF EXISTS ix_finance_conversion_rule_history;
DROP INDEX IF EXISTS ix_finance_conversion_rule_lookup;
DROP INDEX IF EXISTS ux_finance_conversion_rule_active;
DROP TABLE IF EXISTS finance_unit_conversion_rules;

ALTER TABLE finance_mpp_rows
    DROP COLUMN IF EXISTS source_daily_quantity_field,
    DROP COLUMN IF EXISTS source_daily_quantity;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
