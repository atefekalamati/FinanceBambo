"""core progress snapshot reference

Finance can now record *which Core snapshot* a progress reference came from.

WHY THIS EXISTS
Core identifies an MSP snapshot with `msp_snapshots.id bigint` and a schedule file with
`msp_file_versions.id bigint`. Finance stored neither: it had `progress_snapshot_id uuid`
and `source_file_version_id uuid`, which no Core row has ever matched. So a Finance
reference could not say what it referred to, and nothing could pin a financial figure to a
specific Core snapshot.

WHAT IS DELIBERATELY NOT DONE HERE
No foreign key to `msp_snapshots` or `msp_file_versions`. Core deletes an MSP snapshot when
its project is deleted (`msp_snapshots.project_id -> projects(id) ON DELETE CASCADE`), so a
RESTRICT foreign key would block project deletion in Core and a CASCADE one would delete
financial history. Neither is acceptable, and the choice between them is a product decision
about what deleting a financed project means. References are validated at the adapter
boundary instead.

The existing `progress_snapshot_id uuid` is NOT removed and NOT rewritten. It is now
Finance's own opaque public identifier -- the value that appears in URLs and in issued
report payloads -- and `host_snapshot_id` carries the Core identity beside it. Removing the
old column would break every route and rewrite immutable issued reports; that is a later,
separately reviewed decision if it is ever worth making.

`source_file_version_id` loses only its NOT NULL. A row ingested from Core has no
Finance-side file identifier to invent, and NULL says that honestly; fabricating a UUID
there would look like a Host reference and be nothing of the kind.

The downgrade restores that NOT NULL when every row still has a value, and refuses with an
explanation when they do not -- rather than leaving a schema that matches neither revision.
See DOWNGRADE_SQL.

IDEMPOTENCY
The partial unique index is what makes ingestion safe to repeat: the same Core snapshot in
the same project cannot produce a second Finance reference. It is partial because rows
predating this migration have `host_snapshot_id IS NULL`, and every one of them must remain
valid.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
from sqlalchemy import DDL

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


UPGRADE_SQL = """\
-- Core identifiers, nullable and without DEFAULT: a catalog-only change on PostgreSQL 11+,
-- so no row is rewritten and the progress_snapshot_refs_immutable trigger (BEFORE UPDATE OR
-- DELETE, FOR EACH ROW) never fires. Rows imported before this migration keep NULL, which
-- is true of them: they were never linked to a Core snapshot.
ALTER TABLE progress_snapshot_refs
    ADD COLUMN IF NOT EXISTS host_snapshot_id bigint,
    ADD COLUMN IF NOT EXISTS host_file_version_id bigint;

-- Core sequences start at 1, so a non-positive identifier is a mistake rather than a value.
-- Both existence checks are scoped to this table, not to the name alone. Constraint names
-- are unique per relation in PostgreSQL, not per schema, so an unrelated table carrying a
-- constraint of the same name would otherwise make this migration believe its own work was
-- already done and silently skip creating it.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'progress_snapshot_refs_host_snapshot_id_check'
          AND conrelid = 'progress_snapshot_refs'::regclass
    ) THEN
        ALTER TABLE progress_snapshot_refs
            ADD CONSTRAINT progress_snapshot_refs_host_snapshot_id_check
            CHECK (host_snapshot_id IS NULL OR host_snapshot_id > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'progress_snapshot_refs_host_file_version_id_check'
          AND conrelid = 'progress_snapshot_refs'::regclass
    ) THEN
        ALTER TABLE progress_snapshot_refs
            ADD CONSTRAINT progress_snapshot_refs_host_file_version_id_check
            CHECK (host_file_version_id IS NULL OR host_file_version_id > 0);
    END IF;
END $$;

-- One Finance reference per Core snapshot per project. This is the constraint ingestion
-- relies on: repeating an import cannot create a second reference to the same snapshot.
-- Scoped by tenant like every other uniqueness rule here, and partial so that the NULL
-- rows from before this migration are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS ux_progress_snapshot_refs_host_snapshot
    ON progress_snapshot_refs (organization_id, project_id, host_snapshot_id)
    WHERE host_snapshot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_progress_snapshot_refs_host_file_version
    ON progress_snapshot_refs (organization_id, project_id, host_file_version_id);

-- A reference ingested from Core has no Finance-side file version identifier, and inventing
-- a UUID for it would look like a Host reference while being nothing of the kind. Dropping
-- NOT NULL is DDL, not a row update, so the immutability trigger stays quiet.
ALTER TABLE progress_snapshot_refs
    ALTER COLUMN source_file_version_id DROP NOT NULL;
"""


DOWNGRADE_SQL = """\
DROP INDEX IF EXISTS ix_progress_snapshot_refs_host_file_version;
DROP INDEX IF EXISTS ux_progress_snapshot_refs_host_snapshot;

ALTER TABLE progress_snapshot_refs
    DROP CONSTRAINT IF EXISTS progress_snapshot_refs_host_file_version_id_check,
    DROP CONSTRAINT IF EXISTS progress_snapshot_refs_host_snapshot_id_check;

ALTER TABLE progress_snapshot_refs
    DROP COLUMN IF EXISTS host_file_version_id,
    DROP COLUMN IF EXISTS host_snapshot_id;

-- Restore the NOT NULL that 0005 had, or refuse.
--
-- Dropping the columns above is not the whole of this revision: it also relaxed
-- source_file_version_id. Leaving the column nullable would end the downgrade with a schema
-- that is neither 0005 nor 0006, and nothing would say so -- the next person to compare the
-- database against revision 0005 would find a difference with no record of where it came
-- from.
--
-- The column can only be restored if every row still has a value. A row ingested from Core
-- after 0006 legitimately has NULL: there is no Finance-side file identifier for it, and
-- the only ways to satisfy the old constraint would be to invent a UUID -- which would look
-- like a Host reference and be nothing of the kind -- or to delete the row, which is
-- financial history. Neither is acceptable, so the downgrade stops and says why.
--
-- Alembic wraps the migration in one transaction, so this abort rolls back the drops above
-- as well. The database is left exactly at 0006, not half-way between revisions.
DO $$
DECLARE
    ingested bigint;
BEGIN
    SELECT count(*) INTO ingested
    FROM progress_snapshot_refs
    WHERE source_file_version_id IS NULL;

    IF ingested > 0 THEN
        RAISE EXCEPTION USING
            MESSAGE = 'Downgrade to 0005 refused: ' || ingested || ' progress_snapshot_refs '
                      || 'row(s) have no source_file_version_id. These were ingested from a '
                      || 'Core snapshot after revision 0006, and revision 0005 requires the '
                      || 'column to be NOT NULL.',
            HINT = 'Restoring 0005 would mean inventing a Finance file UUID for each of '
                   || 'those rows, which would look like a Host reference and be nothing of '
                   || 'the kind, or deleting them, which is financial history. Resolve the '
                   || 'rows deliberately first, or stay on 0006. Nothing has been changed.',
            ERRCODE = 'raise_exception';
    END IF;

    ALTER TABLE progress_snapshot_refs
        ALTER COLUMN source_file_version_id SET NOT NULL;
END $$;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
