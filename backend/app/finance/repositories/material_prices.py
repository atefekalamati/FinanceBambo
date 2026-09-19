# -*- coding: utf-8 -*-
"""Persistence for spreadsheet-sourced material prices.

Writes into the tables revision 0008 already declared and 0021 widened. Nothing here
creates a `price_versions` row: an observation is evidence, and turning evidence into an
official Finance price stays a person's decision made through the existing price service.

THREE THINGS THIS FILE IS RESPONSIBLE FOR

  * Idempotency. The row fingerprint is (productId, workflow date, price), which was
    measured to be unique across all 1993 rows of the real sheet, and a partial unique
    index refuses a second copy. Re-running the same import inserts nothing and says so.
  * Concurrency. `price_collection_runs` has a partial unique index over
    (organization, project, provider) WHERE status = 'running', so a second import against
    the same provider cannot start. It is refused by the database, not by a flag.
  * Never deleting. A provider item that stops appearing in the sheet is not removed and
    not emptied. It simply stops receiving observations, and the reader can see how old its
    newest one is.
"""

import hashlib
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..domain.material_specs import SPEC_COLUMNS


class RunAlreadyRunning(RuntimeError):
    """Another import is in flight for this provider. Two would interleave one price set."""


def row_fingerprint(product_id, workflow_date_raw, raw_price) -> str:
    """What makes two rows the same observation.

    The triple was measured on the real sheet: 0 rows of 1993 share it, and the duplicate
    productIds -- one product on two workflow dates -- differ in the date, so they stay two
    observations rather than collapsing into one. Hashed rather than stored as a tuple so
    the unique index is over one short column whatever the product name contains.
    """
    parts = "\x1f".join(str(p) if p is not None else "" for p in (product_id, workflow_date_raw, raw_price))
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


