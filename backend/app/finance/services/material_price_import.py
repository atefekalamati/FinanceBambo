# -*- coding: utf-8 -*-
"""One import: fetch, read, decide, store -- and stop rather than publish half of it.

The order of the checks is the design. A workbook that cannot be read completely is
refused BEFORE anything is written, so the failure mode is "today's prices are yesterday's
prices, and the run says why", never "half the catalogue disappeared".

WHAT A FAILED IMPORT DOES NOT DO

  * It does not delete a provider item. A listing that stopped appearing in the sheet keeps
    its row and its observations; what changes is that its newest observation gets older,
    and the reader can see that.
  * It does not write a zero, an empty price set, or a partial one.
  * It does not touch `price_versions`, `estimate_lines`, `invoices` or `report_snapshots`.
    An observation is evidence. A Finance price is a person's decision, made elsewhere.

WHAT IT DOES WRITE

A run row, one provider row per distinct `source` in the sheet, one item row per
(provider, productId), and one observation per row -- including the rows it refused, which
are stored with `validation_status='rejected'` and their reasons, because a row that could
not be read is a fact about the sheet that somebody needs to see.
"""

import asyncio
from datetime import datetime, timezone

from ..domain.material_price_rows import PIPE_FITTING_CATEGORY, RowStatus
from ..domain.price_scope import (SCOPE_LEVELS, SCOPE_ORGANIZATION,
                                  SCOPE_PROJECT, storage_project_id)
from ..repositories.material_prices import RunAlreadyRunning, row_fingerprint
from ..domain.errors import FinanceDomainError
from .google_sheet import GoogleSheetError, export_url, fetch_workbook_as_xlsx, parse_sheet_link
from .material_price_sheet import WORKSHEET_ALLOWLIST, read_workbook, workbook_from_xlsx
from ..domain.material_specs import FROM_COLUMN, conflicts_with, extract_specs

#: The one domain every sheet observation comes from. Providers are distinguished by name
#: within it, because the sheet names a source but never a URL -- see the contract document.
SHEET_DOMAIN_PREFIX = "docs.google.com/spreadsheets"

#: Why a pipe-worksheet row that is not a pipe is inactive. Stored in words rather than as a
#: bare false, so the next reader does not have to guess whether it was a decision.
FITTING_REASON = ("this row is in the pipe worksheet but is not a pipe (fitting, valve, "
                  "tape or accessory); it is kept as imported history and excluded from "
                  "the active pipe list")


class MaterialPriceImportError(FinanceDomainError):
    """The import did not happen. Nothing was published.

    A `FinanceDomainError` so that the HTTP trigger answers 409 with a code a caller can
    branch on. Every reason this is raised is the CALLER's situation to resolve -- the
    sheet is missing a worksheet, another import is already in flight, the workbook named
    no source -- and none of them is a server fault. Raised as a bare Exception it became
    a 500, which says "we broke" about a sheet that simply is not ready.

    The CLI scripts catch this class by name and are unaffected by the new base.
    """

    status = 409
    code = "MATERIAL_PRICE_IMPORT_REFUSED"


class MaterialPriceSheetNotConfigured(MaterialPriceImportError):
    """No sheet is configured, so there is nothing to import from.

    A distinct code because the fix is distinct: this one is an operator setting an
    environment variable, not a person correcting a spreadsheet.
    """

    code = "MATERIAL_PRICE_SHEET_NOT_CONFIGURED"


class ImportOutcome:
    """What one run did, in the words the API and the operator both use."""

    def __init__(self, status, run, inserted, already_present, rejected, worksheet_report,
                 error_message=None):
        self.status = status
        self.run = run
        self.inserted = inserted
        self.already_present = already_present
        self.rejected = rejected
        self.worksheet_report = worksheet_report
        self.error_message = error_message


