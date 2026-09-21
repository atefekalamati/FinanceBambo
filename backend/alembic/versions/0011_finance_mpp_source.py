"""Finance's own record of what a schedule file said

Revision ID: 0011
Revises: 0010

Finance reads the MPP file directly, and until now it kept nothing: the values lived in a
feed for the length of one request. That is not enough. A report issued last month has to
be reproducible next month, and Finance must be able to recover the numbers it used
without asking MSP/Core for them -- which is the whole point of the two modules being
independent.

These two tables are that record, and they are deliberately small:

`finance_mpp_source_versions` is one row per distinct FILE CONTENT (its SHA-256). The same
bytes imported twice are one version, so a sync is idempotent; different bytes are a new
version, so history is kept rather than overwritten. The configured directory is NOT
stored: the path comes from `MPP_IMPORT_ROOT` and moving from a Windows folder to a mounted
volume must not invalidate a row. Only the file's own name travels with it.

`finance_mpp_rows` is one row per schedule row Finance cares about, identified by the MPP's
OWN identifiers -- `source_task_uid`, `source_assignment_uid`, `source_resource_uid`. It
holds no `msp_tasks.id`, no `msp_snapshots.id` and no bridge id: a Finance deployment with
no MSP tables at all must still be able to read every one of these rows.

QUANTITY IS NULLABLE AND, TODAY, NULL
The column exists because the architecture must be ready for a schedule that states an
approved Finance quantity. The file in front of us does not: its twenty-two custom columns
are weighting coefficients, progress measures and planning volumes, and not one of them is
an approved quantity field. So the column is created NULL-able and stays NULL, and every
quantity-dependent figure reports itself as unavailable. A column filled from work hours,
from a duration, or from a custom column that merely contains a number would be worse than
an empty one: nobody can tell an invented quantity from a measured one once it is a number
in a report.

WHY msp_task_metrics GOES
It was created to carry these same values on the Core side so the Finance feed could join
to them. Finance no longer joins to anything, and nothing on the MSP side reads the table:
it has a writer and no reader. Its data is the file's, and the file is still there, so
dropping it loses nothing that a re-import cannot restate. The drop is forward-only -- 0010
is left exactly as it was applied.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE TABLE finance_mpp_source_versions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    -- The file's own name, never the directory it was read from: the directory is
    -- configuration (MPP_IMPORT_ROOT) and differs between a laptop and a server.
    source_file_name_safe text NOT NULL CHECK (length(btrim(source_file_name_safe)) > 0),
    source_sha256 text NOT NULL CHECK (length(source_sha256) = 64),
    source_size_bytes bigint CHECK (source_size_bytes IS NULL OR source_size_bytes > 0),
    reader_engine text,
    status text NOT NULL CHECK (status IN ('ready', 'failed')),
    row_count integer NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    imported_by uuid,
    imported_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- One version per distinct content per project: re-reading the same bytes is a
    -- no-op, which is what makes the sync safe to run on a timer.
    UNIQUE (organization_id, project_id, source_sha256)
);

COMMENT ON TABLE finance_mpp_source_versions IS
    'One row per distinct MPP file CONTENT that Finance has read. Finance-owned; needs no '
    'MSP table to be interpreted.';

CREATE INDEX ix_finance_mpp_source_versions_scope
    ON finance_mpp_source_versions (organization_id, project_id, imported_at DESC);

CREATE TABLE finance_mpp_rows (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    source_version_id uuid NOT NULL
        REFERENCES finance_mpp_source_versions (id) ON DELETE CASCADE,

    -- Identity as the FILE states it. No database id from any other module appears here.
    source_task_uid integer NOT NULL,
    source_assignment_uid integer,
    source_resource_uid integer,

    task_name text,
    task_wbs text,
    resource_name text,

    -- NULL until a schedule states an approved Finance quantity. Never derived from
    -- work, duration, cost or a percentage.
    quantity numeric,
    quantity_unit text,

    weight_rial numeric,
    weight_time numeric,
    weight_base numeric,

    actual_progress numeric,
    actual_progress_percent numeric,
    physical_progress numeric,
    planned_progress numeric,

    cost numeric,
    actual_cost numeric,
    fixed_cost numeric
);

COMMENT ON TABLE finance_mpp_rows IS
    'The schedule rows Finance needs, keyed by the MPP''s own identifiers. Finance-owned: '
    'readable with no msp_* table present.';
COMMENT ON COLUMN finance_mpp_rows.quantity IS
    'NULL unless the file states an approved Finance quantity. Never inferred from work, '
    'duration, cost or percent complete.';

-- COALESCE, because a NULL assignment uid must still collide with another NULL one:
-- Postgres treats NULLs as distinct and a plain UNIQUE would admit duplicates.
CREATE UNIQUE INDEX ux_finance_mpp_rows_identity
    ON finance_mpp_rows (source_version_id, source_task_uid,
                         COALESCE(source_assignment_uid, -1));

CREATE INDEX ix_finance_mpp_rows_scope
    ON finance_mpp_rows (organization_id, project_id, source_version_id);
CREATE INDEX ix_finance_mpp_rows_resource
    ON finance_mpp_rows (source_version_id, source_resource_uid);

-- Core-safe deployment: do not DROP public/Core tables from the Finance migration.
-- msp_task_metrics is intentionally left untouched.
"""


DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS finance_mpp_rows;
DROP TABLE IF EXISTS finance_mpp_source_versions;

-- Recreated exactly as 0010 left it, so downgrading to 0010 restores that schema. The
-- ROWS are not restored: they were the file's, and re-importing the file restates them.
CREATE TABLE msp_task_metrics (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    snapshot_id bigint NOT NULL,
    task_uid integer NOT NULL,
    item_quantity numeric,
    item_quantity_text text,
    work_volume numeric,
    done_volume numeric,
    initial_volume numeric,
    work_volume_percent numeric,
    weight_time numeric,
    weight_rial numeric,
    weight_base numeric,
    weight_percent numeric,
    wf_time numeric,
    wf_rial numeric,
    wf_physical numeric,
    actual_progress numeric,
    actual_progress_percent numeric,
    physical_progress numeric,
    planned_progress numeric,
    planned_progress_component numeric,
    progress_variance numeric,
    jalali_start text,
    jalali_finish text,
    task_cost numeric,
    task_actual_cost numeric,
    task_fixed_cost numeric,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, task_uid)
);
CREATE INDEX ix_msp_task_metrics_snapshot ON msp_task_metrics (snapshot_id);
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
