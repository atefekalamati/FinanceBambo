# -*- coding: utf-8 -*-
"""Persistence for the link between a schedule item and a market listing.

Three reads and one write. The write is the interesting one: a mapping is versioned, so
"change this mapping" means supersede the live row and insert a new version beside it.

ORDER MATTERS, AND THE DATABASE ENFORCES IT
`ux_item_price_mapping_current_line` is a UNIQUE index over the live rows of one subject.
Inserting the new version before retiring the old one would put two live rows there for the
length of the statement, and a unique index is checked per statement, not at commit. So the
supersede happens FIRST and the insert second, both inside one transaction -- which also
means a failure leaves the previous mapping live rather than leaving the item unmapped.
"""

from uuid import uuid4

from psycopg.rows import dict_row

#: Every column a reader needs, named rather than `*`. `ApiModel` forbids unknown fields, so
#: a `SELECT *` that picks up a new column becomes a 500 on a response nobody changed.
_COLUMNS = """
    id, organization_id, project_id, estimate_line_id, finance_resource_id,
    source_assignment_uid, source_task_uid, source_resource_uid, provider_item_id,
    selected_unit, source_price_unit, source_price_basis, conversion_status,
    conversion_factor_id, version, effective_from, superseded_at, superseded_by,
    created_by, created_at, reason
"""


