# -*- coding: utf-8 -*-
"""Persistence for the materials a person says an MSP activity consumes.

Append-only, and the order of the two statements is enforced by the database rather than by
care: `ux_price_component_live` is UNIQUE over the live version of one component, so
inserting the new version before retiring the old would put two live rows there for the
length of the statement. The supersede happens FIRST and the insert second, inside one
transaction -- which also means a failure leaves the previous version live rather than
leaving the line short a material.
"""

from uuid import uuid4

from psycopg.rows import dict_row

#: Named rather than `*`: `ApiModel` forbids unknown fields, so a `SELECT *` that picks up a
#: new column becomes a 500 on a response nobody changed.
_COLUMNS = """
    id, component_id, organization_id, project_id, estimate_line_id, finance_resource_id,
    provider_item_id, category, provider_id, product_type, selected_unit,
    source_price_unit, source_price_basis, usage_mode, usage_quantity_decimal, usage_unit,
    conversion_status, conversion_factor_id, converted_daily_unit_price_irr,
    component_quantity_decimal, component_daily_cost_irr, status, reason, active, version,
    effective_from, superseded_at, superseded_by, created_by, created_at
"""

_INSERT = """
    INSERT INTO finance_item_price_mapping_components
        (id, component_id, organization_id, project_id, estimate_line_id,
         finance_resource_id, provider_item_id, category, provider_id, product_type,
         selected_unit, source_price_unit, source_price_basis, usage_mode,
         usage_quantity_decimal, usage_unit, conversion_status, conversion_factor_id,
         converted_daily_unit_price_irr, component_quantity_decimal,
         component_daily_cost_irr, status, reason, active, version, effective_from,
         created_by)
    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
           %s, %s, %s, %s, %s, coalesce(max(c.version), 0) + 1, %s, %s
      FROM finance_item_price_mapping_components c
     WHERE c.organization_id = %s AND c.project_id = %s AND c.component_id = %s
 RETURNING
"""


