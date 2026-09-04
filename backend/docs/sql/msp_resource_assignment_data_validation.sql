-- DATA VALIDATION -- run after a controlled import of exactly one snapshot. READ ONLY.
--
-- Structural checks live in the postcheck; this one asks whether the rows that arrived are
-- coherent. The section that matters most is the last: a resource's Resource Sheet quantity
-- must equal the sum of its assignments' quantities, and where it does not, the import lost
-- or duplicated something.

BEGIN READ ONLY;

\echo '--- 1. counts per snapshot ---'
SELECT s.id AS snapshot_id, s.snapshot_type, s.status_date_jalali,
       (SELECT count(*) FROM msp_tasks t WHERE t.snapshot_id = s.id)                AS tasks,
       (SELECT count(*) FROM msp_resources r WHERE r.snapshot_id = s.id)            AS resources,
       (SELECT count(*) FROM msp_resource_assignments a WHERE a.snapshot_id = s.id) AS assignments
  FROM msp_snapshots s
 WHERE EXISTS (SELECT 1 FROM msp_resources r WHERE r.snapshot_id = s.id)
    OR EXISTS (SELECT 1 FROM msp_resource_assignments a WHERE a.snapshot_id = s.id)
 ORDER BY s.id;

\echo '--- 2. resource types ---'
SELECT snapshot_id, native_type, bambo_resource_type, count(*)
  FROM msp_resources GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

\echo '--- 3. duplicate snapshot-local keys (must both be 0) ---'
SELECT 'resource_uid' AS key, count(*) AS duplicated FROM (
    SELECT snapshot_id, resource_uid FROM msp_resources GROUP BY 1, 2 HAVING count(*) > 1) d
UNION ALL
SELECT 'assignment_uid', count(*) FROM (
    SELECT snapshot_id, assignment_uid FROM msp_resource_assignments
     GROUP BY 1, 2 HAVING count(*) > 1) d;

\echo '--- 4. null identifiers (must all be 0) ---'
SELECT count(*) FILTER (WHERE resource_uid IS NULL) AS resource_uid_null,
       count(*) FILTER (WHERE snapshot_id IS NULL)  AS resource_snapshot_null
  FROM msp_resources;
SELECT count(*) FILTER (WHERE assignment_uid IS NULL) AS assignment_uid_null,
       count(*) FILTER (WHERE task_uid IS NULL)       AS task_uid_null
  FROM msp_resource_assignments;

\echo '--- 5. orphan references -- THIS SECTION REPLACES FOREIGN KEYS ---'
-- The production migration role has no REFERENCES privilege on Core, so three of the four
-- relationships below are logical and the database does not enforce them. These counts are
-- the enforcement. All four must be 0.
--
-- The fourth is enforced -- msp_resources is owned by the same Alembic chain -- and is
-- checked anyway, because a constraint that has silently gone missing looks exactly like a
-- constraint that is working.
SELECT 'resources -> msp_snapshots'   AS relation, 'logical' AS enforced_by, count(*) AS broken
  FROM msp_resources r
 WHERE NOT EXISTS (SELECT 1 FROM msp_snapshots s WHERE s.id = r.snapshot_id)
UNION ALL
SELECT 'assignments -> msp_snapshots', 'logical', count(*)
  FROM msp_resource_assignments a
 WHERE NOT EXISTS (SELECT 1 FROM msp_snapshots s WHERE s.id = a.snapshot_id)
UNION ALL
SELECT 'assignments -> msp_tasks (same snapshot)', 'logical', count(*)
  FROM msp_resource_assignments a
 WHERE NOT EXISTS (SELECT 1 FROM msp_tasks t
                    WHERE t.snapshot_id = a.snapshot_id AND t.uid = a.task_uid)
UNION ALL
SELECT 'assignments -> msp_resources', 'foreign key', count(*)
  FROM msp_resource_assignments a
 WHERE a.resource_uid IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM msp_resources r
                    WHERE r.snapshot_id = a.snapshot_id AND r.resource_uid = a.resource_uid);

-- Orphans that a Core deletion would produce. A foreign key would have cascaded these away;
-- without one they linger, so they are named rather than left to be discovered as a wrong
-- total. Rows here are safe to delete once the snapshot is confirmed gone from Core.
SELECT snapshot_id,
       (SELECT count(*) FROM msp_resources r WHERE r.snapshot_id = orphan.snapshot_id) AS resources,
       (SELECT count(*) FROM msp_resource_assignments a
         WHERE a.snapshot_id = orphan.snapshot_id) AS assignments
  FROM (SELECT DISTINCT snapshot_id FROM msp_resources
         UNION SELECT DISTINCT snapshot_id FROM msp_resource_assignments) AS orphan
 WHERE NOT EXISTS (SELECT 1 FROM msp_snapshots s WHERE s.id = orphan.snapshot_id)
 ORDER BY snapshot_id;

-- A null resource_uid is expected and legal: MSP leaves some assignments unlinked.
SELECT count(*) FILTER (WHERE resource_uid IS NULL) AS unlinked_assignments,
       count(*)                                     AS total_assignments
  FROM msp_resource_assignments;