#: Where a configured sheet's prices belong. `project` is the default and the existing
#: behaviour: an unflagged import writes exactly what it always wrote. `organization` is
#: opted into per provider row, because which sheet is the company's daily source is a
#: business fact and not something to infer from a URL.
SCOPE_SETTING = "scope_level"


class _Scope:
    """The (organization, project) pair the repository expects, for a tick's own use.

    The HTTP path gets a real authorised scope from the router. A scheduled tick has no
    request and no actor, so it carries only the two identifiers it read out of the
    provider table -- it cannot widen what it touches, because there is nothing else on it.
    """

    __slots__ = ("organization_id", "project_id", "scope_level")

    def __init__(self, organization_id, project_id, scope_level=SCOPE_PROJECT):
        if scope_level not in SCOPE_LEVELS:
            raise ValueError("unknown price scope: %r" % (scope_level,))
        if not organization_id:
            raise ValueError("an import scope needs an organization")
        self.organization_id = organization_id
        self.scope_level = scope_level
        # ONE place decides where an organization row is stored. A caller that passed a
        # real project id alongside `organization` would otherwise file the company's
        # prices inside that project -- which is exactly the mistake a project-scoped URL
        # invites, and it would not fail, it would just be wrong.
        self.project_id = storage_project_id(scope_level, project_id)


