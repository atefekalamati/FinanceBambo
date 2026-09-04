-- POSTCHECK -- run after msp_resource_assignment_apply.sql. READ ONLY.
--
-- Structural only. Data checks after a controlled import live in
-- msp_resource_assignment_data_validation.sql; this one answers "was the schema created
-- correctly", which is a different question and worth keeping separate.

BEGIN READ ONLY;

\echo '--- 1. both tables exist ---'
SELECT name,
       CASE WHEN to_regclass('public.' || name) IS NULL THEN 'MISSING -- FAIL' ELSE 'present' END
  FROM (VALUES ('msp_resources'), ('msp_resource_assignments')) AS t(name);

\echo '--- 2. column types ---'
SELECT table_name, column_name, data_type,
       coalesce(numeric_precision::text || ',' || numeric_scale::text, '-') AS precision,
       is_nullable
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name IN ('msp_resources', 'msp_resource_assignments')
 ORDER BY table_name, ordinal_position;

\echo '--- 3. the four types that carry meaning must be numeric, not float ---'
SELECT table_name, column_name, data_type,
       CASE WHEN data_type = 'numeric' THEN 'ok' ELSE 'FAIL -- money and quantity must not be float' END
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name IN ('msp_resources', 'msp_resource_assignments')
   AND (column_name LIKE '%quantity%' OR column_name LIKE '%cost%'
        OR column_name LIKE '%rate%' OR column_name LIKE '%work%')
   -- The unit columns carry the name of a unit, not an amount of one, so they are text on
   -- purpose. Without this they match the patterns above and report as failures.
   AND column_name NOT LIKE '%_unit'
   AND column_name NOT LIKE '%_unit_source'
 ORDER BY 1, 2;

\echo '--- 4. constraints ---'
SELECT cl.relname AS table_name, c.conname, c.contype, pg_get_constraintdef(c.oid) AS definition
  FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = cl.relnamespace
 WHERE n.nspname = 'public'
   AND cl.relname IN ('msp_resources', 'msp_resource_assignments')
   AND c.contype <> 'n'
 ORDER BY 1, 3, 2;

\echo '--- 5. the two unique keys that must exist ---'
SELECT name,
       CASE WHEN EXISTS (SELECT 1 FROM pg_constraint WHERE conname = name)
            THEN 'present' ELSE 'MISSING -- FAIL' END AS state
  FROM (VALUES ('msp_resources_snapshot_uid_key'),
               ('msp_resource_assignments_snapshot_uid_key'),
               ('msp_resources_id_snapshot_key')) AS t(name);

\echo '--- 6. no cross-snapshot uniqueness was created by accident ---'
-- A unique key on resource_uid or assignment_uid alone would assert cross-version identity
-- that has never been proven. It must not exist.
SELECT c.conname, pg_get_constraintdef(c.oid) AS definition, 'FAIL -- too strict' AS verdict
  FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
 WHERE cl.relname IN ('msp_resources', 'msp_resource_assignments')
   AND c.contype = 'u'
   AND pg_get_constraintdef(c.oid) NOT ILIKE '%snapshot_id%';

\echo '--- 7. indexes ---'
SELECT tablename, indexname, indexdef
  FROM pg_indexes
 WHERE schemaname = 'public'
   AND tablename IN ('msp_resources', 'msp_resource_assignments')
 ORDER BY 1, 2;

\echo '--- 8. foreign keys -- exactly one, and it must not reach into Core ---'
SELECT cl.relname AS child, pg_get_constraintdef(c.oid) AS definition
  FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
 WHERE cl.relname IN ('msp_resources', 'msp_resource_assignments') AND c.contype = 'f'
 ORDER BY 1, 2;

-- The migration role has no REFERENCES privilege on Core, so a key pointing there could
-- not have been created. If one appears, this was applied by a different role than the one
-- production will use, and what else that role did is now an open question.
SELECT count(*) AS foreign_keys_into_core_MUST_BE_ZERO
  FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
  JOIN pg_class parent ON parent.oid = c.confrelid
 WHERE cl.relname IN ('msp_resources', 'msp_resource_assignments')
   AND c.contype = 'f'
   AND parent.relname IN ('msp_snapshots', 'msp_tasks', 'msp_file_versions', 'projects');

-- The one internal key that must exist: both tables belong to this Alembic chain.
SELECT CASE WHEN EXISTS (
           SELECT 1 FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
            WHERE cl.relname = 'msp_resource_assignments'
              AND c.conname = 'msp_resource_assignments_resource_fkey')
       THEN 'present' ELSE 'MISSING -- FAIL' END AS internal_resource_foreign_key;

\echo '--- 9. tables must be empty -- APPLY creates, it does not backfill ---'
SELECT 'msp_resources' AS table_name, count(*) AS rows FROM msp_resources
UNION ALL
SELECT 'msp_resource_assignments', count(*) FROM msp_resource_assignments;

\echo '--- 10. no existing Core object was altered ---'
-- msp_tasks must still have exactly the constraints it had before. Compare against the
-- value PRECHECK recorded.
SELECT count(*) AS msp_tasks_constraints
  FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
 WHERE cl.relname = 'msp_tasks' AND c.contype <> 'n';

ROLLBACK;

-- =====================================================================================
-- PASS when: both tables present; every quantity/cost/rate/work column is numeric; the
-- three unique keys in section 5 present; section 6 returns no rows; both tables empty;
-- msp_tasks constraint count unchanged from PRECHECK.
--
-- FAIL on anything else. Do not repair by hand -- use the rollback package and re-apply.
-- =====================================================================================
