from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4

from ..domain.reports import calculate_live_report
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
        report=calculate_live_report(data["estimates"],data["invoices"],feed.get("assignments",[]),data["conversions"],data["gross_area"])
        return report,data,snapshot,feed

    async def live(self,scope,reporting_date:date,progress_snapshot_id=None):
        report,_data,snapshot,_feed=await self._calculate(scope,reporting_date,progress_snapshot_id)
        return {"reporting_date":reporting_date,"progress_snapshot_id":snapshot["progress_snapshot_id"],"metrics":report.metrics,"breakdown":report.breakdown,"top_price_variances":report.price_variances,"top_quantity_variances":report.quantity_variances,"warnings":report.warnings}

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
            "topPriceVariances":report.price_variances,"topQuantityVariances":report.quantity_variances,"warnings":report.warnings})
        await self.repo.issue(scope,value,payload,self.ids())
        return self._response(scope,value)

    async def get_snapshot(self,scope,report_id):
        value=await self.repo.get(scope,report_id)
        if value is None:raise FinanceRecordNotFound("report snapshot not found")
        return self._response(scope,value)

    @staticmethod
    def _response(scope,value):
        return {"report_snapshot_id":value["report_snapshot_id"],"organization_id":scope.organization_id,"project_id":scope.project_id,
            "issued_at":value["issued_at"],"issued_by":scope.actor_user_id if value.get("issued_by") is None else value["issued_by"],
            "progress_snapshot_id":value["progress_snapshot_id"],"resource_version_ids":value["resource_version_ids"],
            "price_version_ids":value["price_version_ids"],"invoice_ids":value["invoice_ids"],
            "unit_conversion_ids":value["unit_conversion_ids"],"calculated_metrics":value["calculated_metrics"],"immutable":True}
