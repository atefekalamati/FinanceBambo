-- PRECHECK -- run before msp_resource_assignment_apply.sql. READ ONLY.
--
-- Wrapped in a read-only transaction so a stray verb is refused by the server rather than
-- by anyone's care. Nothing here writes.
--
-- Read the last section before deciding. A PASS here is what makes APPLY a routine step
-- instead of a gamble.

BEGIN READ ONLY;

\echo '--- 1. where am I ---'
SELECT current_database()                       AS database,
       current_user                             AS role,
       current_schema()                         AS schema,
       current_setting('server_version')        AS server_version,
       current_setting('transaction_read_only')  AS read_only;

\echo '--- 2. Core tables that must already exist ---'
SELECT name,
       CASE WHEN to_regclass('public.' || name) IS NULL THEN 'MISSING' ELSE 'present' END AS state
  FROM (VALUES ('msp_snapshots'), ('msp_tasks'), ('msp_file_versions'), ('projects')) AS t(name);

\echo '--- 3. target tables that must NOT exist ---'
SELECT name,
       CASE WHEN to_regclass('public.' || name) IS NULL THEN 'absent (expected)'
            ELSE 'ALREADY EXISTS -- BLOCK' END AS state
  FROM (VALUES ('msp_resources'), ('msp_resource_assignments')) AS t(name);

\echo '--- 4. name collisions on the objects APPLY creates ---'
SELECT c.relname AS existing_object, c.relkind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relname IN ('msp_resources_snapshot_idx', 'msp_resources_native_type_idx',
                     'msp_resources_guid_idx', 'msp_resource_assignments_snapshot_idx',
                     'msp_resource_assignments_task_idx',
                     'msp_resource_assignments_resource_idx');

SELECT conname AS existing_constraint
  FROM pg_constraint
 WHERE conname LIKE 'msp_resources%' OR conname LIKE 'msp_resource_assignments%';

\echo '--- 5. msp_tasks UID quality (decides whether a task FK is even possible) ---'
SELECT count(*)                                        AS task_rows,
       count(*) FILTER (WHERE uid IS NULL)             AS null_uid,
       count(DISTINCT (snapshot_id, uid))              AS distinct_snapshot_uid
  FROM msp_tasks;

-- Non-zero here means UNIQUE (snapshot_id, uid) cannot be added to msp_tasks, and the
-- assignment table must keep task_uid as a plain column. Zero does NOT authorise adding
-- that constraint -- that is Core's decision, not this script's.
SELECT count(*) AS snapshot_uid_pairs_used_more_than_once
  FROM (SELECT snapshot_id, uid FROM msp_tasks
         WHERE uid IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1) AS duplicated;

SELECT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
     WHERE cl.relname = 'msp_tasks' AND c.contype IN ('u', 'p')
       AND pg_get_constraintdef(c.oid) ILIKE '%snapshot_id%uid%'
) AS msp_tasks_has_snapshot_uid_unique;

\echo '--- 6. snapshots ---'
SELECT count(*) AS snapshots,
       count(*) FILTER (WHERE snapshot_type = 'ACTUAL')      AS actual,
       count(*) FILTER (WHERE snapshot_type = 'TARGET')      AS target,
       count(*) FILTER (WHERE snapshot_type = 'RESCHEDULED') AS rescheduled
  FROM msp_snapshots;

SELECT id, project_id, snapshot_type, file_version_id, task_count,
       status_date_jalali, parser_engine, created_at
  FROM msp_snapshots ORDER BY created_at DESC, id DESC LIMIT 5;

\echo '--- 7. privileges APPLY needs ---'
SELECT has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_in_public,
       has_schema_privilege(current_user, 'public', 'USAGE')  AS can_use_public,
       has_table_privilege(current_user, 'msp_snapshots', 'SELECT') AS can_read_snapshots,
       has_table_privilege(current_user, 'msp_tasks', 'SELECT')     AS can_read_tasks;

ROLLBACK;

-- =====================================================================================
-- HOW TO READ THIS
--
-- PASS -- APPLY may proceed when all of:
--   1. database is the intended Core database and the server is PostgreSQL 18.x
--   2. msp_snapshots, msp_tasks, msp_file_versions, projects all 'present'
--   3. msp_resources and msp_resource_assignments both 'absent (expected)'
--   4. section 4 returns no rows
--   5. can_create_in_public and can_use_public are both true
--
-- BLOCK -- stop and report, do not run APPLY, when any of:
--   * either target table already exists. Do not adopt it and do not drop it: something
--     applied a version of this schema already, and which version matters.
--   * an index or constraint name from section 4 is taken. APPLY would fail halfway.
--   * can_create_in_public is false. This is a role problem, not a schema problem, and
--     granting it is Core's decision.
--   * msp_snapshots or msp_tasks is missing. Wrong database.
--
-- SECTION 5 IS INFORMATION, NOT A GATE
--   APPLY deliberately creates no foreign key from task_uid to msp_tasks, because
--   msp_tasks has no UNIQUE (snapshot_id, uid) to point at. If
--   snapshot_uid_pairs_used_more_than_once is 0 and Core wants that constraint, it is a
--   separate, Core-owned change -- adding it from here would be Finance quietly altering a
--   Core table.
-- =====================================================================================
