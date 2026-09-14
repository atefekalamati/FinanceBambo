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
from ..repositories.material_prices import RunAlreadyRunning, row_fingerprint
from .google_sheet import GoogleSheetError, export_url, fetch_sheet_as_xlsx, parse_sheet_link
from .material_price_sheet import WORKSHEET_ALLOWLIST, read_workbook, workbook_from_xlsx

#: The one domain every sheet observation comes from. Providers are distinguished by name
#: within it, because the sheet names a source but never a URL -- see the contract document.
SHEET_DOMAIN_PREFIX = "docs.google.com/spreadsheets"

#: Why a pipe-worksheet row that is not a pipe is inactive. Stored in words rather than as a
#: bare false, so the next reader does not have to guess whether it was a decision.
FITTING_REASON = ("this row is in the pipe worksheet but is not a pipe (fitting, valve, "
                  "tape or accessory); it is kept as imported history and excluded from "
                  "the active pipe list")


class MaterialPriceImportError(Exception):
    """The import did not happen. Nothing was published."""


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


class MaterialPriceImportService:
    """Reads one configured spreadsheet into the price-intelligence tables."""

    def __init__(self, repository, *, sheet_link, fetch=fetch_sheet_as_xlsx, clock=None):
        self.repository = repository
        self.sheet_link = sheet_link
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def run(self, scope) -> ImportOutcome:
        if not self.sheet_link:
            raise MaterialPriceImportError(
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
                url = export_url(document_id, WORKSHEET_ALLOWLIST.get(worksheet.title))
                for decided in worksheet.rows:
                    if decided.source is None or decided.product_id is None:
                        # Without a source there is no provider to hang it on and without an
                        # identifier there is no listing. Counted as rejected and reported in
                        # the run; it cannot be stored as an observation of nothing.
                        rejected += 1
                        continue
                    provider = providers[decided.source]
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
                        metadata=decided.attributes)
                    accepted = decided.status == RowStatus.ACCEPTED
                    written = await self.repository.record_observation(
                        scope,
                        provider_id=provider["id"],
                        provider_item_id=item["id"],
                        run_id=run["id"],
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
