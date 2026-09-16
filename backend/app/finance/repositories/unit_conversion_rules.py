# -*- coding: utf-8 -*-
"""Persistence for scoped conversion rules and the mismatches they exist to answer.

TWO TABLES, ONE WORKFLOW

A rule says `1 from_unit = factor to_unit` at some scope; an issue says a line could not be
priced because no such rule existed. Approving a rule closes the issues it answers, and
that closing happens here in one transaction so a rule cannot be approved while the
question it settles stays open.

WHY THE READ IS DELIBERATELY WIDE

`candidates_for` fetches every APPROVED rule for one tenant and one unit pair -- usually
one or two rows -- and the choosing happens in `domain/conversion_rules.py`. Ordering by a
CASE expression here would put the precedence in a place a reader cannot find, and
precedence is the decision most likely to be argued about later.
"""

from uuid import uuid4

from psycopg.rows import dict_row

_RULE_COLUMNS = """
    id, organization_id, project_id, provider_item_id, provider_id, category, scope_type,
    from_unit, to_unit, conversion_method, factor_value, formula_definition,
    formula_schema_version, direction_definition, status, version, effective_from,
    effective_to, supersedes_rule_id, evidence_source, reason, created_by, created_at,
    approved_by, approved_at
"""

_ISSUE_COLUMNS = """
    id, organization_id, project_id, estimate_line_id, finance_resource_id,
    provider_item_id, source_task_uid, source_assignment_uid, source_resource_uid,
    resource_unit, daily_price_unit, error_code, status, first_detected_at,
    last_detected_at, occurrence_count, resolved_at, resolved_by, resolution_rule_id,
    created_at
"""