class PsycopgItemPriceMappingRepository:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------------- reading

    async def current_for_project(self, s):
        """Every live mapping of this project, keyed for a whole-table read.

        One query for the page rather than one per row: the estimate has hundreds of lines
        and the table renders all of them.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mappings"
                " WHERE organization_id=%s AND project_id=%s AND superseded_at IS NULL",
                (s.organization_id, s.project_id))
            return await c.fetchall()

    async def current_for_line(self, s, estimate_line_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mappings"
                " WHERE organization_id=%s AND project_id=%s AND estimate_line_id=%s"
                " AND superseded_at IS NULL",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchone()

    async def history_for_line(self, s, estimate_line_id):
        """Every version, newest first. What a report was priced against is in here."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mappings"
                " WHERE organization_id=%s AND project_id=%s AND estimate_line_id=%s"
                " ORDER BY version DESC",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchall()

    async def latest_prices_for_items(self, s, provider_item_ids):
        """The newest observation behind each listing a mapping names.

        `DISTINCT ON` over the ordered set rather than a correlated subquery per row: the
        page asks about every mapped listing at once, and this is one pass.

        Only validated observations count. An observation the importer flagged is evidence
        that something was wrong with the row, not a price to put in front of a reader.
        """
        if not provider_item_ids:
            return {}
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (o.provider_item_id)
                          o.provider_item_id, o.normalized_price_irr, o.normalized_unit,
                          o.source_unit, o.source_currency, o.raw_price,
                          o.workflow_date_gregorian, o.workflow_date_jalali,
                          o.observed_at, o.validation_status,
                          i.external_name, i.external_id, i.category, i.active,
                          i.source_worksheet, p.name AS provider_name,
                          -- See the component repository: the worksheet states a unit for
                          -- rebar and for nothing else, so a person's label is usually the
                          -- only thing that can say what a price is per.
                          l.source_unit AS label_source_unit
                     FROM price_observations o
                     JOIN provider_items i ON i.id = o.provider_item_id
                     LEFT JOIN price_providers p ON p.id = i.provider_id
                     LEFT JOIN provider_item_labels l
                            ON l.provider_item_id = i.id
                           AND l.organization_id = o.organization_id
                           AND l.project_id = o.project_id
                           AND l.superseded_at IS NULL
                    WHERE o.organization_id=%s AND o.project_id=%s
                      AND o.provider_item_id = ANY(%s)
                      AND o.validation_status = 'valid'
                    ORDER BY o.provider_item_id,
                             o.workflow_date_gregorian DESC NULLS LAST,
                             o.observed_at DESC, o.created_at DESC""",
                (s.organization_id, s.project_id, list(provider_item_ids)))
            return {row["provider_item_id"]: row for row in await c.fetchall()}

    async def approved_factors_for_items(self, s, provider_item_ids):
        """Live, approved product measurements, keyed by (listing, from, to).

        Only approved ones: an unapproved factor is somebody's note, and pricing from it
        would make a draft into a number in a report.
        """
        if not provider_item_ids:
            return {}
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT id, provider_item_id, from_unit, to_unit, factor, factor_type,
                          origin, approved_by
                     FROM provider_item_unit_factors
                    WHERE organization_id=%s AND project_id=%s
                      AND provider_item_id = ANY(%s)
                      AND superseded_at IS NULL AND approved_by IS NOT NULL""",
                (s.organization_id, s.project_id, list(provider_item_ids)))
            return {(r["provider_item_id"], r["from_unit"], r["to_unit"]): r
                    for r in await c.fetchall()}

    async def candidates(self, s, *, category=None, query=None, provider_id=None,
                         product_type=None, page=1, page_size=25, only_active=True):
        """Listings a person could choose from, newest price first.

        Filtered by the things a Finance user actually knows about the item in front of
        them -- what it is made of, who sells it, what it is called -- and never ranked by
        price. Offering the cheapest first is a policy, and a policy nobody configured
        must not arrive disguised as an ordering.
        """
        where = ["i.organization_id=%s", "i.project_id=%s"]
        params = [s.organization_id, s.project_id]
        if only_active:
            where.append("i.active")
        if category:
            where.append("i.category=%s")
            params.append(category)
        if provider_id:
            where.append("i.provider_id=%s")
            params.append(provider_id)
        if product_type:
            where.append("""EXISTS (SELECT 1 FROM provider_item_labels l
                                     WHERE l.provider_item_id=i.id
                                       AND l.superseded_at IS NULL
                                       AND l.product_type=%s)""")
            params.append(product_type)
        if query:
            # Matched against the name AND the external id: an operator pastes either.
            where.append("(i.external_name ILIKE %s OR i.external_id ILIKE %s)")
            params.extend(["%%%s%%" % query, "%%%s%%" % query])
        where = " AND ".join(where)

        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total FROM provider_items i WHERE " + where,
                            params)
            total = (await c.fetchone())["total"]
            await c.execute(
                f"""SELECT i.id AS provider_item_id, i.external_id, i.external_name,
                           i.category, i.source_unit, i.metadata, i.active,
                           i.inactive_reason, i.source_worksheet,
                           p.name AS provider_name, p.id AS provider_id,
                           o.normalized_price_irr, o.raw_price, o.source_currency,
                           o.normalized_unit, o.workflow_date_jalali,
                           o.workflow_date_gregorian,
                           l.product_type, l.display_name, l.source_basis
                      FROM provider_items i
                      LEFT JOIN price_providers p ON p.id = i.provider_id
                      LEFT JOIN LATERAL (
                           SELECT normalized_price_irr, raw_price, source_currency,
                                  normalized_unit, workflow_date_jalali,
                                  workflow_date_gregorian
                             FROM price_observations
                            WHERE provider_item_id = i.id AND validation_status='valid'
                            ORDER BY workflow_date_gregorian DESC NULLS LAST,
                                     observed_at DESC, created_at DESC
                            LIMIT 1) o ON true
                      LEFT JOIN LATERAL (
                           SELECT product_type, display_name, source_basis
                             FROM provider_item_labels
                            WHERE provider_item_id = i.id AND superseded_at IS NULL
                            ORDER BY version DESC LIMIT 1) l ON true
                     WHERE {where}
                     ORDER BY i.category, i.external_name, i.external_id
                     LIMIT %s OFFSET %s""",
                params + [page_size, max(0, (page - 1) * page_size)])
            return await c.fetchall(), total

    async def listing_exists(self, s, provider_item_id):
        """Whether this project has this listing. Active or not -- see the caller."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT 1 FROM provider_items
                    WHERE organization_id=%s AND project_id=%s AND id=%s""",
                (s.organization_id, s.project_id, provider_item_id))
            return await c.fetchone() is not None

    async def product_types(self, s, category=None):
        """The product types somebody has labelled, for the modal's filter."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT l.product_type
                     FROM provider_item_labels l
                     JOIN provider_items i ON i.id = l.provider_item_id
                    WHERE l.organization_id=%s AND l.project_id=%s
                      AND l.superseded_at IS NULL AND l.product_type IS NOT NULL
                      AND (%s::text IS NULL OR i.category = %s)
                    ORDER BY 1""",
                (s.organization_id, s.project_id, category, category))
            return [r["product_type"] for r in await c.fetchall()]

    async def providers(self, s):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT id, name FROM price_providers
                    WHERE organization_id=%s AND project_id=%s AND active
                    ORDER BY name""",
                (s.organization_id, s.project_id))
            return await c.fetchall()

    async def line_context(self, s, estimate_line_id):
        """What the schedule says about the line being mapped.

        The MSP identifiers travel onto the mapping so it stays legible across re-imports,
        and the quantity is what the cost is computed from.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT l.id, l.resource_id, l.activity_external_id,
                          l.source_assignment_uid, l.source_task_uid,
                          r.source_resource_uid, r.title AS resource_title,
                          r.base_unit, r.resource_type
                     FROM estimate_lines l
                     LEFT JOIN finance_resources r ON r.id = l.resource_id
                    WHERE l.organization_id=%s AND l.project_id=%s AND l.id=%s
                      AND l.deleted_at IS NULL""",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchone()

    async def line_quantities(self, s):
        """The quantity each line is priced on, for every line of the project.

        The file's own material quantity from the ACTIVE source version, which is what the
        items page already shows as «مقدار». Read here rather than recomputed so the cost
        and the quantity beside it cannot disagree.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT l.id AS estimate_line_id,
                          coalesce(l.original_quantity,
                                   (SELECT c.quantity
                                      FROM estimate_line_source_completions c
                                     WHERE c.estimate_line_id = l.id)) AS quantity
                     FROM estimate_lines l
                    WHERE l.organization_id=%s AND l.project_id=%s AND l.deleted_at IS NULL""",
                (s.organization_id, s.project_id))
            return {r["estimate_line_id"]: r["quantity"] for r in await c.fetchall()}

    # ------------------------------------------------------------------------- writing

    async def append_mapping(self, s, *, estimate_line_id, finance_resource_id, values,
                             created_by):
        """Retire the live mapping, then write the new version. One transaction.

        The supersede runs first because the live-row index would refuse two. It is also
        the only UPDATE the table's trigger permits, and only on a row that has none -- so
        a concurrent second call finds nothing to retire and its insert is refused by the
        same index rather than quietly making a second live mapping.
        """
        subject_is_line = estimate_line_id is not None
        subject = estimate_line_id or finance_resource_id
        new_id = uuid4()
        # Two literal statements rather than one with the column name interpolated. The
        # column is chosen from exactly two constants either way, but a reader checking
        # this file for injected SQL should not have to prove that -- and neither should
        # `test_route_authorization`, which refuses any interpolation but a composed
        # WHERE and is right to.
        retire = ("UPDATE finance_item_price_mappings"
                  " SET superseded_at = now(), superseded_by = %s"
                  " WHERE organization_id=%s AND project_id=%s AND superseded_at IS NULL"
                  + (" AND estimate_line_id=%s" if subject_is_line
                     else " AND finance_resource_id=%s"))
        insert = ("INSERT INTO finance_item_price_mappings"
                  " (id, organization_id, project_id, estimate_line_id,"
                  "  finance_resource_id, source_assignment_uid, source_task_uid,"
                  "  source_resource_uid, provider_item_id, selected_unit,"
                  "  source_price_unit, source_price_basis, conversion_status,"
                  "  conversion_factor_id, version, effective_from, created_by, reason)"
                  " SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                  "        coalesce(max(m.version), 0) + 1, %s, %s, %s"
                  "   FROM finance_item_price_mappings m"
                  "  WHERE m.organization_id=%s AND m.project_id=%s"
                  + ("  AND m.estimate_line_id=%s" if subject_is_line
                     else "  AND m.finance_resource_id=%s")
                  + " RETURNING " + _COLUMNS)
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as c:
                await c.execute(retire, (new_id, s.organization_id, s.project_id, subject))
                await c.execute(insert,
                    (new_id, s.organization_id, s.project_id, estimate_line_id,
                     finance_resource_id, values.get("source_assignment_uid"),
                     values.get("source_task_uid"), values.get("source_resource_uid"),
                     values["provider_item_id"], values["selected_unit"],
                     values.get("source_price_unit"), values.get("source_price_basis"),
                     values["conversion_status"], values.get("conversion_factor_id"),
                     values["effective_from"], created_by, values["reason"],
                     s.organization_id, s.project_id, subject))
                return await c.fetchone()