\echo '--- 6. quantity coverage ---'
SELECT count(*)                                              AS assignments,
       count(*) FILTER (WHERE planned_quantity IS NOT NULL)  AS with_planned_quantity,
       count(*) FILTER (WHERE actual_quantity IS NOT NULL)   AS with_actual_quantity,
       count(*) FILTER (WHERE remaining_quantity IS NOT NULL) AS with_remaining_quantity,
       count(*) FILTER (WHERE quantity_unit IS NULL
                          AND planned_quantity IS NOT NULL)  AS quantity_without_unit
  FROM msp_resource_assignments;

-- quantity_without_unit must be 0: a CHECK constraint forbids it, and a non-zero here would
-- mean the constraint is missing.
SELECT count(*)                                             AS resources,
       count(*) FILTER (WHERE resource_quantity IS NOT NULL) AS with_quantity,
       count(*) FILTER (WHERE resource_quantity_unit IS NULL
                          AND resource_quantity IS NOT NULL) AS quantity_without_unit,
       count(*) FILTER (WHERE bambo_resource_type IS NULL)   AS unclassified
  FROM msp_resources;

\echo '--- 7. unit source, so a convention change is visible ---'
SELECT quantity_unit_source, count(*), min(resource_quantity_unit) AS example_unit
  FROM msp_resources GROUP BY 1 ORDER BY 2 DESC;

\echo '--- 8. THE IMPORTANT ONE: resource total vs sum of its assignments ---'
-- The Resource Sheet quantity is the aggregate of the assignment quantities. Where they
-- disagree, the import dropped or duplicated rows. A tolerance is applied because MSP
-- stores these as floats and the last decimal place drifts.
WITH rolled AS (
    SELECT r.snapshot_id, r.resource_uid, r.resource_name, r.resource_quantity_unit,
           r.resource_quantity AS sheet_total,
           coalesce(sum(a.planned_quantity), 0) AS assignment_total
      FROM msp_resources r
      LEFT JOIN msp_resource_assignments a
             ON a.snapshot_id = r.snapshot_id AND a.resource_uid = r.resource_uid
     WHERE r.native_type = 'MATERIAL'
     GROUP BY 1, 2, 3, 4, 5
)
SELECT count(*)                                                            AS material_resources,
       count(*) FILTER (WHERE abs(sheet_total - assignment_total) <= 0.01) AS matching,
       count(*) FILTER (WHERE abs(sheet_total - assignment_total) >  0.01) AS MISMATCHED
  FROM rolled WHERE sheet_total IS NOT NULL;

\echo '--- 9. the worst mismatches, if any ---'
WITH rolled AS (
    SELECT r.snapshot_id, r.resource_uid, r.resource_name, r.resource_quantity_unit,
           r.resource_quantity AS sheet_total,
           coalesce(sum(a.planned_quantity), 0) AS assignment_total
      FROM msp_resources r
      LEFT JOIN msp_resource_assignments a
             ON a.snapshot_id = r.snapshot_id AND a.resource_uid = r.resource_uid
     WHERE r.native_type = 'MATERIAL'
     GROUP BY 1, 2, 3, 4, 5
)
SELECT resource_uid, left(resource_name, 30) AS resource, resource_quantity_unit AS unit,
       sheet_total, assignment_total, sheet_total - assignment_total AS difference
  FROM rolled
 WHERE sheet_total IS NOT NULL AND abs(sheet_total - assignment_total) > 0.01
 ORDER BY abs(sheet_total - assignment_total) DESC LIMIT 10;

\echo '--- 10. sample rows, the way Finance will read them ---'
SELECT a.assignment_uid, a.task_uid, left(t.name, 26) AS task, t.wbs,
       a.resource_uid, left(r.resource_name, 18) AS resource, r.native_type,
       r.bambo_resource_type, coalesce(a.quantity_unit, r.resource_quantity_unit) AS unit,
       a.planned_quantity, a.actual_quantity, a.planned_work
  FROM msp_resource_assignments a
  JOIN msp_tasks t ON t.snapshot_id = a.snapshot_id AND t.uid = a.task_uid
  LEFT JOIN msp_resources r
         ON r.snapshot_id = a.snapshot_id AND r.resource_uid = a.resource_uid
 WHERE a.planned_quantity IS NOT NULL
 ORDER BY t.outline_number NULLS LAST LIMIT 12;

ROLLBACK;

-- =====================================================================================
-- PASS when: section 5 reports 0 broken for all four relations; no duplicate
-- snapshot-local keys; no null identifiers; zero quantity_without_unit; MISMATCHED = 0 in
-- section 8.
--
-- SECTION 5 IS THE IMPORTANT ONE. Three of those four relationships have no foreign key --
-- the migration role has no REFERENCES privilege on Core -- so this query is what enforces
-- them. A non-zero count means the importer published a feed it should have refused.
--
-- EXPECTED AND NOT A FAILURE: with_actual_quantity = 0 while the planner has recorded no
-- material progress, and unclassified > 0 for WORK resources MSP gives no basis to call
-- labour or equipment. Both are honest states that Finance reports as such.
-- =====================================================================================
