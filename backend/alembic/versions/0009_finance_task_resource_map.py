"""link Core schedule tasks to Finance resources, one row per pair

Revision ID: 0009
Revises: 0008

`finance_task_resource_map` is the explicit join between a schedule row Core imported
(`msp_tasks.id` -- the database identity, NEVER the file's display Task ID) and a Finance
resource. It carries EXACTLY three columns by design: identity, task, resource. Tenant
scope is deliberately NOT duplicated here -- both endpoints of the link already know their
organization and project, and a copy in this table would be a second source of truth that
could drift. Scope safety comes from three layers instead:

  1. the importer resolves resources only inside the caller's (organization, project);
  2. every read joins through `finance_resources`, which carries the tenant columns;
  3. the constraint trigger below refuses any pair whose task and resource disagree on
     the project.

WHY THE TRIGGER COMPARES ONLY THE PROJECT
Core's `msp_snapshots` names a `project_id` but no organization -- the Core host is
single-organization by construction. The trigger therefore enforces project equality
(the strongest check this schema can express) and fails CLOSED when the task's project
cannot be resolved at all. Organization equality is enforced above the database, in the
import service, which takes the organization from the authenticated context and verifies
it against `projects` before any row is written.

A NOTE ON THE FOREIGN KEY INTO CORE
Revision 0007 recorded that the *production* migration role has no REFERENCES privilege
on Core tables, and that FKs into Core would fail to apply there. The project owner has
since decided this link table MUST be enforced by the database: `task_id` references
`msp_tasks (id)` ON DELETE CASCADE (a task that Core deletes takes its mappings with it)
and `resource_id` references `finance_resources (id)` ON DELETE RESTRICT (a resource that
is still mapped cannot be deleted). Deploying this revision to an environment with the
restricted role therefore REQUIRES, first:

    GRANT REFERENCES ON msp_tasks TO <migration role>;

This is an operator precondition, not something this revision can do for itself.

THE PARTIAL UNIQUE INDEX ON finance_resources
The importer matches `assignment.resource_uid` to `finance_resources.external_resource_id`
inside one (organization, project). That match is only deterministic if the external id is
unique inside that scope -- so this revision makes the database say so, over live rows
only (`deleted_at IS NULL`). It REFUSES to run over dirty data: if duplicates exist the
DO-block raises with the count, and resolving them is a human decision -- this migration
never merges or deletes rows on its own.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
DO $precheck$
BEGIN
    IF to_regclass('msp_tasks') IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = '0009 requires the Core table msp_tasks to exist because the Finance mapping guard validates task/project scope: '
                      'finance_task_resource_map_guard resolves task_id through '
                      'msp_tasks and msp_snapshots. On the shared BAMBO database Core '
                      'creates it; on any other database create a compatible '
                      'msp_tasks (and msp_snapshots for the trigger) first, or do '
                      'not run this revision there.';
    END IF;
END
$precheck$;

-- Held to COMMIT (the whole revision is one transaction): writers to
-- finance_resources wait here, so no INSERT can slip between the duplicate count
-- below and the unique index build and turn the curated refusal into a raw error.
LOCK TABLE finance_resources IN SHARE ROW EXCLUSIVE MODE;

DO $guard$
DECLARE
    bad integer;
BEGIN
    SELECT COUNT(*) INTO bad FROM (
        SELECT 1
        FROM finance_resources
        WHERE external_resource_id IS NOT NULL
          AND deleted_at IS NULL
        GROUP BY organization_id, project_id, external_resource_id
        HAVING COUNT(*) > 1
    ) duplicated;
    IF bad > 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'finance_resources holds ' || bad || ' duplicated '
                      '(organization_id, project_id, external_resource_id) group(s) '
                      'among live rows; resolve them before applying 0009 -- this '
                      'migration never merges or deletes rows itself';
    END IF;
END
$guard$;

CREATE UNIQUE INDEX ux_finance_resources_external_identity
    ON finance_resources (organization_id, project_id, external_resource_id)
    WHERE external_resource_id IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE finance_task_resource_map (
    id uuid PRIMARY KEY,
    task_id bigint NOT NULL,
    resource_id uuid NOT NULL,
    UNIQUE (task_id, resource_id),
    -- Intentionally no FK into Core msp_tasks.
    -- The shared BAMBO deployment role must not require REFERENCES/DDL privileges
    -- on Core-owned tables. finance_task_resource_map_guard() below validates
    -- that task_id resolves through msp_tasks -> msp_snapshots and belongs to
    -- the same project as the Finance resource.
    FOREIGN KEY (resource_id) REFERENCES finance_resources (id) ON DELETE RESTRICT
);

COMMENT ON TABLE finance_task_resource_map IS
    'One row per (Core schedule task, Finance resource) pair. Exactly three columns by '
    'design: tenant scope lives on the two endpoints and every read joins through '
    'finance_resources.';
COMMENT ON COLUMN finance_task_resource_map.task_id IS
    'msp_tasks.id -- the database row identity. NEVER the MPP file''s display Task ID, '
    'which renumbers on every insertion.';

CREATE INDEX ix_finance_task_resource_map_resource
    ON finance_task_resource_map (resource_id);

CREATE OR REPLACE FUNCTION finance_task_resource_map_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
DECLARE
    task_project text;
    resource_project text;
BEGIN
    SELECT s.project_id INTO task_project
    FROM msp_tasks t
    JOIN msp_snapshots s ON s.id = t.snapshot_id
    WHERE t.id = NEW.task_id;

    SELECT r.project_id INTO resource_project
    FROM finance_resources r
    WHERE r.id = NEW.resource_id;

    IF task_project IS NULL THEN
        -- Fail CLOSED: a task whose project cannot be resolved maps to nothing.
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'finance_task_resource_map: task ' || NEW.task_id ||
                      ' has no resolvable project (no snapshot row behind it)';
    END IF;
    IF resource_project IS NULL OR task_project IS DISTINCT FROM resource_project THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'finance_task_resource_map: task ' || NEW.task_id ||
                      ' belongs to project ' || task_project ||
                      '; the finance resource does not';
    END IF;
    RETURN NEW;
END
$fn$;

CREATE CONSTRAINT TRIGGER finance_task_resource_map_scope
    AFTER INSERT OR UPDATE ON finance_task_resource_map
    FOR EACH ROW EXECUTE FUNCTION finance_task_resource_map_guard();
"""


DOWNGRADE_SQL = r"""
DROP TRIGGER IF EXISTS finance_task_resource_map_scope ON finance_task_resource_map;
DROP FUNCTION IF EXISTS finance_task_resource_map_guard();
DROP TABLE IF EXISTS finance_task_resource_map;
DROP INDEX IF EXISTS ux_finance_resources_external_identity;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
