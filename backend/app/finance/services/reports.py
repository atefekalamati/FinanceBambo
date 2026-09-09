import csv
import io
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4

from openpyxl import Workbook
from openpyxl.chart import BarChart,Reference
from openpyxl.styles import Font

from ..domain import wbs as wbs_tree
from ..domain.monthly import DEFAULT_MONTH_COUNT,MAX_MONTH_COUNT,monthly_report
from ..domain.persian_calendar import persian_month_window
from ..domain.reports import calculate_live_report
from ..domain.progress import (finance_version_id,
    apply_progress_overrides,reference_from_header,
 snapshot_assignments,snapshot_metadata)
from ..adapters.ports import supports_current_snapshot
from ..domain.errors import FinanceDomainError
from ..domain.resources import FinanceRecordNotFound


class ReportSnapshotIncomplete(FinanceDomainError):
    code="REPORT_SNAPSHOT_INCOMPLETE"
    status=422


class MonthlyWindowUnsupported(FinanceDomainError):
    """The requested window cannot be expressed on the Persian calendar.

    A reporting date near the Gregorian epoch walks the series back past Persian year 1.
    That is bad input, not a server fault, so it is refused rather than raised out of
    date() as a 500.
    """

    code="VALIDATION_ERROR"
    status=422


def _json_value(value):
    if isinstance(value,(UUID,Decimal,date,datetime)):return str(value)
    if isinstance(value,dict):return {key:_json_value(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_json_value(item) for item in value]
    return value


def _export_cell(value):
    if not isinstance(value,str) or not value:return value
    if value[0] not in "=+-@":return value
    try:Decimal(value);return value
    except Exception:return "'"+value


REPORT_LABELS={
    "fa":{"section":"بخش","key":"کلید","value":"مقدار","summary":"خلاصه","metric":"شاخص","valueIrr":"مقدار (ریال)","breakdown":"تفکیک هزینه","resourceType":"نوع قلم","initialEstimate":"برآورد اولیه (ریال)","revisedEstimate":"برآورد اصلاح‌شده (ریال)","actualCost":"هزینه واقعی (ریال)","remainingPhysicalCost":"هزینه باقی‌مانده (ریال)","forecastFinal":"پیش‌بینی نهایی (ریال)","priceVariance":"انحراف قیمت","quantityVariance":"انحراف مقدار","resourceCode":"کد قلم","resourceTitle":"عنوان قلم","variance":"انحراف","costBreakdown":"تفکیک هزینه","irr":"ریال"},
    "en":{"section":"section","key":"key","value":"value","summary":"Summary","metric":"Metric","valueIrr":"Value (IRR)","breakdown":"Breakdown","resourceType":"Resource Type","initialEstimate":"Initial Estimate (IRR)","revisedEstimate":"Revised Estimate (IRR)","actualCost":"Actual Cost (IRR)","remainingPhysicalCost":"Remaining Physical Cost (IRR)","forecastFinal":"Forecast Final (IRR)","priceVariance":"Price Variance","quantityVariance":"Quantity Variance","resourceCode":"Resource Code","resourceTitle":"Resource Title","variance":"Variance","costBreakdown":"Cost Breakdown","irr":"IRR"},
    "ar":{"section":"القسم","key":"المفتاح","value":"القيمة","summary":"الملخص","metric":"المؤشر","valueIrr":"القيمة (ريال)","breakdown":"تفصيل التكلفة","resourceType":"نوع البند","initialEstimate":"التقدير الأولي (ريال)","revisedEstimate":"التقدير المعدل (ريال)","actualCost":"التكلفة الفعلية (ريال)","remainingPhysicalCost":"تكلفة الأعمال المتبقية (ريال)","forecastFinal":"التكلفة النهائية المتوقعة (ريال)","priceVariance":"انحراف السعر","quantityVariance":"انحراف الكمية","resourceCode":"رمز البند","resourceTitle":"عنوان البند","variance":"الانحراف","costBreakdown":"تفصيل التكلفة","irr":"ريال"},
}


def _labels(locale):
    return REPORT_LABELS.get(locale,REPORT_LABELS["fa"])


class FinanceLiveReportService:
    #: One page big enough to hold a project's whole activity catalogue. The WBS tree is
    #: only a tree if every activity is in it -- reading it a page at a time would build a
    #: different tree per page, and rolling money up a partial tree gives a wrong total
    #: rather than a partial one.
    ACTIVITY_PAGE_SIZE=10000

    def __init__(self,repository,progress_provider,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc),
                 activity_provider=None):
        self.repo,self.provider,self.ids,self.clock=repository,progress_provider,id_factory,clock
        # Optional, like the resource service's: a deployment without an activity catalogue
        # still serves every other report. `by_wbs` is the one caller that needs it.
        self.activities=activity_provider

    async def _current_reference_value(self,scope,reporting_date):
        """The host's current snapshot as a Finance reference value, unsaved.

        None whenever there is nothing to pin to -- a host that does not implement
        `current_snapshot`, one with no snapshot for this project, a header describing
        another tenant, or one carrying no Core identifier. Every one of those means "no
        progress", which the report states through its warnings rather than inventing one.
        """
        if not supports_current_snapshot(self.provider):return None
        feed=await self.provider.current_snapshot(str(scope.organization_id),scope.project_id,reporting_date)
        metadata=feed.get("snapshot") if isinstance(feed,dict) else None
        return reference_from_header(metadata,scope,self.ids,self.clock,reporting_date)

    @staticmethod
    def _descriptor(row):
        """The shape repo.load and repo.snapshot return, from a stored reference row.

        `host_snapshot_id` belongs in it: without that field the caller falls back to the
        Finance UUID when asking the host for the feed, and the host has never heard of that
        value. A second request hid the bug, because it reads the row back from the database.
        """
        return {"progress_snapshot_ref_id":row["id"],
                "progress_snapshot_id":row["progress_snapshot_id"],
                "host_snapshot_id":row["host_snapshot_id"],
                "reporting_date":row["reporting_date"]}

    async def _read_current_snapshot(self,scope,reporting_date):
        """The host's current snapshot, **without writing anything**.

        `GET /reports/live` and `GET /overview` reach this. Viewing a page must not insert a
        row, and `/overview` is gated only by `finance.view` -- a read permission that must
        not imply a write.

        If a Finance reference already exists for this exact Core snapshot it is read and
        returned, so a pinned project keeps showing its stable Finance identifier. If none
        exists, the descriptor carries the Core identifier and no Finance UUID, because none
        exists yet. Minting one per request would hand clients an identifier that changes on
        every refresh and resolves to nothing.
        """
        value=await self._current_reference_value(scope,reporting_date)
        if value is None:return None
        if value.host_snapshot_id is None:
            # One of Finance's own source versions. Its identity is the version UUID, which
            # the provider answers to directly, so an UNPINNED read still resolves -- the
            # descriptor carries that UUID where a Core snapshot would carry a host id.
            existing=getattr(self.repo,"progress_reference_for_snapshot",None)
            if existing is not None:
                row=await existing(scope,value.progress_snapshot_id)
                if row is not None:return self._descriptor(row)
            return {"progress_snapshot_ref_id":None,
                    "progress_snapshot_id":value.progress_snapshot_id,
                    "host_snapshot_id":None,
                    "reporting_date":value.reporting_date}
        existing=getattr(self.repo,"progress_reference_for_host",None)
        if existing is not None:
            row=await existing(scope,value.host_snapshot_id)
            if row is not None:return self._descriptor(row)
        return {"progress_snapshot_ref_id":None,
                "progress_snapshot_id":None,
                "host_snapshot_id":value.host_snapshot_id,
                "reporting_date":value.reporting_date}

    async def _pin_current_snapshot(self,scope,reporting_date):
        """Record a reference to the host's current snapshot, creating it only if absent.

        Reached only from operations that are themselves writing something immutable -- an
        issued report, an override -- where the exact Core snapshot has to stay reproducible
        long after the host has moved on.
        """
        value=await self._current_reference_value(scope,reporting_date)
        if value is None:return None
        row=await self.repo.ensure_progress_reference(scope,value)
        return None if row is None else self._descriptor(row)

    async def _read_named_finance_snapshot(self,scope,progress_snapshot_id):
        """Resolve an unpinned Finance-owned source version without writing a ref."""
        feed=await self.provider.get_snapshot(
            str(scope.organization_id),scope.project_id,str(progress_snapshot_id))
        metadata=snapshot_metadata(
            feed,scope.organization_id,scope.project_id,progress_snapshot_id)
        value=reference_from_header(metadata,scope,self.ids,self.clock)
        if (value is None or value.host_snapshot_id is not None
                or str(value.progress_snapshot_id)!=str(progress_snapshot_id)):
            raise FinanceRecordNotFound("progress snapshot not found")
        return {"progress_snapshot_ref_id":None,
                "progress_snapshot_id":value.progress_snapshot_id,
                "host_snapshot_id":None,
                "reporting_date":value.reporting_date}

    async def _calculate(self,scope,reporting_date,progress_snapshot_id,pin=False):
        """Calculate the report. `pin` decides whether a missing reference may be created.

        Reads pass pin=False and never write. Operations that persist something immutable
        pass pin=True, because an issued report or an override has to name the exact Core
        snapshot it used, forever.
        """
        data=await self.repo.load(scope,reporting_date)
        snapshot=data["snapshot"] if progress_snapshot_id is None else await self.repo.snapshot(scope,progress_snapshot_id)
        if snapshot is None and progress_snapshot_id is not None:
            snapshot=await self._read_named_finance_snapshot(scope,progress_snapshot_id)
        if snapshot is None and progress_snapshot_id is None:
            # Nothing recorded for this date. Ask the host what its current snapshot is,
            # rather than answering 404 for a project whose progress exists but has never
            # been referenced -- which, before this, was every real project.
            snapshot=await (self._pin_current_snapshot if pin else self._read_current_snapshot)(
                scope,reporting_date)
        if snapshot is None or snapshot["reporting_date"]>reporting_date:raise FinanceRecordNotFound("progress snapshot not found for reporting date")
        # Ask the host by the host's own identifier when there is one. Finance mints
        # `progress_snapshot_id` itself for a reference ingested from Core, and the host has
        # never heard of that value -- looking the feed up by it would 404 a snapshot that
        # exists. References that predate the Core integration have no host identifier and
        # are still looked up the way they always were.
        lookup=snapshot.get("host_snapshot_id") or snapshot["progress_snapshot_id"]
        feed=await self.provider.get_snapshot(str(scope.organization_id),scope.project_id,str(lookup))
        snapshot_metadata(feed,scope.organization_id,scope.project_id,lookup)
        for row in data["estimates"]:row["progress_snapshot_id"]=snapshot["progress_snapshot_id"]
        # No Finance reference means no stored overrides can exist -- an override carries a
        # foreign key to one. That is zero *overrides*, not zero progress: the feed is read
        # and calculated exactly as always, and a line the feed cannot answer for stays
        # missing with its warning rather than becoming a measured zero.
        overrides=(await self.repo.latest_overrides(scope,snapshot["progress_snapshot_ref_id"])
                   if hasattr(self.repo,"latest_overrides")
                   and snapshot.get("progress_snapshot_ref_id") is not None else [])
        effective_feed={**feed,"assignments":apply_progress_overrides(snapshot_assignments(feed),overrides,snapshot["progress_snapshot_id"])}
        # A Finance source version is a source these estimate lines were never recorded
        # against, so its pairing must be corroborated rather than accidental. A Core
        # snapshot keeps the historical rule: those lines WERE seeded from a Core schedule.
        header=effective_feed.get("snapshot") if isinstance(effective_feed,dict) else None
        report=calculate_live_report(data["estimates"],data["invoices"],effective_feed.get("assignments",[]),data["conversions"],data["gross_area"],
            corroborate_identity=finance_version_id(header) is not None)
        return report,data,snapshot,effective_feed

    async def live(self,scope,reporting_date:date,progress_snapshot_id=None):
        report,_data,snapshot,_feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
        return {"reporting_date":reporting_date,"progress_snapshot_id":snapshot["progress_snapshot_id"],"host_snapshot_id":snapshot.get("host_snapshot_id"),"metrics":report.metrics,"breakdown":report.breakdown,"top_price_variances":report.price_variances,"top_quantity_variances":report.quantity_variances,"warnings":report.warnings,"calculation_status":report.calculation_status,"incomplete_metric_keys":report.incomplete_metric_keys,"missing_price_count":report.missing_price_count,"excluded_estimate_line_count":report.excluded_estimate_line_count,"excluded_estimate_line_ids":report.excluded_estimate_line_ids,"progress_quality":report.progress_quality}

    OVERVIEW_FIELDS=("reporting_date","progress_snapshot_id","host_snapshot_id","metrics","breakdown","top_price_variances","top_quantity_variances","warnings","calculation_status","incomplete_metric_keys","missing_price_count","excluded_estimate_line_count","progress_quality")

    async def overview(self,scope,reporting_date:date,progress_snapshot_id=None):
        """Project the live report down to the operational fields finance.view may read."""
        report=await self.live(scope,reporting_date,progress_snapshot_id)
        return {key:report[key] for key in self.OVERVIEW_FIELDS}

    async def _activity_catalogue(self,scope):
        """The project's whole activity catalogue, keyed by activity code.

        One call per report, not one per estimate line. The tree is only a tree if every
        activity is in it, so this asks for all of them at once.
        """
        if self.activities is None:
            return {}
        value=await self.activities.list_activities(
            str(scope.organization_id),scope.project_id,None,None,1,self.ACTIVITY_PAGE_SIZE)
        rows=value[0] if isinstance(value,tuple) else value.get("items",[])
        return {row["activityExternalId"]:row for row in rows if row.get("activityExternalId")}

    async def by_wbs(self,scope,reporting_date:date,progress_snapshot_id=None,level=None,
                     parent_wbs_code=None):
        """The live report rolled up to WBS stages.

        Each node's money is produced by `calculate_live_report` over that node's own rows.
        Running the canonical engine once per node rather than summing its output is what
        keeps a node's forecast a forecast: the formula is not distributive, and adding up
        per-line results would quietly give a different answer from the project total.

        A node's figures include its whole subtree, which is what a stage heading means.
        Money that reaches no node is not hidden -- it comes back in `unattributedActualIrr`
        and `unmappedWbsActualIrr`, and those two plus the roots reconcile to the project's
        actual cost exactly.
        """
        report,data,snapshot,feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
        catalogue=await self._activity_catalogue(scope)
        nodes=wbs_tree.build_tree(catalogue.values())
        placed,unplaced_line_ids=wbs_tree.line_nodes(data["estimates"],catalogue)
        linked,unattributed,unplaced_invoices=wbs_tree.split_invoices(data["invoices"],placed)

        estimates_by_code={}
        for row in data["estimates"]:
            code=placed.get(row["id"])
            if code is not None:
                estimates_by_code.setdefault(code,[]).append(row)

        assignments=feed.get("assignments",[])
        items=[]
        for code in wbs_tree.select(nodes,level,parent_wbs_code):
            covered=wbs_tree.subtree(nodes,code)
            rows=[row for child in covered for row in estimates_by_code.get(child,[])]
            invoices=[line for row in rows for line in linked.get(row["id"],[])]
            # The same engine, the same arguments, a narrower set of rows. Gross area is
            # passed through so a node's per-area warning matches the project's; the
            # per-area metrics themselves are not part of a node's contract.
            node_report=calculate_live_report(rows,invoices,assignments,data["conversions"],
                                              data["gross_area"])
            metrics=node_report.metrics
            revised=sum((entry["revisedEstimateIrr"] for entry in node_report.breakdown),
                        wbs_tree.ZERO)
            node=nodes[code]
            items.append({
                "wbs_code":code,
                "title":node["title"],
                "parent_wbs_code":node["parentWbsCode"],
                "activity_count":len(node["activityCodes"]),
                "child_count":len(node["children"]),
                "estimate_line_count":len(rows),
                "initial_estimate_irr":metrics["initialEstimateIrr"],
                "revised_estimate_irr":revised,
                "actual_cost_irr":metrics["actualCostIrr"],
                "remaining_physical_cost_irr":metrics["remainingPhysicalCostIrr"],
                "money_required_irr":metrics["moneyRequiredToContinueIrr"],
                "forecast_final_irr":metrics["forecastFinalCostIrr"],
                "calculation_status":node_report.calculation_status,
                "breakdown":{entry["resourceType"]:entry["actualCostIrr"]
                             for entry in node_report.breakdown},
            })
        return {
            "reporting_date":reporting_date,
            "progress_snapshot_id":snapshot["progress_snapshot_id"],
            "host_snapshot_id":snapshot.get("host_snapshot_id"),
            "level":None if parent_wbs_code is not None else (1 if level is None else level),
            "parent_wbs_code":wbs_tree.normalize(parent_wbs_code),
            "items":items,
            # Purchases with no estimate line at all. Requiring one on entry would make the
            # tree tidy by making invoice capture refuse real documents, so they are counted
            # here instead of being demanded away.
            "unattributed_actual_irr":wbs_tree.actual_of(unattributed),
            # Purchases that do have an estimate line, whose activity carries no WBS code.
            "unmapped_wbs_actual_irr":wbs_tree.actual_of(unplaced_invoices),
            "unmapped_estimate_line_count":len(unplaced_line_ids),
            "totals":report.metrics,
            "calculation_status":report.calculation_status,
            "warnings":report.warnings,
        }

    DEFAULT_MONTH_COUNT=DEFAULT_MONTH_COUNT
    MAX_MONTH_COUNT=MAX_MONTH_COUNT

    async def monthly(self,scope,reporting_date:date|None,month_count=None,
                      progress_snapshot_id=None):
        """The Persian-month cost series ending on `reporting_date`.

        The window closes on the reporting date rather than the end of its Persian month,
        matching the live report's `invoice_date<=as_of`, so the last bar never includes
        cost dated after the date the caller asked about — and is a partial month by
        design, which `windowEnd` reports.

        The window is bounded at MAX_MONTH_COUNT months. Cost older than `windowStart` is
        outside the series, so the bars sum to the live report's actualCostIrr only when
        the window covers the whole project; both ends are in the response so a caller can
        tell which case it has.
        """
        if progress_snapshot_id is not None:
            snapshot=await self.repo.snapshot(scope,progress_snapshot_id)
            if snapshot is None:
                snapshot=await self._read_named_finance_snapshot(scope,progress_snapshot_id)
            # The immutable snapshot is authoritative. A stale date cached by a caller
            # must not make the S-curve extend beyond (or stop before) that period.
            reporting_date=snapshot["reporting_date"]
        if reporting_date is None:raise MonthlyWindowUnsupported("reportingDate is required")
        count=self.DEFAULT_MONTH_COUNT if month_count is None else int(month_count)
        if not 1<=count<=self.MAX_MONTH_COUNT:raise MonthlyWindowUnsupported("monthCount is out of range")
        try:window_start,year,month=persian_month_window(reporting_date,count)
        except ValueError as error:raise MonthlyWindowUnsupported(str(error)) from error
        amounts,documents=await self.repo.monthly_actuals(scope,window_start,reporting_date)
        return monthly_report(amounts,documents,(window_start,year,month,count),reporting_date,
                              progress_snapshot_id)

    async def variances(self,scope,reporting_date:date,progress_snapshot_id=None,variance_type="all",resource_type=None,query=None,page=1,page_size=50,sort_by=None,sort_direction="desc"):
        report,_data,_snapshot,_feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
        items=[]
        if variance_type in ("price","all"):items.extend(report.all_price_variances)
        if variance_type in ("quantity","all"):items.extend(report.all_quantity_variances)
        if resource_type:items=[item for item in items if item.get("resourceType")==resource_type]
        if query:
            term=query.casefold()
            items=[item for item in items if term in str(item.get("resourceCode","")).casefold() or term in str(item.get("resourceTitle","")).casefold() or term in str(item.get("activityExternalId","")).casefold()]
        # A mixed list has no shared variance column, so rank it by the money at stake instead.
        key=sort_by or {"price":"varianceIrr","quantity":"varianceQuantity"}.get(variance_type,"remainingPhysicalCostIrr")
        reverse=sort_direction!="asc"
        items.sort(key=lambda item:abs(item.get(key) or Decimal(0)),reverse=reverse)
        total=len(items);start=(page-1)*page_size;end=start+page_size
        return {"items":items[start:end],"page":page,"page_size":page_size,"total_items":total,"total_pages":0 if total==0 else ((total-1)//page_size)+1}

    async def issue(self,scope,reporting_date,progress_snapshot_id=None):
        # pin=True: an issued report is immutable and must stay reproducible against the
        # exact Core snapshot it used, so the reference is created here if it does not
        # already exist. A direct POST works on a fresh project -- nobody has to open the
        # live report first to bring a reference into being.
        report,data,snapshot,feed=await self._calculate(scope,reporting_date,progress_snapshot_id,pin=True)
        resource_ids=sorted({str(row["resource_id"]) for row in data["estimates"]})
        price_ids=sorted({str(row["price_version_id"]) for row in data["estimates"] if row.get("price_version_id")})
        if data["settings_id"] is None or not resource_ids or not price_ids:
            raise ReportSnapshotIncomplete("settings, resources, and effective prices are required to issue a report")
        value={"report_snapshot_id":self.ids(),"reporting_date":reporting_date,
            "progress_snapshot_ref_id":snapshot["progress_snapshot_ref_id"],"progress_snapshot_id":snapshot["progress_snapshot_id"],
            "finance_settings_id":data["settings_id"],"resource_version_ids":resource_ids,
            "estimate_revision_ids":sorted({str(row["estimate_version_id"]) for row in data["estimates"]}),
            "price_version_ids":price_ids,"unit_conversion_ids":sorted({str(row["id"]) for row in data["conversions"]}),
            "invoice_ids":sorted({str(row["invoice_id"]) for row in data["invoices"]}),
            "calculated_metrics":{key:format(item,"f") for key,item in report.metrics.items() if item is not None},
            "issued_at":self.clock()}
        payload=_json_value({"reportingDate":reporting_date,"settingsId":data["settings_id"],"grossBuiltArea":data["gross_area"],
            "progressSnapshot":feed,"estimateInputs":data["estimates"],"invoiceInputs":data["invoices"],
            "unitConversions":data["conversions"],"metrics":report.metrics,"breakdown":report.breakdown,
            "topPriceVariances":report.price_variances,"topQuantityVariances":report.quantity_variances,
            "priceVariances":report.all_price_variances,"quantityVariances":report.all_quantity_variances,
            "calculationStatus":report.calculation_status,"incompleteMetricKeys":report.incomplete_metric_keys,
            "missingPriceCount":report.missing_price_count,"excludedEstimateLineCount":report.excluded_estimate_line_count,
            "excludedEstimateLineIds":report.excluded_estimate_line_ids,"progressQuality":report.progress_quality,"warnings":report.warnings})
        await self.repo.issue(scope,value,payload,self.ids())
        return self._response(scope,value)

    async def list_snapshots(self,scope,page=1,page_size=50,reporting_date_from=None,reporting_date_to=None):
        """Page and filter in the database, so a narrow range cannot miss older reports."""
        items,total=await self.repo.list(scope,limit=page_size,offset=(page-1)*page_size,
            reporting_date_from=reporting_date_from,reporting_date_to=reporting_date_to)
        return {"items":items,"page":page,"page_size":page_size,"total_items":total,
            "total_pages":0 if total==0 else ((total-1)//page_size)+1}

    async def get_snapshot(self,scope,report_id):
        value=await self.repo.get(scope,report_id)
        if value is None:raise FinanceRecordNotFound("report snapshot not found")
        return self._response(scope,value)

    async def export(self,scope,report_id,kind):
        value=await self.repo.export_payload(scope,report_id)
        if value is None:raise FinanceRecordNotFound("report snapshot not found")
        payload=value["snapshot_payload"]
        locale=getattr(scope,"locale","fa")
        return self._csv(payload,locale) if kind=="csv" else self._xlsx(payload,locale)

    @staticmethod
    def _csv(payload,locale="fa"):
        labels=_labels(locale)
        stream=io.StringIO(newline="")
        writer=csv.writer(stream)
        writer.writerow((labels["section"],labels["key"],labels["value"]))
        for key,value in payload.get("metrics",{}).items():writer.writerow(("metrics",_export_cell(key),_export_cell(value)))
        for row in payload.get("breakdown",[]):
            kind=row.get("resourceType","")
            for key,value in row.items():
                if key!="resourceType":writer.writerow((_export_cell(f"breakdown:{kind}"),_export_cell(key),_export_cell(value)))
        for section,key in (("priceVariance","topPriceVariances"),("quantityVariance","topQuantityVariances")):
            for index,row in enumerate(payload.get(key,[]),1):
                for name,value in row.items():writer.writerow((f"{section}:{index}",_export_cell(name),_export_cell(value)))
        return ("\ufeff"+stream.getvalue()).encode("utf-8")

    @staticmethod
    def _xlsx(payload,locale="fa"):
        labels=_labels(locale)
        workbook=Workbook()
        rtl=locale in ("fa","ar")
        summary=workbook.active;summary.title=labels["summary"];summary.sheet_view.rightToLeft=rtl
        summary.append((labels["metric"],labels["valueIrr"]))
        for key,value in payload.get("metrics",{}).items():summary.append((_export_cell(key),_export_cell(value)))
        breakdown=workbook.create_sheet(labels["breakdown"]);breakdown.sheet_view.rightToLeft=rtl
        breakdown.append((labels["resourceType"],labels["initialEstimate"],labels["revisedEstimate"],labels["actualCost"],labels["remainingPhysicalCost"],labels["forecastFinal"]))
        for row in payload.get("breakdown",[]):breakdown.append(tuple(_export_cell(value) for value in (row.get("resourceType"),row.get("initialEstimateIrr"),row.get("revisedEstimateIrr"),row.get("actualCostIrr"),row.get("remainingPhysicalCostIrr"),row.get("forecastFinalIrr"))))
        for title,key,variance in ((labels["priceVariance"],"topPriceVariances","varianceIrr"),(labels["quantityVariance"],"topQuantityVariances","varianceQuantity")):
            sheet=workbook.create_sheet(title);sheet.sheet_view.rightToLeft=rtl
            sheet.append((labels["resourceCode"],labels["resourceTitle"],labels["resourceType"],labels["variance"]))
            for row in payload.get(key,[]):sheet.append(tuple(_export_cell(value) for value in (row.get("resourceCode"),row.get("resourceTitle"),row.get("resourceType"),row.get(variance))))
        for sheet in workbook.worksheets:
            for cell in sheet[1]:cell.font=Font(bold=True)
            sheet.freeze_panes="A2";sheet.auto_filter.ref=sheet.dimensions
            for column in sheet.columns:sheet.column_dimensions[column[0].column_letter].width=min(45,max(14,max(len(str(cell.value or "")) for cell in column)+2))
        if breakdown.max_row>1:
            chart=BarChart();chart.title=labels["costBreakdown"];chart.y_axis.title=labels["irr"];chart.x_axis.title=labels["resourceType"]
            chart.add_data(Reference(breakdown,min_col=2,max_col=4,min_row=1,max_row=breakdown.max_row),titles_from_data=True)
            chart.set_categories(Reference(breakdown,min_col=1,min_row=2,max_row=breakdown.max_row));breakdown.add_chart(chart,"F2")
        output=io.BytesIO();workbook.save(output);return output.getvalue()

    @staticmethod
    def _response(scope,value):
        return {"report_snapshot_id":value["report_snapshot_id"],"organization_id":scope.organization_id,"project_id":scope.project_id,
            "reporting_date":value["reporting_date"],"issued_at":value["issued_at"],"issued_by":scope.actor_user_id if value.get("issued_by") is None else value["issued_by"],
            "progress_snapshot_id":value["progress_snapshot_id"],"resource_version_ids":value["resource_version_ids"],
            "price_version_ids":value["price_version_ids"],"invoice_ids":value["invoice_ids"],
            "unit_conversion_ids":value["unit_conversion_ids"],"calculated_metrics":value["calculated_metrics"],"immutable":True}