class PsycopgItemPriceComponentRepository:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------------- reading

    async def live_for_project(self, s):
        """Every live component of the project, for a whole-table read.

        One query for the page rather than one per row: the estimate has hundreds of lines
        and the table renders all of them at once. Inactive components come back too --
        the caller excludes them from the total and still needs to know they exist.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mapping_components"
                " WHERE organization_id=%s AND project_id=%s AND superseded_at IS NULL"
                " ORDER BY created_at",
                (s.organization_id, s.project_id))
            return await c.fetchall()

    async def live_for_line(self, s, estimate_line_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mapping_components"
                " WHERE organization_id=%s AND project_id=%s AND estimate_line_id=%s"
                " AND superseded_at IS NULL ORDER BY created_at",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchall()

    async def history_for_line(self, s, estimate_line_id):
        """Every version of every component of this line, newest first.

        What a report issued last month was calculated from is in here.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mapping_components"
                " WHERE organization_id=%s AND project_id=%s AND estimate_line_id=%s"
                " ORDER BY component_id, version DESC",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchall()

    async def live_component(self, s, estimate_line_id, component_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + _COLUMNS + " FROM finance_item_price_mapping_components"
                " WHERE organization_id=%s AND project_id=%s AND estimate_line_id=%s"
                " AND component_id=%s AND superseded_at IS NULL",
                (s.organization_id, s.project_id, estimate_line_id, component_id))
            return await c.fetchone()

    # ------------------------------------------------------------------------- writing

    async def append(self, s, *, component_id, estimate_line_id, values, created_by):
        """A new version of one component. Retire the live one first, then insert.

        `component_id` is the stable identity: a new material gets a fresh one, and an edit
        or a deactivation reuses it so the history reads as one thing changing rather than
        as three unrelated rows.
        """
        row_id = uuid4()
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as c:
                await c.execute(
                    "UPDATE finance_item_price_mapping_components"
                    " SET superseded_at = now(), superseded_by = %s"
                    " WHERE organization_id=%s AND project_id=%s AND component_id=%s"
                    " AND superseded_at IS NULL",
                    (row_id, s.organization_id, s.project_id, component_id))
                await c.execute(
                    _INSERT + _COLUMNS,
                    (row_id, component_id, s.organization_id, s.project_id,
                     estimate_line_id, values.get("finance_resource_id"),
                     values["provider_item_id"], values.get("category"),
                     values.get("provider_id"), values.get("product_type"),
                     values["selected_unit"], values.get("source_price_unit"),
                     values.get("source_price_basis"), values.get("usage_mode"),
                     values.get("usage_quantity"), values.get("usage_unit"),
                     values["conversion_status"], values.get("conversion_factor_id"),
                     values.get("converted_daily_unit_price_irr"),
                     values.get("component_quantity"),
                     values.get("component_daily_cost_irr"), values.get("status"),
                     values["reason"], values.get("active", True),
                     values["effective_from"], created_by,
                     s.organization_id, s.project_id, component_id))
                return await c.fetchone()

    # ------------------------------------------------------- what the pricing needs
    #
    # These three read the OTHER modules' tables. They are here rather than duplicated in
    # the service because they are queries, and a query belongs with the other queries.

    async def latest_prices_for_items(self, s, provider_item_ids):
        """The newest VALIDATED observation behind each listing a component names.

        An observation the importer flagged is evidence that something was wrong with the
        row, not a price to put in front of a reader.
        """
        if not provider_item_ids:
            return {}
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (o.provider_item_id)
                          o.provider_item_id, o.normalized_price_irr, o.normalized_unit,
                          o.source_unit, o.source_currency, o.workflow_date_jalali,
                          o.workflow_date_gregorian,
                          i.external_name, i.external_id, i.category, i.active,
                          i.source_worksheet, i.metadata, p.name AS provider_name,
                          -- What a person said about THIS listing. The worksheet states a
                          -- unit for rebar and for nothing else, so for most of the
                          -- catalogue the label is the only thing that can say what the
                          -- price is per. Read here so the pricing agrees with the prices
                          -- page, which has always asked the label first.
                          l.source_unit AS label_source_unit,
                          l.product_type AS label_product_type,
                          l.display_name AS label_display_name
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
        """Live, APPROVED product measurements, keyed by (listing, from, to).

        An unapproved factor is somebody's note; pricing from it would make a draft into a
        number in a report.
        """
        if not provider_item_ids:
            return {}
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT id, provider_item_id, from_unit, to_unit, factor, origin
                     FROM provider_item_unit_factors
                    WHERE organization_id=%s AND project_id=%s
                      AND provider_item_id = ANY(%s)
                      AND superseded_at IS NULL AND approved_by IS NOT NULL""",
                (s.organization_id, s.project_id, list(provider_item_ids)))
            return {(r["provider_item_id"], r["from_unit"], r["to_unit"]): r
                    for r in await c.fetchall()}

    async def line_quantities(self, s):
        """The quantity each line is priced on, for every line of the project.

        The file's own quantity from the ACTIVE source version, which is what the items
        page already shows. Read here rather than recomputed so a component's quantity and
        the «مقدار» beside it on the same row cannot disagree.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT l.id AS estimate_line_id,
                          coalesce(l.original_quantity,
                                   (SELECT c.quantity
                                      FROM estimate_line_source_completions c
                                     WHERE c.estimate_line_id = l.id)) AS quantity
                     FROM estimate_lines l
                    WHERE l.organization_id=%s AND l.project_id=%s
                      AND l.deleted_at IS NULL""",
                (s.organization_id, s.project_id))
            return {r["estimate_line_id"]: r["quantity"] for r in await c.fetchall()}

    async def line_context(self, s, estimate_line_id):
        """What the schedule says about the line: its name, unit, quantity and MSP cost.

        The panel's header. Read in one query so the panel can name the activity a person
        is pricing before they choose anything.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT l.id, l.resource_id, l.activity_external_id,
                          l.source_assignment_uid, l.source_task_uid,
                          r.source_resource_uid, r.title AS resource_title,
                          r.base_unit, r.resource_type,
                          coalesce(l.original_quantity,
                                   (SELECT x.quantity
                                      FROM estimate_line_source_completions x
                                     WHERE x.estimate_line_id = l.id)) AS quantity,
                          l.original_unit_price_irr,
                          (SELECT m.source_assignment_cost_irr FROM finance_mpp_rows m
                            WHERE m.organization_id=l.organization_id
                              AND m.project_id=l.project_id
                              AND m.source_assignment_uid=l.source_assignment_uid
                            LIMIT 1) AS msp_cost_irr,
                          (SELECT m.normalized_unit FROM finance_mpp_rows m
                            WHERE m.organization_id=l.organization_id
                              AND m.project_id=l.project_id
                              AND m.source_assignment_uid=l.source_assignment_uid
                            LIMIT 1) AS msp_unit
                     FROM estimate_lines l
                     LEFT JOIN finance_resources r ON r.id = l.resource_id
                    WHERE l.organization_id=%s AND l.project_id=%s AND l.id=%s
                      AND l.deleted_at IS NULL""",
                (s.organization_id, s.project_id, estimate_line_id))
            return await c.fetchone()

    async def listing_exists(self, s, provider_item_id):
        """Whether this project has this listing at all. Inactive ones count: an operator
        maps the product that was actually used, and one that left the sheet is still it."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT category, provider_id FROM provider_items"
                " WHERE organization_id=%s AND project_id=%s AND id=%s",
                (s.organization_id, s.project_id, provider_item_id))
            return await c.fetchone()

    async def product_types(self, s, *, category=None, provider_id=None):
        """The product types somebody has labelled, scoped by category AND provider.

        Scoped by both because the modal's dropdowns cascade: choosing «میلگرد» then
        «AhanOnline» must not offer a type that only exists on another supplier's brick.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT l.product_type
                     FROM provider_item_labels l
                     JOIN provider_items i ON i.id = l.provider_item_id
                    WHERE l.organization_id=%s AND l.project_id=%s
                      AND l.superseded_at IS NULL AND l.product_type IS NOT NULL
                      AND (%s::text IS NULL OR i.category = %s)
                      AND (%s::uuid IS NULL OR i.provider_id = %s)
                    ORDER BY 1""",
                (s.organization_id, s.project_id, category, category,
                 provider_id, provider_id))
            return [r["product_type"] for r in await c.fetchall()]

    async def providers(self, s, category=None):
        """Suppliers, scoped to a category when one is chosen.

        A provider that sells no brick must not appear under «آجر»: the cascade would then
        offer a choice that yields an empty product list, which reads as a broken page.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT p.id, p.name FROM price_providers p
                     JOIN provider_items i ON i.provider_id = p.id
                    WHERE p.organization_id=%s AND p.project_id=%s AND p.active
                      AND i.active
                      AND (%s::text IS NULL OR i.category = %s)
                    ORDER BY p.name""",
                (s.organization_id, s.project_id, category, category))
            return await c.fetchall()