class PsycopgMaterialPriceRepository:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------ providers

    async def ensure_provider(self, s, *, name, domain, interval_minutes=1440):
        """The provider row for one sheet source, created once and reused.

        `ON CONFLICT ... DO UPDATE` on the scoped domain rather than an insert-or-select
        pair: two imports starting together would otherwise both see no row and both
        insert. The update is deliberately narrow -- it refreshes the display name and
        nothing operational, so re-importing never quietly re-enables a provider somebody
        turned off.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO price_providers
                       (id, organization_id, project_id, name, domain, provider_type,
                        crawl_method, active, default_interval_minutes)
                   VALUES (%s, %s, %s, %s, %s, 'spreadsheet', 'google_sheet', true, %s)
                   ON CONFLICT (organization_id, project_id, domain)
                   DO UPDATE SET name = EXCLUDED.name
                   RETURNING *""",
                (uuid4(), s.organization_id, s.project_id, name, domain, interval_minutes))
            return await c.fetchone()

    async def providers(self, s):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT * FROM price_providers
                    WHERE organization_id=%s AND project_id=%s AND provider_type='spreadsheet'
                    ORDER BY name""", (s.organization_id, s.project_id))
            return await c.fetchall()

    # -------------------------------------------------------------- provider items

    #: The typed specification columns an import may fill, and the order they are written
    #: in. The list itself lives in the domain, so selecting, writing, publishing and
    #: backfilling a column are four uses of one statement rather than four copies of it.
    SPEC_COLUMNS = SPEC_COLUMNS

    async def ensure_item(self, s, *, provider_id, external_id, external_name, category,
                          url, source_unit, worksheet, active, inactive_reason, metadata,
                          specs=None, spec_source=None, spec_conflicts=None):
        """One listing. Re-imported rows update the display fields and nothing else.

        `active` is updated because it is derived from the row itself -- a pipe worksheet
        row that is a fitting today was a fitting yesterday -- but the row is never deleted
        and its observations are never touched.

        A SPECIFICATION IS NOT A PRICE, AND IS NOT OVERWRITTEN LIKE ONE.

        Each typed column is filled only where it is currently NULL -- `COALESCE(stored,
        incoming)`, not `EXCLUDED`. A price is append-only and today's replaces nothing;
        a measured weight is a fact somebody established, and an arriving sheet that
        disagrees is far more often a parser or a source having gone wrong than a product
        having changed. The disagreement is recorded in `spec_conflicts` for a person, and
        the stored value stands.
        """
        columns = list(self.SPEC_COLUMNS)
        values = [(specs or {}).get(column) for column in columns]
        # COALESCE keeps whatever is already there; a NULL column takes the new value.
        keep_existing = ", ".join(
            "%s = COALESCE(provider_items.%s, EXCLUDED.%s)" % (c, c, c) for c in columns)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO provider_items
                       (id, organization_id, project_id, provider_id, external_id,
                        external_name, category, url, source_unit, source_worksheet,
                        active, inactive_reason, metadata, spec_source, spec_conflicts, """
                + ", ".join(columns) + """)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, """
                + ", ".join(["%s"] * len(columns)) + """)
                   ON CONFLICT (organization_id, project_id, provider_id, external_id)
                   DO UPDATE SET external_name = EXCLUDED.external_name,
                                 category      = EXCLUDED.category,
                                 source_unit   = EXCLUDED.source_unit,
                                 source_worksheet = EXCLUDED.source_worksheet,
                                 active        = EXCLUDED.active,
                                 inactive_reason = EXCLUDED.inactive_reason,
                                 metadata      = EXCLUDED.metadata,
                                 spec_source   = COALESCE(provider_items.spec_source,
                                                          EXCLUDED.spec_source),
                                 spec_conflicts = EXCLUDED.spec_conflicts,
                                 """ + keep_existing + """
                   -- A HAND-ENTERED LISTING IS NOT THE IMPORTER'''S TO CHANGE.
                   --
                   -- Without this a re-import that happened to generate the same
                   -- external_id would rename the product, move its category, replace
                   -- its unit and could deactivate it -- silently overwriting a price
                   -- somebody obtained by telephone with one the sheet never carried.
                   -- The row is skipped, not merged: there is nothing about a manual
                   -- listing an import knows better.
                   WHERE provider_items.origin = 'sheet'
                   RETURNING *""",
                [uuid4(), s.organization_id, s.project_id, provider_id, external_id,
                 external_name, category, url, source_unit, worksheet, active,
                 inactive_reason, Jsonb(metadata or {}), spec_source,
                 Jsonb(spec_conflicts) if spec_conflicts else None] + values)
            written = await c.fetchone()
            if written is not None:
                return written
            # The WHERE above refused the update because this listing is a manual one.
            # The importer still needs a row to hang its observation on -- refusing to
            # CHANGE the listing is not refusing to record that the sheet also quoted
            # this product -- so the untouched row is read back and returned as it
            # stands.
            await c.execute(
                """SELECT * FROM provider_items
                    WHERE organization_id=%s AND project_id=%s AND provider_id=%s
                      AND external_id=%s""",
                (s.organization_id, s.project_id, provider_id, external_id))
            return await c.fetchone()

    async def items_page(self, s, *, category=None, provider_id=None, active=None,
                         page=1, page_size=50):
        where = [" FROM provider_items WHERE organization_id=%s AND project_id=%s"]
        args = [s.organization_id, s.project_id]
        if category is not None:
            where.append(" AND category=%s")
            args.append(category)
        if provider_id is not None:
            where.append(" AND provider_id=%s")
            args.append(provider_id)
        if active is not None:
            where.append(" AND active=%s")
            args.append(active)
        clause = "".join(where)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, tuple(args))
            total = (await c.fetchone())["total"]
            await c.execute("SELECT *" + clause + " ORDER BY external_name, id LIMIT %s OFFSET %s",
                            tuple(args) + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total

    async def categories(self, s):
        """Every category present, with how many listings are active and how many are not.

        Counted rather than listed from a constant: the answer must describe the database,
        and a category with nothing in it is not a category this project has.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT category,
                          count(*)                                AS item_count,
                          count(*) FILTER (WHERE active)          AS active_count,
                          count(*) FILTER (WHERE NOT active)      AS inactive_count
                     FROM provider_items
                    WHERE organization_id=%s AND project_id=%s
                    GROUP BY category ORDER BY category""",
                (s.organization_id, s.project_id))
            return await c.fetchall()

    # ------------------------------------------------------ declared categories

    async def declared_categories(self, s):
        """Categories a person declared that this project can see.

        Its own `project` ones, its organization's, and every `global` one. A project
        does not see another project's declarations -- a word one site chose for its own
        materials is not a word the site next door has agreed to.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT id, category, label, scope_level, project_id, created_by,
                          created_at
                     FROM finance_price_categories
                    WHERE organization_id=%s
                      AND (scope_level='global'
                           OR scope_level='organization'
                           OR (scope_level='project' AND project_id=%s))
                    ORDER BY category""",
                (s.organization_id, s.project_id))
            return await c.fetchall()

    async def declare_category(self, s, *, category, label, scope_level, created_by,
                               category_id):
        """Record one declared category, or None when this scope already has it.

        The uniqueness is the table's own constraint, so two people declaring the same
        word at the same moment cannot both succeed. `ON CONFLICT DO NOTHING` turns that
        race into an empty result the caller reports as a conflict, rather than an
        integrity error surfacing as a 500.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO finance_price_categories
                       (id, organization_id, project_id, scope_level, category, label,
                        created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING
                   RETURNING id, category, label, scope_level, project_id, created_by,
                             created_at""",
                (category_id, s.organization_id,
                 s.project_id if scope_level == "project" else None,
                 scope_level, category, label, created_by))
            return await c.fetchone()

    async def category_exists(self, s, category):
        """Whether this word is already a category here -- declared, or in use by a listing.

        Both count. A category that arrived in the sheet is as real as one somebody
        declared, and requiring a declaration for it would mean re-declaring the seven
        the workbook already uses.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT EXISTS (
                       SELECT 1 FROM provider_items
                        WHERE organization_id=%s AND project_id=%s AND category=%s)
                    OR EXISTS (
                       SELECT 1 FROM finance_price_categories
                        WHERE organization_id=%s AND category=%s
                          AND (scope_level<>'project' OR project_id=%s))
                       AS present""",
                (s.organization_id, s.project_id, category,
                 s.organization_id, category, s.project_id))
            return bool((await c.fetchone())["present"])

    # ----------------------------------------------------------- manual price entry

    async def ensure_manual_provider(self, s, *, name, provider_id):
        """The one provider manual rows hang from, created on first use.

        A price with no supplier row cannot be joined to anything, and inventing a
        different provider per entry would fill the supplier list with one-offs. So there
        is exactly one per project and it is named for what it is.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT * FROM price_providers
                    WHERE organization_id=%s AND project_id=%s AND name=%s
                    LIMIT 1""",
                (s.organization_id, s.project_id, name))
            existing = await c.fetchone()
            if existing is not None:
                return existing
            await c.execute(
                """INSERT INTO price_providers
                       (id, organization_id, project_id, name, domain, provider_type,
                        crawl_method, active, default_interval_minutes)
                   VALUES (%s, %s, %s, %s, %s, 'manual', 'manual_entry', true, 1440)
                   RETURNING *""",
                (provider_id, s.organization_id, s.project_id, name,
                 "manual://%s" % s.project_id))
            return await c.fetchone()

    async def find_manual_item(self, s, *, provider_id, external_name, category):
        """The listing a previous manual entry created for this product, if any.

        Matched on the name the person typed, within the manual provider and category.
        Re-entering a price for the same product must append an observation to the
        listing that already exists, not create a second listing with the same name --
        two listings would be two rows on the prices page for one product, each with half
        its history.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT * FROM provider_items
                    WHERE organization_id=%s AND project_id=%s AND provider_id=%s
                      AND origin='manual' AND external_name=%s AND category=%s
                    LIMIT 1""",
                (s.organization_id, s.project_id, provider_id, external_name, category))
            return await c.fetchone()

    async def create_manual_item(self, s, *, provider_id, item_id, external_id,
                                 external_name, category, source_unit):
        """One hand-entered listing. `origin='manual'` is what keeps the importer off it."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO provider_items
                       (id, organization_id, project_id, provider_id, external_id,
                        external_name, category, source_unit, url, active, metadata,
                        origin)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, true, '{}'::jsonb,
                           'manual')
                   RETURNING *""",
                (item_id, s.organization_id, s.project_id, provider_id, external_id,
                 external_name, category, source_unit))
            return await c.fetchone()

    async def record_manual_observation(self, s, *, observation_id, provider_id,
                                        provider_item_id, price_irr, source_unit,
                                        observed_on, entered_by, reason, fingerprint,
                                        product_name, provider_name):
        """A hand-entered price, appended like every other observation.

        No run and no url: this was not an import and must not claim to be. The
        append-only trigger applies here exactly as it does to imported rows, which is
        why correcting a manual price means recording another one rather than editing
        this one.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO price_observations
                       (id, organization_id, project_id, provider_id, provider_item_id,
                        collection_run_id, raw_price, normalized_price_irr,
                        source_currency, source_unit, source_url, observed_at,
                        fetched_at, availability, validation_status, validation_reasons,
                        raw_data, observed_at_source, workflow_date_gregorian,
                        row_fingerprint, product_external_id, product_name_snapshot,
                        provider_name_snapshot, origin, entered_by, reason)
                   VALUES (%s, %s, %s, %s, %s,
                           NULL, %s, %s,
                           'IRR', %s, NULL, %s,
                           now(), 'available', 'valid', '[]'::jsonb,
                           '{}'::jsonb, 'workflow_date', %s,
                           %s, %s, %s,
                           %s, 'manual', %s, %s)
                   ON CONFLICT DO NOTHING
                   RETURNING *""",
                (observation_id, s.organization_id, s.project_id, provider_id,
                 provider_item_id, str(price_irr), price_irr, source_unit, observed_on,
                 observed_on, fingerprint, str(provider_item_id), product_name,
                 provider_name, entered_by, reason))
            return await c.fetchone()

    async def projects_with_active_providers(self):
        """Every (organization, project) with an active spreadsheet provider, and how
        long ago its newest SUCCESSFUL import started.

        The project list a scheduled tick works from. It is derived from what is actually
        configured rather than kept as a second list beside it -- a project with no active
        provider has nothing to import, and one somebody sets up tomorrow is picked up
        without an edit here.

        `minutes_since_last_success` is NULL when a project has never had a successful
        run. The caller treats that as due, which is what makes a freshly configured
        project import on the next tick instead of waiting out an interval it was never
        present for.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT p.organization_id, p.project_id,
                          EXTRACT(EPOCH FROM (now() - max(r.started_at))) / 60
                              AS minutes_since_last_success
                     FROM price_providers p
                     LEFT JOIN price_collection_runs r
                            ON r.organization_id = p.organization_id
                           AND r.project_id = p.project_id
                           AND r.status IN ('succeeded', 'partially_succeeded')
                    WHERE p.active AND p.crawl_method = 'google_sheet'
                    GROUP BY p.organization_id, p.project_id
                    ORDER BY p.project_id""")
            return await c.fetchall()

    # ------------------------------------------------------------------------ runs

    async def start_run(self, s, *, provider_id, document_id, started_at):
        """Begin a run, or refuse because one is already in flight.

        The refusal comes from a partial unique index, so two processes racing cannot both
        win. `UniqueViolation` is translated here rather than leaked, because the caller
        needs to tell "somebody else is importing" apart from every other database error.
        """
        from psycopg import errors

        try:
            async with self.db.cursor(row_factory=dict_row) as c:
                await c.execute(
                    """INSERT INTO price_collection_runs
                           (id, organization_id, project_id, provider_id, started_at,
                            status, source_document_id)
                       VALUES (%s, %s, %s, %s, %s, 'running', %s)
                       RETURNING *""",
                    (uuid4(), s.organization_id, s.project_id, provider_id, started_at,
                     document_id))
                return await c.fetchone()
        except errors.UniqueViolation as exc:
            raise RunAlreadyRunning(
                "an import is already running for this provider; it must finish or fail "
                "before another can start") from exc

    async def finish_run(self, s, run_id, *, status, finished_at, total_items,
                         successful_items, failed_items, rejected_items, worksheet_report,
                         error_message=None, published_at=None):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """UPDATE price_collection_runs
                      SET status=%s, finished_at=%s, total_items=%s, successful_items=%s,
                          failed_items=%s, rejected_items=%s, worksheet_report=%s,
                          error_message=%s, published_at=%s
                    WHERE organization_id=%s AND project_id=%s AND id=%s
                RETURNING *""",
                (status, finished_at, total_items, successful_items, failed_items,
                 rejected_items, Jsonb(worksheet_report or {}), error_message, published_at,
                 s.organization_id, s.project_id, run_id))
            return await c.fetchone()

    async def runs_page(self, s, *, page=1, page_size=50):
        clause = (" FROM price_collection_runs WHERE organization_id=%s AND project_id=%s")
        args = (s.organization_id, s.project_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            await c.execute("SELECT *" + clause + " ORDER BY started_at DESC, id LIMIT %s OFFSET %s",
                            args + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total

    async def last_successful_run(self, s, provider_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT * FROM price_collection_runs
                    WHERE organization_id=%s AND project_id=%s AND provider_id=%s
                      AND status IN ('succeeded', 'partially_succeeded')
                    ORDER BY started_at DESC LIMIT 1""",
                (s.organization_id, s.project_id, provider_id))
            return await c.fetchone()

    # ---------------------------------------------------------------- observations

    async def record_observation(self, s, *, provider_id, provider_item_id, run_id,
                                 raw_price, price_irr, secondary_price_irr,
                                 secondary_price_basis, source_unit, source_url,
                                 observed_at, fetched_at, validation_status,
                                 validation_reasons, raw_data, document_id, worksheet,
                                 row_number, workflow_date_raw, workflow_date_jalali,
                                 workflow_date_gregorian, fingerprint,
                                 product_external_id=None, product_name_snapshot=None,
                                 provider_name_snapshot=None):
        """Insert one observation, or do nothing because it is already there.

        `ON CONFLICT DO NOTHING` against the fingerprint index is what makes a re-import
        idempotent. It returns no row when it did nothing, which is how the caller counts
        "already present" separately from "inserted".
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO price_observations
                       (id, organization_id, project_id, provider_id, provider_item_id,
                        collection_run_id, raw_price, normalized_price_irr, source_currency,
                        source_unit, source_url, observed_at, fetched_at, availability,
                        validation_status, validation_reasons, raw_data,
                        source_document_id, source_worksheet, source_row_number,
                        workflow_date_raw, workflow_date_jalali, workflow_date_gregorian,
                        observed_at_source, secondary_price_irr, secondary_price_basis,
                        row_fingerprint,
                        product_external_id, product_name_snapshot, provider_name_snapshot)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'TOMAN', %s, %s, %s, %s,
                           'unknown', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (organization_id, project_id, provider_item_id, row_fingerprint)
                   WHERE row_fingerprint IS NOT NULL
                   DO NOTHING
                   RETURNING *""",
                (uuid4(), s.organization_id, s.project_id, provider_id, provider_item_id,
                 run_id, raw_price, price_irr, source_unit, source_url, observed_at,
                 fetched_at, validation_status, Jsonb(list(validation_reasons or ())),
                 Jsonb(raw_data or {}), document_id, worksheet, row_number,
                 workflow_date_raw, workflow_date_jalali, workflow_date_gregorian,
                 # `observed_at` holds the workflow date when the sheet stated a readable
                 # one, and the fetch time otherwise. Saying which is the whole point of
                 # the column: the sheet supplies no provider observation time at all.
                 "workflow_date" if workflow_date_gregorian is not None else "fetch_time",
                 secondary_price_irr, secondary_price_basis, fingerprint,
                 product_external_id, product_name_snapshot, provider_name_snapshot))
            return await c.fetchone()

    async def item_specs(self, s, *, provider_id, external_id):
        """The typed specifications already stored for one listing, or {} when it is new.

        Read before writing so the importer can tell an empty column from one that
        disagrees. Without it, "do not overwrite" and "record the conflict" would both be
        guesses about what was there.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                "SELECT " + ", ".join(self.SPEC_COLUMNS) + " FROM provider_items"
                " WHERE organization_id=%s AND project_id=%s AND provider_id=%s"
                "   AND external_id=%s",
                (s.organization_id, s.project_id, provider_id, external_id))
            return await c.fetchone() or {}

    async def latest_observations(self, s, *, category=None, only_active=True):
        """The newest VALID observation for each listing, and why that word matters.

        The ordering has three keys and the first one is the fix:

            1. a valid row that states a business date, before anything else
            2. newest business date -- what the SHEET says, not when we read it
            3. newest fetch, then id, so the answer never depends on scan order

        WHAT KEY 1 REPAIRS

        It used to order by date alone. So the day a supplier typed «تماس بگیرید» into the
        sheet, that row arrived with a NEWER business date than the last real price, won
        the `DISTINCT ON`, and the product's current price became null -- `invalid_source`,
        no number, in every estimate that read it. A perfectly good price from three days
        earlier was sitting in the same table, and nothing would return it until somebody
        typed a number into the sheet again.

        That is the opposite of what a rejected row is for. A row is rejected because it
        could not be believed; it should not thereby become the thing everyone believes.

        WHAT IT DELIBERATELY KEEPS

        A listing whose observations are ALL invalid still appears, with a null price and
        its reasons, because key 1 only sorts -- it does not filter. "We have this product
        and cannot price it" is an answer a reader needs; silence is not. And the newest
        rejected row is reported beside the chosen one (see `rejected_after`), so a reader
        can see that today's sheet said something unusable rather than being quietly shown
        a three-day-old number with no explanation.
        """
        where = [" WHERE o.organization_id=%s AND o.project_id=%s"]
        args = [s.organization_id, s.project_id]
        if category is not None:
            where.append(" AND i.category=%s")
            args.append(category)
        if only_active:
            where.append(" AND i.active")
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (o.provider_item_id)
                          o.*, i.external_id, i.external_name, i.category, i.active,
                          i.inactive_reason, i.source_worksheet AS item_worksheet,
                          i.metadata, p.name AS provider_name,
                          -- The listing's own typed specifications. Named rather than
                          -- `i.*`: the response forbids unknown fields, so a column added
                          -- to provider_items tomorrow must not become a 500 today.
                          i.product_code, i.manufacturer, i.grade, i.product_type,
                          i.dimensions_text, i.length_value, i.length_m,
                          i.width_value, i.height_value,
                          i.thickness_value, i.diameter_value,
                          i.weight_value, i.weight_kg, i.weight_basis,
                          i.branch_count, i.pieces_per_package, i.coverage_m2,
                          i.volume_m3, i.spec_source, i.spec_conflicts,
                          later.workflow_date_gregorian AS rejected_after_date,
                          later.raw_price AS rejected_after_raw_price,
                          later.validation_reasons AS rejected_after_reasons
                     FROM price_observations o
                     JOIN provider_items i
                       ON i.organization_id=o.organization_id AND i.project_id=o.project_id
                      AND i.id=o.provider_item_id
                     JOIN price_providers p
                       ON p.organization_id=o.organization_id AND p.project_id=o.project_id
                      AND p.id=o.provider_id
                     -- The newest row that could NOT be believed, when it is newer than
                     -- the one chosen. Reported, never selected: the exclusion has to be
                     -- visible or the reader is looking at an old price and cannot tell.
                     LEFT JOIN LATERAL (
                          SELECT r.workflow_date_gregorian, r.raw_price,
                                 r.validation_reasons
                            FROM price_observations r
                           WHERE r.organization_id=o.organization_id
                             AND r.project_id=o.project_id
                             AND r.provider_item_id=o.provider_item_id
                             AND r.validation_status <> 'valid'
                             AND r.workflow_date_gregorian IS NOT NULL
                             AND (o.workflow_date_gregorian IS NULL
                                  OR r.workflow_date_gregorian > o.workflow_date_gregorian)
                           ORDER BY r.workflow_date_gregorian DESC, r.fetched_at DESC, r.id
                           LIMIT 1) later ON TRUE""" + "".join(where) +
                """ ORDER BY o.provider_item_id,
                             (o.validation_status = 'valid'
                              AND o.workflow_date_gregorian IS NOT NULL) DESC,
                             o.workflow_date_gregorian DESC NULLS LAST,
                             o.fetched_at DESC, o.id""",
                tuple(args))
            return await c.fetchall()

    async def observation_history(self, s, provider_item_id, *, page=1, page_size=50):
        """Every observation for one listing, with BOTH identities on each row.

        The join supplies what the listing is called NOW; `o.*` carries what the sheet
        said on the day. They are returned under different names and never merged: a
        reader has to be able to see that a product was renamed, and a history that
        silently showed today's name against a year-old price would be asserting the
        product was called that then.

        `LEFT JOIN`, not `JOIN`: a deleted provider must not make the evidence of what it
        once quoted disappear from the history.
        """
        clause = (" FROM price_observations o"
                  " LEFT JOIN provider_items i"
                  "        ON i.organization_id=o.organization_id"
                  "       AND i.project_id=o.project_id AND i.id=o.provider_item_id"
                  " LEFT JOIN price_providers p"
                  "        ON p.organization_id=o.organization_id"
                  "       AND p.project_id=o.project_id AND p.id=o.provider_id"
                  " WHERE o.organization_id=%s AND o.project_id=%s"
                  " AND o.provider_item_id=%s")
        args = (s.organization_id, s.project_id, provider_item_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            await c.execute(
                "SELECT o.*, i.external_name AS current_product_name,"
                "       p.name AS current_provider_name" + clause +
                " ORDER BY o.workflow_date_gregorian DESC NULLS LAST, o.fetched_at DESC, o.id"
                " LIMIT %s OFFSET %s", args + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total

    async def invalid_observations_page(self, s, *, page=1, page_size=50):
        """Rows that were stored and could not be believed. They are findable, not hidden.

        Same shape as the history, joins included. A rejected row is the one case where
        the snapshot columns are most likely to be NULL -- a row rejected for a missing
        product id has no id to state -- and the listing's current name is often the only
        handle a reader has for finding out which product it was.
        """
        clause = (" FROM price_observations o"
                  " LEFT JOIN provider_items i"
                  "        ON i.organization_id=o.organization_id"
                  "       AND i.project_id=o.project_id AND i.id=o.provider_item_id"
                  " LEFT JOIN price_providers p"
                  "        ON p.organization_id=o.organization_id"
                  "       AND p.project_id=o.project_id AND p.id=o.provider_id"
                  " WHERE o.organization_id=%s AND o.project_id=%s"
                  " AND o.validation_status IN ('rejected', 'needs_review')")
        args = (s.organization_id, s.project_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            await c.execute(
                "SELECT o.*, i.external_name AS current_product_name,"
                "       p.name AS current_provider_name" + clause +
                " ORDER BY o.fetched_at DESC, o.id LIMIT %s OFFSET %s",
                args + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total

    # ------------------------------------------------------------- unit settings

    async def unit_settings(self, s, *, category=None):
        """The newest version of each unit decision. Older versions stay readable."""
        where = [" WHERE organization_id=%s AND project_id=%s"]
        args = [s.organization_id, s.project_id]
        if category is not None:
            where.append(" AND category=%s")
            args.append(category)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (category, resource_id) *
                     FROM material_unit_settings""" + "".join(where) +
                " ORDER BY category, resource_id, version DESC", tuple(args))
            return await c.fetchall()

    async def append_unit_setting(self, s, *, category, resource_id, display_unit, reason,
                                  created_by):
        """A new version of a unit decision. Never an update of the previous one."""
        # One statement, so the version is chosen and used without a gap for a second
        # writer to occupy. `FOR UPDATE` cannot lock an aggregate, and a read-then-insert
        # pair would let two appends both pick the same next version; here the partial
        # unique index on (scope, category, version) is what makes a race fail loudly
        # instead of quietly producing two version 2s.
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO material_unit_settings
                       (id, organization_id, project_id, category, resource_id, version,
                        display_unit, reason, created_by)
                   SELECT %s, %s, %s, %s, %s,
                          coalesce(max(version), 0) + 1, %s, %s, %s
                     FROM material_unit_settings
                    WHERE organization_id=%s AND project_id=%s AND category=%s
                      AND resource_id IS NOT DISTINCT FROM %s
                RETURNING *""",
                (uuid4(), s.organization_id, s.project_id, category, resource_id,
                 display_unit, reason, created_by,
                 s.organization_id, s.project_id, category, resource_id))
            return await c.fetchone()

    # --------------------------------------------------- product-specific factors

    async def item_unit_factors(self, s, provider_item_id):
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (from_unit, to_unit) *
                     FROM provider_item_unit_factors
                    WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                    ORDER BY from_unit, to_unit, version DESC""",
                (s.organization_id, s.project_id, provider_item_id))
            return await c.fetchall()


    async def mapped_resource_units(self, s):
        """`{provider_item_id: (resource_id, base_unit, dimension, title)}` for approved maps.

        The Finance resource's unit is read from `finance_resources.base_unit`, which is
        where an MSP/MPP import puts it and which `services/resources.py` already validates
        against the same registry. So comparing it with a chosen material unit is comparing
        two values from one vocabulary -- which is the whole reason the vocabulary had to be
        one.

        Only APPROVED mappings are joined. An unapproved one is somebody's suggestion, and a
        suggestion must not decide which unit a price is measured in.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (l.provider_item_id)
                          l.provider_item_id, l.finance_resource_id,
                          r.base_unit, r.dimension, r.title
                     FROM provider_item_labels l
                     JOIN finance_resources r
                       ON r.organization_id = l.organization_id AND r.project_id = l.project_id
                      AND r.id = l.finance_resource_id
                    WHERE l.organization_id=%s AND l.project_id=%s
                      AND l.superseded_at IS NULL AND l.mapping_approved
                      AND r.deleted_at IS NULL
                    ORDER BY l.provider_item_id, l.version DESC""",
                (s.organization_id, s.project_id))
            return {row["provider_item_id"]: row for row in await c.fetchall()}

    # ------------------------------------------------------- labels a person wrote

    async def labels(self, s, *, provider_item_id=None, active_only=True):
        """The current label for each listing.

        `DISTINCT ON (provider_item_id)` over `version DESC`: a label is superseded by a
        newer one, never updated, so the current answer is the highest version. A
        superseded row stays readable and is simply not the current one.
        """
        where = [" WHERE organization_id=%s AND project_id=%s"]
        args = [s.organization_id, s.project_id]
        if provider_item_id is not None:
            where.append(" AND provider_item_id=%s")
            args.append(provider_item_id)
        if active_only:
            where.append(" AND superseded_at IS NULL")
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT DISTINCT ON (provider_item_id) *
                     FROM provider_item_labels""" + "".join(where) +
                " ORDER BY provider_item_id, version DESC", tuple(args))
            return await c.fetchall()

    async def label_history(self, s, provider_item_id):
        """Every version, oldest first. Nothing here was ever rewritten."""
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """SELECT * FROM provider_item_labels
                    WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                    ORDER BY version""",
                (s.organization_id, s.project_id, provider_item_id))
            return await c.fetchall()

    async def append_label(self, s, *, provider_item_id, values, created_by):
        """A new version of a listing label, with the previous one marked superseded.

        Both statements in one transaction. A new version without the old one closed would
        leave two rows claiming to be current; closing the old one without a new one would
        leave a listing with no label at all. Neither is a state anybody should be able to
        read, so neither is a state that exists between these two statements.
        """
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as c:
                await c.execute(
                    """INSERT INTO provider_item_labels
                           (id, organization_id, project_id, provider_item_id, version,
                            label, display_name, category, product_type, source_unit,
                            source_basis, target_unit, finance_resource_id,
                            mapping_approved, mapping_approved_by, mapping_approved_at,
                            active, notes, reason, created_by)
                       SELECT %s, %s, %s, %s, coalesce(max(version), 0) + 1,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                         FROM provider_item_labels
                        WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                    RETURNING *""",
                    (uuid4(), s.organization_id, s.project_id, provider_item_id,
                     values.get("label"), values.get("display_name"), values.get("category"),
                     values.get("product_type"), values.get("source_unit"),
                     values.get("source_basis"), values.get("target_unit"),
                     values.get("finance_resource_id"),
                     bool(values.get("mapping_approved")),
                     values.get("mapping_approved_by"), values.get("mapping_approved_at"),
                     values.get("active", True), values.get("notes"), values["reason"],
                     created_by,
                     s.organization_id, s.project_id, provider_item_id))
                created = await c.fetchone()
                await c.execute(
                    """UPDATE provider_item_labels
                          SET superseded_at = now(), superseded_by = %s
                        WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                          AND id <> %s AND superseded_at IS NULL""",
                    (created["id"], s.organization_id, s.project_id, provider_item_id,
                     created["id"]))
                return created

    async def append_item_factor(self, s, *, provider_item_id, from_unit, to_unit, factor,
                                 factor_type, origin, reason, created_by, approved_by=None):
        """A factor somebody measured for one listing. Supersedes its own pair only.

        Scoped to the (from, to) pair rather than the whole listing: a brick can have a
        weight per piece and an area per piece at once, and recording a new weight must not
        retire the area.
        """
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as c:
                await c.execute(
                    """INSERT INTO provider_item_unit_factors
                           (id, organization_id, project_id, provider_item_id, version,
                            from_unit, to_unit, factor, origin, factor_type, reason,
                            created_by, approved_by, approved_at)
                       SELECT %s, %s, %s, %s, coalesce(max(version), 0) + 1,
                              %s, %s, %s, %s, %s, %s, %s, %s,
                              CASE WHEN %s::uuid IS NULL THEN NULL ELSE now() END
                         FROM provider_item_unit_factors
                        WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                          AND from_unit=%s AND to_unit=%s
                    RETURNING *""",
                    (uuid4(), s.organization_id, s.project_id, provider_item_id,
                     from_unit, to_unit, factor, origin, factor_type, reason, created_by,
                     approved_by, approved_by,
                     s.organization_id, s.project_id, provider_item_id, from_unit, to_unit))
                created = await c.fetchone()
                await c.execute(
                    """UPDATE provider_item_unit_factors
                          SET superseded_at = now(), superseded_by = %s
                        WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                          AND from_unit=%s AND to_unit=%s AND id <> %s
                          AND superseded_at IS NULL""",
                    (created["id"], s.organization_id, s.project_id, provider_item_id,
                     from_unit, to_unit, created["id"]))
                return created

    async def unresolved_items(self, s, *, page=1, page_size=50):
        """Listings somebody still has to say something about.

        Unresolved here means: no current label, and the sheet stated no unit either. Those
        are the rows where no amount of category-wide configuration can produce a price, so
        they are the ones worth putting in front of a person.
        """
        clause = """
             FROM provider_items i
             LEFT JOIN provider_item_labels l
               ON l.organization_id = i.organization_id AND l.project_id = i.project_id
              AND l.provider_item_id = i.id AND l.superseded_at IS NULL
            WHERE i.organization_id=%s AND i.project_id=%s AND i.active
              AND l.id IS NULL
              AND (i.source_unit IS NULL OR length(btrim(i.source_unit)) = 0)"""
        args = (s.organization_id, s.project_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            # The columns the response declares, named rather than `i.*`. A star selects
            # every column the table happens to have, and the response model forbids extras
            # -- so `i.*` turned a working query into a 500 the moment anybody added a
            # column. Naming them makes the query and the contract one change, not two.
            await c.execute(
                "SELECT i.id, i.external_id, i.external_name, i.category, i.source_unit,"
                " i.source_worksheet, i.active" + clause +
                " ORDER BY i.category, i.external_name, i.id LIMIT %s OFFSET %s",
                args + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total