class MaterialPriceImportService:
    """Reads one configured spreadsheet into the price-intelligence tables."""

    #: How long a successful import stays "recent enough" when nobody says otherwise.
    #: A day, because that is what this sheet is refreshed on. Held here rather than read
    #: from the environment inside the service: `app/` is deployable without the
    #: development host, and reaching into `devhost` for a number would end that.
    DEFAULT_INTERVAL_MINUTES = 1440

    def __init__(self, repository, *, sheet_link, fetch=fetch_workbook_as_xlsx, clock=None,
                 interval_minutes=None):
        self.repository = repository
        self.sheet_link = sheet_link
        self.interval_minutes = interval_minutes or self.DEFAULT_INTERVAL_MINUTES
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def due_projects(self, interval_minutes, *, force=False):
        """`(scope_row, minutes_since_last_success)` for every project that should import.

        WHICH PROJECTS. Those with an active spreadsheet provider, read from
        `price_providers` -- configuration by what is actually set up, not a second list
        somebody has to keep in step with the first. A project nobody configured a
        provider for is a project with nothing to import.

        WHEN. A project is due when its newest SUCCESSFUL run started longer ago than the
        interval. Successful, not newest: a run that failed leaves the prices exactly as
        they were, and treating it as "we imported today" would mean a broken sheet
        silences the importer for a day instead of being retried.

        `force` skips the due check and nothing else. It is the operator's override and
        the endpoint's behaviour -- somebody who asks for an import now is not asking
        whether it is time.
        """
        rows = await self.repository.projects_with_active_providers()
        due = []
        for row in rows:
            minutes = row.get("minutes_since_last_success")
            if force or minutes is None or minutes >= interval_minutes:
                due.append((row, minutes))
        return due

    async def periodic_tick(self, interval_minutes, *, force=False):
        """Import every project that is due. NEVER raises.

        Returns one outcome dict per project, in the shape the MPP importer's tick
        already uses -- `{"projectId", "status", ...}` -- because the host prints them the
        same way and two shapes would mean two ways to read a log.

            imported   rows were read and the run finished
            skipped    not due yet; `minutesSinceLastSuccess` says how long ago
            failed     the sheet or the database refused; the reason travels with it

        One project's failure never stops the next, and a failure is an OUTCOME rather
        than an exception: a scheduler loop that dies on a bad sheet stops importing
        every other project too, and the symptom is silence.
        """
        configured = await self.repository.projects_with_active_providers()
        due = await self.due_projects(interval_minutes, force=force)
        due_ids = {row["project_id"] for row, _ in due}

        outcomes = []
        for row, _minutes in due:
            # The provider row is the configuration. A tick reads the scope it was
            # marked with rather than deciding one, so activating the company's sheet is a
            # single edit on that row and no code change at all.
            scope = _Scope(row["organization_id"], row["project_id"],
                           row.get("scope_level") or SCOPE_PROJECT)
            try:
                outcome = await self.run(scope)
                outcomes.append({
                    "projectId": row["project_id"], "status": "imported",
                    "runStatus": outcome.status, "inserted": outcome.inserted,
                    "alreadyPresent": outcome.already_present,
                    "rejected": outcome.rejected})
            except MaterialPriceImportError as error:
                # Including RunAlreadyRunning, translated by `run`: another import is in
                # flight for this provider and this tick must not start a second one.
                outcomes.append({"projectId": row["project_id"], "status": "failed",
                                 "code": getattr(error, "code", None), "reason": str(error)})
            except Exception as error:  # noqa: BLE001 -- the loop must survive
                outcomes.append({"projectId": row["project_id"], "status": "failed",
                                 "code": "UNEXPECTED", "reason": str(error)})
        # Every project that was NOT due is reported as skipped, with how long ago it
        # last succeeded. A tick that did nothing and a tick that never ran look the same
        # in a log otherwise, and the difference is the whole question this mission asked.
        for row in configured:
            if row["project_id"] not in due_ids:
                outcomes.append({
                    "projectId": row["project_id"], "status": "skipped",
                    "minutesSinceLastSuccess": row.get("minutes_since_last_success")})
        return outcomes

    async def run(self, scope) -> ImportOutcome:
        if not self.sheet_link:
            raise MaterialPriceSheetNotConfigured(
                "no material price sheet is configured; set FINANCE_MATERIAL_PRICE_SHEET_URL")

        document_id, _ = parse_sheet_link(self.sheet_link)
        started_at = self._clock()

        # ------------------------------------------------ read before writing anything
        try:
            content = await self._fetch(self.sheet_link)
        except GoogleSheetError as exc:
            raise MaterialPriceImportError(str(exc)) from exc
        fetched_at = self._clock()

        sheets = await asyncio.to_thread(workbook_from_xlsx, content)
        workbook = read_workbook(sheets)
        report = {
            "worksheets": {w.title: {"read": w.read, "reason": w.reason,
                                     "rows": len(w.rows), "accepted": len(w.accepted),
                                     "rejected": len(w.rejected)}
                           for w in workbook.worksheets},
            "unknownTitles": list(workbook.unknown_titles),
            "missingTitles": list(workbook.missing_titles),
        }
        if not workbook.complete:
            # Nothing is written, and that is the protection: the previous prices stay
            # exactly as they were, and the reason is in the message rather than in a log
            # nobody reads.
            problems = [w.reason for w in workbook.refused if w.reason]
            if workbook.missing_titles:
                problems.append("worksheet(s) missing from the workbook: %s"
                                % ", ".join(workbook.missing_titles))
            raise MaterialPriceImportError(
                "the sheet was not imported and the current prices are unchanged. "
                + " ".join(problems))

        # ---------------------------------------------------- providers, then the run
        sources = sorted({row.source for row in workbook.all_rows if row.source})
        if not sources:
            raise MaterialPriceImportError(
                "the sheet named no source in any row; nothing was imported")

        providers = {}
        for name in sources:
            providers[name] = await self.repository.ensure_provider(
                scope, name=name, domain="%s/%s#%s" % (SHEET_DOMAIN_PREFIX, document_id, name))

        # One run per import, recorded against the first provider alphabetically. The
        # per-provider detail lives in worksheet_report; the run's job is to be the single
        # thing that can be in flight, which is what stops two imports interleaving.
        anchor = providers[sources[0]]["id"]
        try:
            run = await self.repository.start_run(
                scope, provider_id=anchor, document_id=document_id, started_at=started_at)
        except RunAlreadyRunning as exc:
            raise MaterialPriceImportError(str(exc)) from exc

        inserted = already = rejected = 0
        try:
            for worksheet in workbook.worksheets:
                url = export_url(document_id, worksheet.gid or WORKSHEET_ALLOWLIST.get(worksheet.title))
                for decided in worksheet.rows:
                    if decided.source is None or decided.product_id is None:
                        # Without a source there is no provider to hang it on and without an
                        # identifier there is no listing. Counted as rejected and reported in
                        # the run; it cannot be stored as an observation of nothing.
                        rejected += 1
                        continue
                    provider = providers[decided.source]
                    # What this sheet's declared columns mean for this category, typed.
                    # Anything not declared stays in `metadata` untouched -- the parser
                    # hands both back and neither is invented.
                    specs, _leftovers = extract_specs(decided.category, decided.attributes)
                    stored = await self.repository.item_specs(
                        scope, provider_id=provider["id"], external_id=decided.product_id)
                    disagreements = conflicts_with(stored, specs)
                    item = await self.repository.ensure_item(
                        scope,
                        provider_id=provider["id"],
                        external_id=decided.product_id,
                        external_name=decided.product_name or decided.product_id,
                        category=decided.category or "unknown",
                        url=url,
                        source_unit=decided.source_unit,
                        worksheet=worksheet.title,
                        active=decided.category != PIPE_FITTING_CATEGORY,
                        inactive_reason=(FITTING_REASON
                                         if decided.category == PIPE_FITTING_CATEGORY else None),
                        metadata=decided.attributes,
                        specs=specs,
                        spec_source=FROM_COLUMN if specs else None,
                        spec_conflicts=disagreements or None)
                    accepted = decided.status == RowStatus.ACCEPTED
                    written = await self.repository.record_observation(
                        scope,
                        provider_id=provider["id"],
                        provider_item_id=item["id"],
                        run_id=run["id"],
                        # What the product and supplier were CALLED on the day this price
                        # was read. The foreign keys still say which rows they are; these
                        # say what they said, so a later rename cannot rewrite the past.
                        product_external_id=decided.product_id,
                        product_name_snapshot=decided.product_name or decided.product_id,
                        provider_name_snapshot=provider.get("name") or decided.source,
                        raw_price=decided.raw_price or "(blank)",
                        price_irr=decided.price_irr,
                        secondary_price_irr=decided.secondary_price_irr,
                        secondary_price_basis=decided.secondary_price_basis,
                        source_unit=decided.source_unit,
                        source_url=url,
                        observed_at=self._observed_at(decided, fetched_at),
                        fetched_at=fetched_at,
                        validation_status="valid" if accepted else "rejected",
                        validation_reasons=decided.reasons,
                        raw_data={"worksheet": worksheet.title,
                                  "rowNumber": decided.row_number,
                                  "attributes": decided.attributes,
                                  "workflowDateRaw": decided.workflow_date_raw},
                        document_id=document_id,
                        worksheet=worksheet.title,
                        row_number=decided.row_number,
                        workflow_date_raw=decided.workflow_date_raw,
                        workflow_date_jalali=decided.workflow_date_jalali,
                        workflow_date_gregorian=decided.workflow_date_gregorian,
                        fingerprint=row_fingerprint(decided.product_id,
                                                    decided.workflow_date_raw,
                                                    decided.raw_price))
                    if written is None:
                        already += 1
                    elif accepted:
                        inserted += 1
                    else:
                        rejected += 1
        except Exception as exc:
            await self.repository.finish_run(
                scope, run["id"], status="failed", finished_at=self._clock(),
                total_items=len(workbook.all_rows), successful_items=inserted,
                failed_items=0, rejected_items=rejected, worksheet_report=report,
                error_message=str(exc)[:500])
            raise

        finished_at = self._clock()
        run = await self.repository.finish_run(
            scope, run["id"], status="succeeded", finished_at=finished_at,
            total_items=len(workbook.all_rows), successful_items=inserted,
            failed_items=0, rejected_items=rejected, worksheet_report=report,
            published_at=finished_at)
        return ImportOutcome("succeeded", run, inserted, already, rejected, report)

    @staticmethod
    def _observed_at(decided, fetched_at):
        """When this price is taken to have been true.

        The sheet states no provider observation time, so this is the workflow date when
        there is a readable one and the fetch time when there is not. `observed_at_source`
        on the row records which, so nobody later reads it as something the provider said.
        """
        if decided.workflow_date_gregorian is None:
            return fetched_at
        return datetime.combine(decided.workflow_date_gregorian,
                                datetime.min.time(), tzinfo=timezone.utc)


