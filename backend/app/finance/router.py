"""Finance API composition root.

Feature endpoints are intentionally added only in their approved delivery stage.
"""

from fastapi import APIRouter, Request, UploadFile, File, Form,Response,Query
from uuid import UUID

from .schemas.settings import (
    FinanceSettingsPatch,
    FinanceSettingsResponse,
    FinanceSummaryResponse,
)
from .security.guards import authorize_finance_request
from .services.settings import settings_edit_permission
from .schemas.resources import (EstimateLineCreate, EstimateLineResponse,
    EstimateRevisionCreate, ResourceCreate, ResourcePatch, ResourceResponse)
from .schemas.prices import CurrentPriceTrendResponse,PriceCreate, PriceResponse
from .schemas.conversions import ConversionCreate,ConversionPatch,ConversionResponse
from .schemas.progress import ProgressFeedResponse,ProgressOverrideCreate,ProgressOverrideResponse,ProgressSnapshotResponse
from .schemas.imports import ImportCommit,ImportCommitResponse,ImportPreviewResponse
from .schemas.invoices import CorrectiveInvoiceCreate,InvoiceCreate,InvoiceListResponse,InvoicePatch,InvoiceConfirm,InvoiceResponse,InvoiceVoid
from .schemas.attachments import AttachmentListResponse,AttachmentResponse
from .schemas.extractions import ExtractionConfirm,ExtractionDraftResponse,ExtractionListResponse,ExtractionReject,ExtractionRetry,ExtractionStart
from .schemas.reports import LiveReportResponse,ReportSnapshotCreate,ReportSnapshotReference
from .schemas.audit import AuditEventResponse
from datetime import date

router = APIRouter(prefix="/projects/{projectId}/finance", tags=["finance"])

_ERROR_EXAMPLE={"error":{"code":"VALIDATION_ERROR","message":"Request validation failed.","requestId":"req-example","details":[]}}
FINANCE_ERROR_RESPONSES={status:{"description":description,"content":{"application/json":{"example":_ERROR_EXAMPLE}}} for status,description in ((403,"Forbidden"),(404,"Scoped record not found"),(409,"Conflict or stale version"),(413,"File too large"),(415,"Unsupported media type"),(422,"Validation error"),(503,"Provider or storage unavailable"))}


def _host_ports(request: Request):
    return (
        request.app.state.auth_context_provider,
        request.app.state.scope_authorizer,
        request.app.state.permission_authorizer,
    )


@router.get("/settings", response_model=FinanceSettingsResponse)
async def get_finance_settings(projectId: str, request: Request):
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    scope = await authorize_finance_request(
        request,
        projectId,
        "finance.view",
        auth,
        scope_authorizer,
        permission_authorizer,
    )
    value = await request.app.state.finance_settings_service.get(scope)
    return FinanceSettingsResponse.from_domain(value)


@router.patch("/settings", response_model=FinanceSettingsResponse)
async def patch_finance_settings(
    projectId: str, payload: FinanceSettingsPatch, request: Request
):
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    scope = await authorize_finance_request(
        request,
        projectId,
        settings_edit_permission,
        auth,
        scope_authorizer,
        permission_authorizer,
    )
    value = await request.app.state.finance_settings_service.update(scope, payload)
    return FinanceSettingsResponse.from_domain(value)


@router.get("/summary", response_model=FinanceSummaryResponse)
async def get_finance_summary(projectId: str, request: Request):
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    scope = await authorize_finance_request(
        request,
        projectId,
        "finance.view",
        auth,
        scope_authorizer,
        permission_authorizer,
    )
    value = await request.app.state.finance_settings_service.summary(scope)
    return FinanceSummaryResponse.from_domain(value)


async def _resource_scope(project_id, request, permission):
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    return await authorize_finance_request(request, project_id, permission, auth, scope_authorizer, permission_authorizer)


