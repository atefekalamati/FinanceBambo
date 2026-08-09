from datetime import date

from ..domain.reports import calculate_live_report
from ..domain.resources import FinanceRecordNotFound


class FinanceLiveReportService:
    def __init__(self,repository,progress_provider):self.repo,self.provider=repository,progress_provider

    async def live(self,scope,reporting_date:date,progress_snapshot_id=None):
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
        return {"reporting_date":reporting_date,"progress_snapshot_id":snapshot["progress_snapshot_id"],"metrics":report.metrics,"breakdown":report.breakdown,"top_price_variances":report.price_variances,"top_quantity_variances":report.quantity_variances,"warnings":report.warnings}
