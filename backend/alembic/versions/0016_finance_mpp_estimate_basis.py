"""The quantity and the rate the file states, and a place to record them for a line that predates them

Revision ID: 0016
Revises: 0015

WHAT THE FILE ACTUALLY STATES

MS Project keeps a material assignment's PHYSICAL quantity in its own field -- MPXJ's
`assignment.getMaterial()` -- which is neither `Work` (time, in hours) nor `Units` (the
same quantity scaled by a hundred) nor `Cost` (a total). The resource carries the price of
one such unit in `resource.getStandardRate()`. On the reference schedule the two multiply
out exactly:

    assignment 9703 «تجهیز کارگاه مستمر» / resource 155 «تجهیز مستمر»
        Material 1 واحد  x  StandardRate 12,565,115,391  =  Cost 12,565,115,391

and that holds for all 289 material assignments in the file (143 to the last digit, 146
inside a millionth, none outside it). That identity is the evidence that the rate is per
material unit rather than per hour, and `source_rate_basis` records it per row: a row whose
numbers do not multiply out gets NULL there and is not treated as an estimate basis.

The file's other 438 assignments belong to WORK resources: they state no Material at all and
their standard rate is zero. They get NULL in all three columns, which is the honest answer
-- a cost with no quantity cannot yield a unit rate, and dividing one by the other would be
inventing a number.

WHY A SEPARATE TABLE FOR OLD LINES

`estimate_original_fields_immutable` refuses any UPDATE that changes `original_quantity` or
`original_unit_price_irr`, and it must keep refusing: the original estimate is the record of
what was estimated, and rewriting it would erase that. But the 715 lines mapped before this
migration were created with both columns NULL, and the values were in the file all along.

`estimate_line_source_completions` records those values ALONGSIDE the line instead of inside
it: which source version they came from, that version's sha256, the assignment they belong
to, when they were recorded and by whom. The line's own columns keep saying what they always
said -- NULL, nothing was recorded at creation -- and a reader that wants the effective
original takes the completion when the column is NULL. Nothing is overwritten, the provenance
travels with the value, and a line that HAS an original keeps it: the unique index is on the
line, and a completion is only ever inserted where the column is NULL.

A completion is not a revision. A revision says the estimate changed; this says the estimate
was always this and was written down late. They are different facts and they live in
different tables, so `estimate_revisions` still means only the first thing.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_mpp_rows
    -- The physical quantity the file states for THIS assignment (MPXJ's Material field).
    ADD COLUMN source_material_quantity numeric,
    -- What one such unit costs, per the resource's standard rate, in rials.
    ADD COLUMN source_resource_rate_irr numeric,
    -- Why the rate may be read as a per-unit price at all, or NULL when it may not.
    ADD COLUMN source_rate_basis text;

COMMENT ON COLUMN finance_mpp_rows.source_material_quantity IS
    'The physical quantity the file states for this assignment (MPXJ Material), in '
    '`resource_unit`. NOT `source_assignment_units`, which is this number scaled by a '
    'hundred, and NOT `quantity`, which is the approved financial quantity.';

COMMENT ON COLUMN finance_mpp_rows.source_resource_rate_irr IS
    'The resource''s standard rate in rials per unit of `resource_unit` (the file''s toman '
    'rate x10). NULL when the file states none; a real zero stays zero.';

COMMENT ON COLUMN finance_mpp_rows.source_rate_basis IS
    '`material_unit` when the resource is MATERIAL and quantity x rate reproduces the '
    'assignment''s own cost -- the proof that the rate is per material unit. NULL when '
    'nothing proves it, and then the rate is not an estimate basis.';

CREATE TABLE estimate_line_source_completions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    estimate_line_id uuid NOT NULL REFERENCES estimate_lines (id),
    -- The version the values are FROM. A later import does not get to rewrite history:
    -- the row is written once and the unique index below is what enforces that.
    source_version_id uuid NOT NULL REFERENCES finance_mpp_source_versions (id),
    source_sha256 text NOT NULL,
    source_task_uid integer,
    source_assignment_uid integer NOT NULL,
    source_resource_uid integer,
    quantity numeric,
    quantity_unit text,
    unit_price_irr numeric,
    currency text NOT NULL DEFAULT 'IRR',
    basis text NOT NULL,
    completed_by uuid NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT estimate_line_source_completions_line_key UNIQUE (estimate_line_id),
    CONSTRAINT estimate_line_source_completions_scope_key
        UNIQUE (organization_id, project_id, id),
    -- A completion that states neither figure would say nothing and mean nothing.
    CONSTRAINT estimate_line_source_completions_states_something
        CHECK (quantity IS NOT NULL OR unit_price_irr IS NOT NULL)
);

COMMENT ON TABLE estimate_line_source_completions IS
    'The original quantity and rate a mapped estimate line was created without, recorded '
    'from the exact source version it was mapped from. One row per line, ever: the effective '
    'original is the line''s own column when it has one and this otherwise.';

-- Both read paths join by line inside a tenant; the unique index on the line already
-- serves the lookup, and this one keeps the version's own completions cheap to audit.
CREATE INDEX IF NOT EXISTS ix_estimate_line_completions_version
    ON estimate_line_source_completions (organization_id, project_id, source_version_id);
"""


DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS estimate_line_source_completions;
ALTER TABLE finance_mpp_rows
    DROP COLUMN source_rate_basis,
    DROP COLUMN source_resource_rate_irr,
    DROP COLUMN source_material_quantity;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