@router.get("/resources", response_model=list[ResourceResponse])
async def list_resources(projectId: str, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return [ResourceResponse.from_domain(x) for x in await request.app.state.finance_resources_service.list_resources(scope)]

@router.post("/resources", response_model=ResourceResponse, status_code=201)
async def create_resource(projectId: str, payload: ResourceCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.create_resource(scope, payload))

@router.get("/resources/{resourceId}", response_model=ResourceResponse)
async def get_resource(projectId: str, resourceId: UUID, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.get_resource(scope, resourceId))

@router.patch("/resources/{resourceId}", response_model=ResourceResponse)
async def patch_resource(projectId: str, resourceId: UUID, payload: ResourcePatch, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.update_resource(scope, resourceId, payload))

@router.get("/estimate-lines", response_model=list[EstimateLineResponse])
async def list_estimate_lines(projectId: str, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return [EstimateLineResponse.from_domain(x) for x in await request.app.state.finance_resources_service.list_estimate_lines(scope)]

@router.post("/estimate-lines", response_model=EstimateLineResponse, status_code=201)
async def create_estimate_line(projectId: str, payload: EstimateLineCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return EstimateLineResponse.from_domain(await request.app.state.finance_resources_service.create_estimate_line(scope, payload))

@router.post("/estimate-lines/{lineId}/revisions", response_model=EstimateLineResponse, status_code=201)
async def revise_estimate_line(projectId: str, lineId: UUID, payload: EstimateRevisionCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return EstimateLineResponse.from_domain(await request.app.state.finance_resources_service.revise_estimate_line(scope, lineId, payload))

@router.get("/resources/{resourceId}/prices", response_model=list[PriceResponse])
async def resource_prices(projectId:str,resourceId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return [PriceResponse.from_domain(x) for x in await request.app.state.finance_price_service.history(scope,resourceId)]

@router.post("/resources/{resourceId}/prices", response_model=PriceResponse,status_code=201)
async def create_price(projectId:str,resourceId:UUID,payload:PriceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return PriceResponse.from_domain(await request.app.state.finance_price_service.create(scope,resourceId,payload))

@router.get("/price-history", response_model=list[PriceResponse])
async def price_history(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return [PriceResponse.from_domain(x) for x in await request.app.state.finance_price_service.history(scope)]

@router.get("/prices/current",response_model=list[CurrentPriceTrendResponse])
async def current_price_trends(projectId:str,asOf:date,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.finance_price_service.trends(scope,asOf)

@router.get("/unit-conversions",response_model=list[ConversionResponse])
async def unit_conversions(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return [ConversionResponse.from_domain(x) for x in await request.app.state.unit_conversion_service.list(scope)]

@router.post("/unit-conversions",response_model=ConversionResponse,status_code=201)
async def create_unit_conversion(projectId:str,payload:ConversionCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ConversionResponse.from_domain(await request.app.state.unit_conversion_service.create(scope,payload))

@router.patch("/unit-conversions/{conversionId}",response_model=ConversionResponse)
async def revise_unit_conversion(projectId:str,conversionId:UUID,payload:ConversionPatch,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ConversionResponse.from_domain(await request.app.state.unit_conversion_service.revise(scope,conversionId,payload))

@router.get("/progress-snapshots",response_model=list[ProgressSnapshotResponse])
async def progress_snapshots(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.progress_service.list_snapshots(scope)

@router.get("/progress-snapshots/{snapshotId}/feed",response_model=ProgressFeedResponse)
async def progress_feed(projectId:str,snapshotId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.progress_service.feed(scope,snapshotId)

@router.post("/estimate-lines/{lineId}/progress-override",response_model=ProgressOverrideResponse,status_code=201)
async def progress_override(projectId:str,lineId:UUID,payload:ProgressOverrideCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ProgressOverrideResponse.from_domain(await request.app.state.progress_service.override(scope,lineId,payload))

async def _preview_import(projectId,request,kind,file,currency_unit=None):
    scope=await _resource_scope(projectId,request,"finance.edit")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        from .services.imports import ImportValidationError
        raise ImportValidationError("only .xlsx Excel files are accepted")
    return await request.app.state.finance_import_service.preview(scope,kind,await file.read(),currency_unit)
@router.post("/imports/estimate/preview",response_model=ImportPreviewResponse)
async def preview_estimate(projectId:str,request:Request,file:UploadFile=File(...)):return await _preview_import(projectId,request,"estimate",file)
@router.post("/imports/prices/preview",response_model=ImportPreviewResponse)
async def preview_prices(projectId:str,request:Request,file:UploadFile=File(...),currencyUnit:str=Form(...)):return await _preview_import(projectId,request,"prices",file,currencyUnit)
async def _commit_import(projectId,request,payload):
    scope=await _resource_scope(projectId,request,"finance.edit");return await request.app.state.finance_import_service.commit(scope,payload.preview_id)
@router.post("/imports/estimate/commit",response_model=ImportCommitResponse)
async def commit_estimate(projectId:str,payload:ImportCommit,request:Request):return await _commit_import(projectId,request,payload)
@router.post("/imports/prices/commit",response_model=ImportCommitResponse)
async def commit_prices(projectId:str,payload:ImportCommit,request:Request):return await _commit_import(projectId,request,payload)

@router.get("/invoices",response_model=InvoiceListResponse,responses=FINANCE_ERROR_RESPONSES)
async def invoices(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),query:str|None=Query(None,min_length=1,max_length=200),status:str|None=Query(None,pattern="^(draft|awaitingConfirmation|confirmed|voided|corrected)$"),source:str|None=Query(None,pattern="^(manual|image|voice|reversal|corrective)$")):
    scope=await _resource_scope(projectId,request,"finance.view");items,total=await request.app.state.invoice_service.list(scope,page,pageSize,query,status,source)
    return InvoiceListResponse(items=[InvoiceResponse.from_domain(x) for x in items],page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)
@router.post("/invoices",response_model=InvoiceResponse,status_code=201)
async def create_invoice(projectId:str,payload:InvoiceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit");return InvoiceResponse.from_domain(await request.app.state.invoice_service.create(scope,payload))
@router.get("/invoices/{invoiceId}",response_model=InvoiceResponse)
async def invoice(projectId:str,invoiceId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view");return InvoiceResponse.from_domain(await request.app.state.invoice_service.get(scope,invoiceId))
@router.patch("/invoices/{invoiceId}",response_model=InvoiceResponse)
async def patch_invoice(projectId:str,invoiceId:UUID,payload:InvoicePatch,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit");return InvoiceResponse.from_domain(await request.app.state.invoice_service.update(scope,invoiceId,payload))
@router.post("/invoices/{invoiceId}/confirm",response_model=InvoiceResponse)
async def confirm_invoice(projectId:str,invoiceId:UUID,payload:InvoiceConfirm,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit");return InvoiceResponse.from_domain(await request.app.state.invoice_service.confirm(scope,invoiceId,payload))
@router.post("/invoices/{invoiceId}/void",response_model=InvoiceResponse,status_code=201)
async def void_invoice(projectId:str,invoiceId:UUID,payload:InvoiceVoid,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit");return InvoiceResponse.from_domain(await request.app.state.invoice_service.void(scope,invoiceId,payload))
@router.post("/invoices/{invoiceId}/corrective",response_model=InvoiceResponse,status_code=201)
async def corrective_invoice(projectId:str,invoiceId:UUID,payload:CorrectiveInvoiceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit");return InvoiceResponse.from_domain(await request.app.state.invoice_service.corrective(scope,invoiceId,payload))

@router.post("/files",response_model=AttachmentResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def upload_finance_file(projectId:str,request:Request,logicalType:str=Form(...),file:UploadFile=File(...)):
    scope=await _resource_scope(projectId,request,"finance.edit")
    value=await request.app.state.finance_attachment_service.upload(scope,logicalType,file.filename or "upload.bin",file.content_type or "application/octet-stream",await file.read())
    return AttachmentResponse.from_domain(value)

@router.get("/files",response_model=AttachmentListResponse,responses=FINANCE_ERROR_RESPONSES)
async def list_finance_files(
    projectId:str, request:Request,
    page:int=Query(1,ge=1), pageSize:int=Query(50,ge=1,le=200),
    logicalType:str|None=Query(None,pattern="^(invoice_image|invoice_voice)$"),
    fileCategory:str|None=Query(None,pattern="^(image|audio)$"),
    processingStatus:str|None=Query(None,pattern="^(uploaded|processing|ready|failed)$"),
    uploaderId:UUID|None=None,
):
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total_count=await request.app.state.finance_attachment_service.list(
        scope,page,pageSize,logicalType,fileCategory,processingStatus,uploaderId)
    return AttachmentListResponse(
        items=[AttachmentResponse.from_domain(item) for item in items],
        page=page,page_size=pageSize,total_count=total_count,
        total_pages=(total_count+pageSize-1)//pageSize,
    )

@router.get("/files/{fileId}",response_model=AttachmentResponse,responses=FINANCE_ERROR_RESPONSES)
async def get_finance_file(projectId:str,fileId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return AttachmentResponse.from_domain(await request.app.state.finance_attachment_service.get(scope,fileId))

@router.get("/files/{fileId}/content",responses=FINANCE_ERROR_RESPONSES)
async def get_finance_file_content(projectId:str,fileId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    metadata,content=await request.app.state.finance_attachment_service.content(scope,fileId)
    return Response(content=content,media_type=metadata.mime_type,headers={"Content-Disposition":f'inline; filename="{metadata.original_name_safe}"',"X-Content-Type-Options":"nosniff"})

@router.post("/files/{fileId}/extractions",response_model=ExtractionDraftResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def start_extraction(projectId:str,fileId:UUID,payload:ExtractionStart,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.start(scope,fileId,payload.hints))

@router.get("/extractions",response_model=ExtractionListResponse,responses=FINANCE_ERROR_RESPONSES)
async def list_extractions(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),reviewStatus:str|None=Query(None,pattern="^(awaitingReview|accepted|rejected)$"),source:str|None=Query(None,pattern="^(image|voice)$"),fileId:UUID|None=None,linkedInvoiceId:UUID|None=None):
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.finance_extraction_service.list(scope,page,pageSize,reviewStatus,source,fileId,linkedInvoiceId)
    return ExtractionListResponse(items=[ExtractionDraftResponse.from_domain(item) for item in items],page=page,page_size=pageSize,total_count=total,total_pages=(total+pageSize-1)//pageSize)

@router.get("/extractions/{draftId}",response_model=ExtractionDraftResponse,responses=FINANCE_ERROR_RESPONSES)
async def get_extraction(projectId:str,draftId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.get(scope,draftId))

@router.post("/extractions/{draftId}/reject",response_model=ExtractionDraftResponse,responses=FINANCE_ERROR_RESPONSES)
async def reject_extraction(projectId:str,draftId:UUID,payload:ExtractionReject,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.reject(scope,draftId,payload))

@router.post("/extractions/{draftId}/retry",response_model=ExtractionDraftResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def retry_extraction(projectId:str,draftId:UUID,payload:ExtractionRetry,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.retry(scope,draftId,payload.hints))

@router.post("/extractions/{draftId}/confirm",response_model=InvoiceResponse,responses=FINANCE_ERROR_RESPONSES)
async def confirm_extraction(projectId:str,draftId:UUID,payload:ExtractionConfirm,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return InvoiceResponse.from_domain(await request.app.state.finance_extraction_service.confirm(scope,draftId,payload))

@router.get("/reports/live",response_model=LiveReportResponse)
async def live_report(projectId:str,request:Request,reportingDate:date,progressSnapshotId:UUID|None=None):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.finance_live_report_service.live(scope,reportingDate,progressSnapshotId)

@router.post("/report-snapshots",response_model=ReportSnapshotReference,status_code=201)
async def issue_report_snapshot(projectId:str,payload:ReportSnapshotCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.issue")
    return await request.app.state.finance_live_report_service.issue(scope,payload.reporting_date,payload.progress_snapshot_id)

@router.get("/report-snapshots/{reportId}",response_model=ReportSnapshotReference)
async def report_snapshot(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.get_snapshot(scope,reportId)

@router.get("/report-snapshots/{reportId}/csv")
async def report_snapshot_csv(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.export")
    content=await request.app.state.finance_live_report_service.export(scope,reportId,"csv")
    return Response(content,media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="finance-report-{reportId}.csv"'})

@router.get("/report-snapshots/{reportId}/xlsx")
async def report_snapshot_xlsx(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.export")
    content=await request.app.state.finance_live_report_service.export(scope,reportId,"xlsx")
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="finance-report-{reportId}.xlsx"'})

@router.get("/audit-events",response_model=list[AuditEventResponse])
async def audit_events(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.finance_audit_service.list(scope)