def validate_import(organization_id, project_id, scope_level, workbook=None):
    """Whether a configured source could be imported, WITHOUT importing it.

    Written so the company's sheet can be signed off before it exists: `workbook` is
    optional and the configuration half is checked either way. Give it a fixture and the
    content half is checked too -- which is what a test does, and what the CLI's
    `--dry-run` does against the real link.

    It never writes. There is no repository on this function at all, which is a stronger
    guarantee than a flag that has to be honoured by everything downstream: a dry run that
    can reach the database is one edit away from not being one.

    Returns a report. `ok` is True only when nothing would be refused outright; rejected
    ROWS do not make it False, because a sheet with three bad rows out of four hundred is
    a sheet worth importing and the three are reported with their reasons.
    """
    problems = []
    if not organization_id:
        problems.append({"code": "ORGANIZATION_MISSING",
                         "message": "an import needs an organization"})
    if scope_level not in SCOPE_LEVELS:
        problems.append({"code": "SCOPE_UNKNOWN",
                         "message": "unknown price scope: %r" % (scope_level,)})
    elif scope_level == SCOPE_ORGANIZATION:
        # Not an error, a statement: the caller's project is deliberately ignored, and
        # somebody reading this report should see that rather than infer it.
        problems.append({"code": "SCOPE_ORGANIZATION_SENTINEL", "severity": "info",
                         "message": "rows will be filed under %r, not %r"
                                    % (storage_project_id(scope_level, project_id),
                                       project_id)})
    elif not project_id:
        problems.append({"code": "PROJECT_MISSING",
                         "message": "a project-scoped import needs a project"})

    report = {
        "ok": not any(problem.get("severity") != "info" for problem in problems),
        "scopeLevel": scope_level,
        "storageProjectId": storage_project_id(scope_level, project_id)
                            if scope_level in SCOPE_LEVELS else None,
        "problems": problems,
        "worksheets": [],
        "wouldInsert": 0,
        "wouldReject": 0,
        "written": False,
    }
    if workbook is None:
        return report

    for worksheet in workbook.worksheets:
        rejected = worksheet.rejected
        report["wouldInsert"] += len(worksheet.accepted)
        report["wouldReject"] += len(rejected)
        report["worksheets"].append({
            "title": worksheet.title,
            "read": worksheet.read,
            # A worksheet refused for a missing REQUIRED header says so here, which is the
            # answer to "will the new sheet's columns do".
            "reason": worksheet.reason,
            "rows": len(worksheet.rows),
            "accepted": len(worksheet.accepted),
            "rejected": len(rejected),
            # Reasons, deduplicated, with a row number for each so the sheet can be fixed
            # rather than merely blamed. A unit nobody could name lands here, never in the
            # accepted pile with a guess attached.
            "rejections": sorted({(row.row_number, reason)
                                  for row in rejected for reason in (row.reasons or ())})[:20],
        })
    for title in workbook.missing_titles:
        report["problems"].append({"code": "WORKSHEET_MISSING",
                                   "message": "the source states no worksheet %r" % title})
    report["ok"] = report["ok"] and not workbook.missing_titles
    return report
