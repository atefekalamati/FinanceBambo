-- ROLLBACK -- removes the two Core tables this package created.
--
-- THIS IS DESTRUCTIVE AND IT REFUSES TO BE QUIET ABOUT IT.
--
-- If either table holds rows, the script raises and changes nothing. Dropping an imported
-- snapshot's resources and assignments silently would look identical to a clean rollback
-- right up to the moment somebody asks where the quantities went.
--
-- To drop tables that DO hold rows, the operator sets the flag below, having first read the
-- counts the script prints. That is deliberately two deliberate acts, not one.
--
--   psql -v allow_data_loss=yes -f msp_resource_assignment_rollback.sql
--
-- Nothing here touches msp_snapshots, msp_tasks, or any other Core table.

\set ON_ERROR_STOP on
\if :{?allow_data_loss} \else \set allow_data_loss no \endif

\echo '--- what is about to be dropped ---'
SELECT 'msp_resources' AS table_name,
       CASE WHEN to_regclass('public.msp_resources') IS NULL THEN NULL
            ELSE (SELECT count(*) FROM msp_resources) END AS rows
UNION ALL
SELECT 'msp_resource_assignments',
       CASE WHEN to_regclass('public.msp_resource_assignments') IS NULL THEN NULL
            ELSE (SELECT count(*) FROM msp_resource_assignments) END;

-- The guard runs in psql, not in plpgsql: a psql variable is not substituted inside a
-- dollar-quoted block, so a check written there would have compared the literal text
-- ":'allow_data_loss'" and passed every time.
SELECT coalesce((SELECT count(*) FROM msp_resources
                  WHERE to_regclass('public.msp_resources') IS NOT NULL), 0)
     + coalesce((SELECT count(*) FROM msp_resource_assignments
                  WHERE to_regclass('public.msp_resource_assignments') IS NOT NULL), 0)
       AS total_rows \gset

\if :total_rows
  \if :allow_data_loss
    \echo 'proceeding: allow_data_loss was set and the counts above were shown'
  \else
    \warn 'REFUSING: the tables hold rows (see counts above).'
    \warn 'Re-run with  -v allow_data_loss=yes  only after deciding those rows may be lost.'
    \quit 1
  \endif
\endif

BEGIN;

-- Assignments first: they carry the foreign key to resources.
DROP TABLE IF EXISTS msp_resource_assignments;
DROP TABLE IF EXISTS msp_resources;

COMMIT;

\echo '--- after ---'
SELECT name,
       CASE WHEN to_regclass('public.' || name) IS NULL THEN 'dropped' ELSE 'STILL PRESENT' END
  FROM (VALUES ('msp_resources'), ('msp_resource_assignments')) AS t(name);

-- Core tables must be untouched. Both numbers should match what PRECHECK recorded.
SELECT (SELECT count(*) FROM msp_snapshots) AS snapshots,
       (SELECT count(*) FROM msp_tasks)     AS tasks;
