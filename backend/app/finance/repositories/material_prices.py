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

    async def ensure_item(self, s, *, provider_id, external_id, external_name, category,
                          url, source_unit, worksheet, active, inactive_reason, metadata):
        """One listing. Re-imported rows update the display fields and nothing else.

        `active` is updated because it is derived from the row itself -- a pipe worksheet
        row that is a fitting today was a fitting yesterday -- but the row is never deleted
        and its observations are never touched.
        """
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute(
                """INSERT INTO provider_items
                       (id, organization_id, project_id, provider_id, external_id,
                        external_name, category, url, source_unit, source_worksheet,
                        active, inactive_reason, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (organization_id, project_id, provider_id, external_id)
                   DO UPDATE SET external_name = EXCLUDED.external_name,
                                 category      = EXCLUDED.category,
                                 source_unit   = EXCLUDED.source_unit,
                                 source_worksheet = EXCLUDED.source_worksheet,
                                 active        = EXCLUDED.active,
                                 inactive_reason = EXCLUDED.inactive_reason,
                                 metadata      = EXCLUDED.metadata
                   RETURNING *""",
                (uuid4(), s.organization_id, s.project_id, provider_id, external_id,
                 external_name, category, url, source_unit, worksheet, active,
                 inactive_reason, Jsonb(metadata or {})))
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
                                 workflow_date_gregorian, fingerprint):
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
                        row_fingerprint)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'TOMAN', %s, %s, %s, %s,
                           'unknown', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s)
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
                 secondary_price_irr, secondary_price_basis, fingerprint))
            return await c.fetchone()

    async def latest_observations(self, s, *, category=None, only_active=True):
        """The newest observation for each listing, with everything a reader needs to judge it.

        `DISTINCT ON` over (item) ordered by workflow date then fetch time: the newest the
        SHEET says, with the newest thing we read as the tiebreak. A listing whose only
        observations are invalid still appears -- with a null price and its reasons -- so a
        reader sees "we have this product and cannot price it" rather than nothing at all.
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
                          i.metadata, p.name AS provider_name
                     FROM price_observations o
                     JOIN provider_items i
                       ON i.organization_id=o.organization_id AND i.project_id=o.project_id
                      AND i.id=o.provider_item_id
                     JOIN price_providers p
                       ON p.organization_id=o.organization_id AND p.project_id=o.project_id
                      AND p.id=o.provider_id""" + "".join(where) +
                """ ORDER BY o.provider_item_id,
                             o.workflow_date_gregorian DESC NULLS LAST,
                             o.fetched_at DESC, o.id""",
                tuple(args))
            return await c.fetchall()

    async def observation_history(self, s, provider_item_id, *, page=1, page_size=50):
        clause = (" FROM price_observations WHERE organization_id=%s AND project_id=%s"
                  " AND provider_item_id=%s")
        args = (s.organization_id, s.project_id, provider_item_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            await c.execute(
                "SELECT *" + clause +
                " ORDER BY workflow_date_gregorian DESC NULLS LAST, fetched_at DESC, id"
                " LIMIT %s OFFSET %s", args + (page_size, (page - 1) * page_size))
            return await c.fetchall(), total

    async def invalid_observations_page(self, s, *, page=1, page_size=50):
        """Rows that were stored and could not be believed. They are findable, not hidden."""
        clause = (" FROM price_observations WHERE organization_id=%s AND project_id=%s"
                  " AND validation_status IN ('rejected', 'needs_review')")
        args = (s.organization_id, s.project_id)
        async with self.db.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT count(*) AS total" + clause, args)
            total = (await c.fetchone())["total"]
            await c.execute("SELECT *" + clause + " ORDER BY fetched_at DESC, id LIMIT %s OFFSET %s",
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
