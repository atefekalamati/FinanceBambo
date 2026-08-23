import csv
import io
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4

from openpyxl import Workbook
from openpyxl.chart import BarChart,Reference
from openpyxl.styles import Font

from ..domain.reports import calculate_live_report
from ..domain.progress import apply_progress_overrides
from ..domain.errors import FinanceDomainError
from ..domain.resources import FinanceRecordNotFound


class ReportSnapshotIncomplete(FinanceDomainError):
    code="REPORT_SNAPSHOT_INCOMPLETE"
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
    def __init__(self,repository,progress_provider,id_factory=uuid4,clock=lambda:datetime.now(timezone.utc)):
        self.repo,self.provider,self.ids,self.clock=repository,progress_provider,id_factory,clock

    async def _calculate(self,scope,reporting_date,progress_snapshot_id):
        data=await self.repo.load(scope,reporting_date)
        snapshot=data["snapshot"] if progress_snapshot_id is None else await self.repo.snapshot(scope,progress_snapshot_id)
        if snapshot is None or snapshot["reporting_date"]>reporting_date:raise FinanceRecordNotFound("progress snapshot not found for reporting date")
        feed=await self.provider.get_snapshot(str(scope.organization_id),scope.project_id,str(snapshot["progress_snapshot_id"]))
        metadata=feed.get("snapshot") or {}
        if (str(metadata.get("organizationId"))!=str(scope.organization_id)
                or metadata.get("projectId")!=scope.project_id
                or str(metadata.get("progressSnapshotId"))!=str(snapshot["progress_snapshot_id"])):
            raise FinanceRecordNotFound("progress snapshot not found")
        for row in data["estimates"]:row["progress_snapshot_id"]=snapshot["progress_snapshot_id"]
        overrides=await self.repo.latest_overrides(scope,snapshot["progress_snapshot_ref_id"]) if hasattr(self.repo,"latest_overrides") else []
        effective_feed={**feed,"assignments":apply_progress_overrides(feed.get("assignments",[]),overrides,snapshot["progress_snapshot_id"])}
        report=calculate_live_report(data["estimates"],data["invoices"],effective_feed.get("assignments",[]),data["conversions"],data["gross_area"])
        return report,data,snapshot,effective_feed

    async def live(self,scope,reporting_date:date,progress_snapshot_id=None):
        report,_data,snapshot,_feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
        return {"reporting_date":reporting_date,"progress_snapshot_id":snapshot["progress_snapshot_id"],"metrics":report.metrics,"breakdown":report.breakdown,"top_price_variances":report.price_variances,"top_quantity_variances":report.quantity_variances,"warnings":report.warnings,"calculation_status":report.calculation_status,"incomplete_metric_keys":report.incomplete_metric_keys,"missing_price_count":report.missing_price_count,"excluded_estimate_line_count":report.excluded_estimate_line_count,"excluded_estimate_line_ids":report.excluded_estimate_line_ids,"progress_quality":report.progress_quality}

    OVERVIEW_FIELDS=("reporting_date","progress_snapshot_id","metrics","breakdown","top_price_variances","top_quantity_variances","warnings","calculation_status","incomplete_metric_keys","missing_price_count","excluded_estimate_line_count")

    async def overview(self,scope,reporting_date:date,progress_snapshot_id=None):
        """Project the live report down to the operational fields finance.view may read."""
        report=await self.live(scope,reporting_date,progress_snapshot_id)
        return {key:report[key] for key in self.OVERVIEW_FIELDS}

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
        report,data,snapshot,feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
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
