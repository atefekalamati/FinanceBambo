# -*- coding: utf-8 -*-
"""The rows behind "Items and Estimates", read from the schedule that is authoritative.

ONE SOURCE VERSION, NAMED

`finance_mpp_rows` holds every import ever done -- on the audited project the same 789-row
file three times over -- so a query that forgets to scope by version reports each
assignment three times and trebles the project total. The newest LIVE version is chosen
here and its id travels back with the answer, because "which file is this" is part of the
answer and not a detail of how it was fetched.

Live, not merely newest: 0028 lets a version say it has been superseded, and a superseded
version is one nobody may read. Two versions are live on the audited project -- the oldest
is still cited by 289 estimate-line completions -- and the newest of those is the one the
listing reads.

WHY THE ASSIGNMENT IS THE GRAIN

A resource assigned to five activities is five assignments and ONE resource. The query
returns assignment rows; the service groups them. Aggregating in SQL and returning both
levels would let a caller add a resource total to its own assignment totals, which is the
double count the approved model names explicitly.

`DISTINCT ON (source_assignment_uid)` because one assignment can appear on several
`finance_mpp_rows` rows within a version -- the table is row-per-task-per-assignment and a
resource used twice in one task lands twice. The assignment uid is the identity; the row
is a carrier.
"""

from psycopg.rows import dict_row


#: The newest version anybody may still read. Superseded versions are excluded by 0028's
#: column rather than by guessing from `imported_at` alone.
LIVE_VERSION = """
SELECT id, source_file_name_safe, source_sha256, imported_at, reporting_date, row_count
  FROM finance_mpp_source_versions
 WHERE organization_id=%s AND project_id=%s AND status='ready' AND superseded_at IS NULL
 ORDER BY imported_at DESC, id
 LIMIT 1
"""

#: Every assignment of one source version, with the Finance resource it maps to, the live
#: price mapping, and the newest valid observation of the mapped listing.
#:
#: The joins are all LEFT: an assignment the file states exists whether or not Finance has
#: classified it, mapped it or can price it, and a listing that dropped the unmapped ones
#: would answer "we have 45 items" for a project whose schedule names 68.
ASSIGNMENTS = """
SELECT DISTINCT ON (m.source_assignment_uid)
       m.source_assignment_uid, m.source_resource_uid, m.source_task_uid,
       m.task_name, m.task_wbs, m.resource_name, m.resource_type AS file_resource_type,
       m.resource_unit, m.normalized_unit, m.unit_source, m.unit_confidence,
       m.source_assignment_units, m.source_assignment_cost_irr, m.source_cost,
       m.source_actual_cost,
       r.id AS resource_id, r.title AS resource_title, r.resource_type, r.base_unit,
       r.source_resource_uid AS finance_resource_uid,
       l.id AS estimate_line_id, l.legacy_status,
       map.id AS mapping_id, map.provider_item_id, map.selected_unit,
       map.conversion_status, map.version AS mapping_version,
       pi.external_name AS mapped_product_name, pi.category AS mapped_product_category,
       obs.normalized_price_irr AS current_unit_price_irr,
       obs.source_unit AS price_source_unit,
       obs.workflow_date_gregorian AS price_as_of
  FROM finance_mpp_rows m
  LEFT JOIN finance_resources r
         ON r.organization_id=m.organization_id AND r.project_id=m.project_id
        AND r.source_resource_uid=m.source_resource_uid AND r.deleted_at IS NULL
  LEFT JOIN estimate_lines l
         ON l.organization_id=m.organization_id AND l.project_id=m.project_id
        AND l.source_assignment_uid=m.source_assignment_uid AND l.deleted_at IS NULL
  LEFT JOIN LATERAL (
       SELECT x.* FROM finance_item_price_mappings x
        WHERE x.organization_id=m.organization_id AND x.project_id=m.project_id
          AND x.source_assignment_uid=m.source_assignment_uid
          AND x.superseded_at IS NULL
        ORDER BY x.version DESC LIMIT 1) map ON TRUE
  LEFT JOIN provider_items pi
         ON pi.organization_id=m.organization_id AND pi.project_id=m.project_id
        AND pi.id=map.provider_item_id
  LEFT JOIN LATERAL (
       SELECT o.normalized_price_irr, o.source_unit, o.workflow_date_gregorian
         FROM price_observations o
        WHERE o.organization_id=m.organization_id AND o.project_id=m.project_id
          AND o.provider_item_id=map.provider_item_id
          AND o.validation_status='valid'
        ORDER BY o.workflow_date_gregorian DESC NULLS LAST, o.fetched_at DESC, o.id
        LIMIT 1) obs ON TRUE
 WHERE m.organization_id=%s AND m.project_id=%s AND m.source_version_id=%s
   AND m.source_assignment_uid IS NOT NULL
 ORDER BY m.source_assignment_uid, m.id
"""

#: Rows the schedule does not account for. Returned separately and never mixed into the
#: hierarchy above: they have no assignment to be a child of, and putting them in the tree
#: under a placeholder resource is exactly the fabricated identity the model forbids.
LEGACY_LINES = """
SELECT l.id, l.legacy_status, l.source, l.created_at, l.original_quantity,
       l.original_unit_price_irr, r.title AS resource_title, r.resource_type,
       EXISTS (SELECT 1 FROM invoice_lines il
                WHERE il.organization_id=l.organization_id
                  AND il.project_id=l.project_id AND il.estimate_line_id=l.id)
           AS invoice_linked
  FROM estimate_lines l
  JOIN finance_resources r
    ON r.organization_id=l.organization_id AND r.project_id=l.project_id
   AND r.id=l.resource_id
 WHERE l.organization_id=%s AND l.project_id=%s AND l.deleted_at IS NULL
   AND l.legacy_status IS NOT NULL
 ORDER BY l.created_at, l.id
"""


class PsycopgItemsAndEstimatesRepository:
    """Reads only. Nothing in this class writes, and nothing here creates an identity."""

    def __init__(self, db):
        self.db = db

    async def live_version(self, s):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(LIVE_VERSION, (s.organization_id, s.project_id))
            return await c.fetchone()

    async def assignments(self, s, source_version_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(ASSIGNMENTS,
                            (s.organization_id, s.project_id, source_version_id))
            return await c.fetchall()

    async def legacy_lines(self, s):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(LEGACY_LINES, (s.organization_id, s.project_id))
            return await c.fetchall()