class PsycopgUnitConversionRuleRepository:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------------ rules

    async def candidates_for(self, s, *, from_unit, to_unit):
        """Every approved rule for this tenant that crosses these two units.

        Not filtered by scope: which scope wins is the domain's decision, and a query that
        pre-selected one would make the precedence invisible. A tenant has a handful of
        these, so the width costs nothing.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _RULE_COLUMNS + " FROM finance_unit_conversion_rules"
                " WHERE organization_id=%s AND status='approved'"
                "   AND from_unit=%s AND to_unit=%s"
                "   AND (project_id IS NULL OR project_id=%s)",
                (s.organization_id, from_unit, to_unit, s.project_id))
            return await c.fetchall()

    async def list_rules(self, s, *, scope_type=None, status=None, from_unit=None,
                         to_unit=None, include_other_projects=True):
        """What a person browsing Project Financial Settings sees.

        Rules with a NULL project belong to the tenant and are shown here too: a project
        editor needs to know a site-wide rule already answers their question before they
        write a narrower one that shadows it.
        """
        where = [" WHERE organization_id=%s",
                 " AND (project_id IS NULL OR project_id=%s)"]
        args = [s.organization_id, s.project_id]
        if scope_type:
            where.append(" AND scope_type=%s")
            args.append(scope_type)
        if status:
            where.append(" AND status=%s")
            args.append(status)
        if from_unit:
            where.append(" AND from_unit=%s")
            args.append(from_unit)
        if to_unit:
            where.append(" AND to_unit=%s")
            args.append(to_unit)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _RULE_COLUMNS + " FROM finance_unit_conversion_rules"
                + "".join(where)
                + " ORDER BY from_unit, to_unit, scope_type, version DESC",
                tuple(args))
            return await c.fetchall()

    async def rule(self, s, rule_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _RULE_COLUMNS + " FROM finance_unit_conversion_rules"
                " WHERE organization_id=%s AND id=%s"
                "   AND (project_id IS NULL OR project_id=%s)",
                (s.organization_id, rule_id, s.project_id))
            return await c.fetchone()

    async def history_for(self, s, rule_id):
        """Every version of one rule, newest first, following the supersede chain.

        What a report issued last month was converted by is in here.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """WITH RECURSIVE chain AS (
                       SELECT r.* FROM finance_unit_conversion_rules r
                        WHERE r.organization_id=%s AND r.id=%s
                       UNION ALL
                       SELECT r.* FROM finance_unit_conversion_rules r
                         JOIN chain ON r.id = chain.supersedes_rule_id
                                    OR r.supersedes_rule_id = chain.id
                        WHERE r.organization_id = chain.organization_id)
                   SELECT DISTINCT """ + _RULE_COLUMNS + """ FROM chain
                    ORDER BY version DESC""",
                (s.organization_id, rule_id))
            return await c.fetchall()

    async def create_rule(self, s, *, values, created_by):
        """A new rule, always at the next version for its own scope and unit pair.

        The version is chosen inside the INSERT so two writers cannot both pick the same
        next number; the partial unique index then refuses a second ACTIVE row rather than
        quietly producing two.
        """
        rule_id = uuid4()
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO finance_unit_conversion_rules
                       (id, organization_id, project_id, provider_item_id, provider_id,
                        category, scope_type, from_unit, to_unit, conversion_method,
                        factor_value, formula_definition, formula_schema_version,
                        direction_definition, status, version, effective_from,
                        supersedes_rule_id, evidence_source, reason, created_by)
                   SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          coalesce(%s, 'one_from_unit_equals_factor_to_unit'),
                          'draft', coalesce(max(r.version), 0) + 1, %s, %s, %s, %s, %s
                     FROM finance_unit_conversion_rules r
                    WHERE r.organization_id=%s AND r.scope_type=%s
                      AND r.from_unit=%s AND r.to_unit=%s
                      AND r.project_id IS NOT DISTINCT FROM %s
                      AND r.provider_item_id IS NOT DISTINCT FROM %s
                      AND r.provider_id IS NOT DISTINCT FROM %s
                      AND r.category IS NOT DISTINCT FROM %s
                RETURNING """ + _RULE_COLUMNS,
                (rule_id, s.organization_id, values.get("project_id"),
                 values.get("provider_item_id"), values.get("provider_id"),
                 values.get("category"), values["scope_type"], values["from_unit"],
                 values["to_unit"], values.get("conversion_method", "factor"),
                 values.get("factor_value"), values.get("formula_definition"),
                 values.get("formula_schema_version"),
                 values.get("direction_definition"),
                 values["effective_from"], values.get("supersedes_rule_id"),
                 values.get("evidence_source"), values["reason"], created_by,
                 s.organization_id, values["scope_type"], values["from_unit"],
                 values["to_unit"], values.get("project_id"),
                 values.get("provider_item_id"), values.get("provider_id"),
                 values.get("category")))
            return await c.fetchone()

    async def approve_rule(self, s, rule_id, *, approved_by):
        """A draft becomes the rule calculations use. One statement, so a rule cannot be
        half-approved, and the check constraint refuses an approval with no approver."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "UPDATE finance_unit_conversion_rules"
                "   SET status='approved', approved_by=%s, approved_at=now()"
                " WHERE organization_id=%s AND id=%s AND status='draft'"
                " RETURNING " + _RULE_COLUMNS,
                (approved_by, s.organization_id, rule_id))
            return await c.fetchone()

    async def supersede_rule(self, s, rule_id, *, effective_to):
        """Close a rule's window. The row stays: a calculation made under it must remain
        explainable, and a deleted rule explains nothing."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "UPDATE finance_unit_conversion_rules"
                "   SET status='superseded', effective_to=%s"
                " WHERE organization_id=%s AND id=%s AND effective_to IS NULL"
                " RETURNING " + _RULE_COLUMNS,
                (effective_to, s.organization_id, rule_id))
            return await c.fetchone()

    # ----------------------------------------------------------------------- issues

    async def record_issue(self, s, *, values):
        """One open issue per line, product and unit pair -- counted, not duplicated.

        `ON CONFLICT` against the partial unique index turns the two-hundredth preview into
        `occurrence_count = 200` on one row rather than into two hundred rows. The first
        sighting is never moved: it is when the question started.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO finance_unit_conversion_issues
                       (id, organization_id, project_id, estimate_line_id,
                        finance_resource_id, provider_item_id, source_task_uid,
                        source_assignment_uid, source_resource_uid, resource_unit,
                        daily_price_unit, error_code, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
                   ON CONFLICT (organization_id, project_id,
                                coalesce(estimate_line_id, '00000000-0000-0000-0000-000000000000'::uuid),
                                coalesce(provider_item_id, '00000000-0000-0000-0000-000000000000'::uuid),
                                coalesce(resource_unit, ''), coalesce(daily_price_unit, ''),
                                error_code)
                   WHERE status = 'open'
                   DO UPDATE SET last_detected_at = now(),
                                 occurrence_count = finance_unit_conversion_issues.occurrence_count + 1
                RETURNING """ + _ISSUE_COLUMNS,
                (uuid4(), s.organization_id, s.project_id, values.get("estimate_line_id"),
                 values.get("finance_resource_id"), values.get("provider_item_id"),
                 values.get("source_task_uid"), values.get("source_assignment_uid"),
                 values.get("source_resource_uid"), values.get("resource_unit"),
                 values.get("daily_price_unit"), values["error_code"]))
            return await c.fetchone()

    async def list_issues(self, s, *, status="open", estimate_line_id=None):
        where = [" WHERE organization_id=%s AND project_id=%s"]
        args = [s.organization_id, s.project_id]
        if status:
            where.append(" AND status=%s")
            args.append(status)
        if estimate_line_id:
            where.append(" AND estimate_line_id=%s")
            args.append(estimate_line_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _ISSUE_COLUMNS + " FROM finance_unit_conversion_issues"
                + "".join(where) + " ORDER BY last_detected_at DESC",
                tuple(args))
            return await c.fetchall()

    async def resolve_issues_for(self, s, *, from_unit, to_unit, rule_id, resolved_by,
                                 provider_item_id=None):
        """Close the open issues an approved rule answers.

        Scoped by the unit pair the rule crosses, and by the listing when the rule names
        one: a product-specific rule settles that product's question and nobody else's.
        Resolved rows are never reopened -- a later mismatch of the same shape is a new
        question that happened at a different time.
        """
        # The tenant keys are part of the statement itself rather than of a fragment
        # appended to it: a scoped UPDATE whose scope arrives by concatenation reads, to
        # anything scanning this file, as an UPDATE with no scope at all -- and the whole
        # point of that scan is that a missing tenant key is invisible in review.
        args = [resolved_by, rule_id, s.organization_id, s.project_id, from_unit, to_unit]
        optional = ""
        if provider_item_id is not None:
            optional = " AND provider_item_id=%s"
            args.append(provider_item_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "UPDATE finance_unit_conversion_issues"
                "   SET status='resolved', resolved_at=now(), resolved_by=%s,"
                "       resolution_rule_id=%s"
                " WHERE organization_id=%s AND project_id=%s AND status='open'"
                "   AND daily_price_unit=%s AND resource_unit=%s"
                + optional + " RETURNING " + _ISSUE_COLUMNS,
                tuple(args))
            return await c.fetchall()
