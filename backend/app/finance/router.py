"""Finance API composition root.

Feature endpoints are intentionally added only in their approved delivery stage.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, File, Form,Response,Query
from uuid import UUID

from .schemas.settings import (
    FinanceSettingsPatch,
    FinanceSettingsResponse,
    FinanceSettingsRevisionResponse,
    FinanceSummaryResponse,
)
from .security.guards import FinanceNotFound, authorize_finance_request
from .adapters.ports import supports_actor_names
from .domain.actors import apply_actor_names, collect_actor_ids
from .services.settings import SETTINGS_EDIT_PERMISSION, may_edit_settings
from .schemas.resources import (EstimateLineCreate, EstimateLineResponse,
    EstimateRevisionCreate, ResourceCreate, ResourcePatch, ResourceResponse)
from .schemas.activities import ActivityCreate, ActivityListResponse, ActivityResponse
from .schemas.unit_registry import UnitDefinitionResponse, UnitRegistryResponse
from .domain.unit_registry import UNIT_REGISTRY
from .domain.unit_conversion import can_convert, quantity_factor
from .schemas.prices import CurrentPriceTrendResponse,PriceCreate, PriceHistoryListResponse, PriceResponse
from .schemas.conversions import ConversionCreate,ConversionListResponse,ConversionPatch,ConversionResponse
from .schemas.progress import ProgressFeedResponse,ProgressOverrideCreate,ProgressOverrideResponse,ProgressSnapshotResponse
from .schemas.imports import ImportCommit,ImportCommitResponse,ImportFromLink,ImportPreviewResponse
from .services.google_sheet import fetch_sheet_as_xlsx
from .schemas.invoices import CorrectiveInvoiceCreate,InvoiceCreate,InvoiceListResponse,InvoicePatch,InvoiceConfirm,InvoiceResponse,InvoiceVoid
from .schemas.attachments import AttachmentListResponse,AttachmentResponse
from .schemas.extractions import ExtractionConfirm,ExtractionDraftResponse,ExtractionListResponse,ExtractionReject,ExtractionRetry,ExtractionStart
from .domain.monthly import DEFAULT_MONTH_COUNT,MAX_MONTH_COUNT
from .schemas.reports import LiveReportResponse,MonthlyReportResponse,OperationalOverviewResponse,ReportSnapshotCreate,ReportSnapshotListResponse,ReportSnapshotReference,ReportVarianceListResponse,WbsReportResponse
from .schemas.audit import AuditEventListResponse,AuditEventResponse
from .schemas.material_prices import (ImportRunListResponse,ImportRunResponse,
    MaterialCategoryListResponse,MaterialCategoryResponse,MaterialPriceHistoryListResponse,
    MaterialPriceHistoryResponse,MaterialPriceListResponse,MaterialPriceResponse,
    MaterialUnitSettingCreate,MaterialUnitSettingListResponse,MaterialUnitSettingResponse,
    ProviderItemFactorCreate,ProviderItemFactorListResponse,ProviderItemFactorResponse,
    ProviderItemLabelCreate,ProviderItemLabelListResponse,ProviderItemLabelResponse,
    UnresolvedItemListResponse,UnresolvedItemResponse)
from .schemas.item_price_mappings import (CandidateListResponse,CandidateProductResponse,
    ConvertedPricePreviewResponse,ItemPriceMappingCreate,ItemPriceMappingResponse,
    MappingFiltersResponse)
from .schemas.item_price_components import (ItemPriceRowStatusListResponse,ItemPriceRowStatusResponse,PriceComponentCreate,
    PriceComponentDeactivate,PriceComponentListResponse,PriceComponentPreviewResponse,
    PriceComponentResponse,PriceComponentRow,PricedLineHeaderResponse)
from .domain.material_categories import category_columns,category_label,spec_columns,specs_of
from .services.material_price_resolution import canonical_unit
from datetime import date
from decimal import Decimal

router = APIRouter(prefix="/projects/{projectId}/finance", tags=["finance"])

_ERROR_EXAMPLE={"error":{"code":"VALIDATION_ERROR","message":"Request validation failed.","requestId":"req-example","details":[]}}
FINANCE_ERROR_RESPONSES={status:{"description":description,"content":{"application/json":{"example":_ERROR_EXAMPLE}}} for status,description in ((403,"Forbidden"),(404,"Scoped record not found"),(409,"Conflict or stale version"),(413,"File too large"),(415,"Unsupported media type"),(422,"Validation error"),(503,"Provider or storage unavailable"))}
ATTACHMENT_CONTENT_RESPONSES={**FINANCE_ERROR_RESPONSES,200:{"description":"Immutable attachment bytes","content":{media:{"schema":{"type":"string","format":"binary"}} for media in ("image/png","image/jpeg","image/webp","audio/mpeg","audio/mp4","audio/wav","audio/ogg")}}}
CSV_DOWNLOAD_RESPONSES={200:{"description":"UTF-8 CSV with BOM","content":{"text/csv":{"schema":{"type":"string","format":"binary"}}}},**FINANCE_ERROR_RESPONSES}
XLSX_DOWNLOAD_RESPONSES={200:{"description":"Excel workbook","content":{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":{"schema":{"type":"string","format":"binary"}}}},**FINANCE_ERROR_RESPONSES}


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
    return FinanceSettingsResponse.from_domain(value, may_edit_settings(scope))


@router.patch("/settings", response_model=FinanceSettingsResponse)
async def patch_finance_settings(
    projectId: str, payload: FinanceSettingsPatch, request: Request
):
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    scope = await authorize_finance_request(
        request,
        projectId,
        SETTINGS_EDIT_PERMISSION,
        auth,
        scope_authorizer,
        permission_authorizer,
    )
    value = await request.app.state.finance_settings_service.update(scope, payload)
    return FinanceSettingsResponse.from_domain(value, may_edit_settings(scope))


@router.get("/settings/revisions", response_model=list[FinanceSettingsRevisionResponse])
async def get_finance_settings_revisions(projectId: str, request: Request):
    """Expose the append-only settings trail; the table is immutable, so the list stays short."""
    auth, scope_authorizer, permission_authorizer = _host_ports(request)
    scope = await authorize_finance_request(
        request,
        projectId,
        "finance.view",
        auth,
        scope_authorizer,
        permission_authorizer,
    )
    return await _named(request, await request.app.state.finance_settings_service.revisions(scope))


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


async def _named(request, payload):
    """Put the host's name beside every actor id in this response, then return it.

    One call per response, never one per row: the ids are collected first and looked up
    together, so a page of fifty invoices written by three people costs three names and one
    query rather than fifty. See `domain.actors` for what is traversed and what is not.

    Every failure mode ends as "no names": a host with no directory, a directory that does
    not know an id, a lookup that raises. The payload is returned either way, carrying the
    ids it always carried -- a decoration is never worth failing a report for.
    """
    directory = getattr(request.app.state, "actor_directory", None)
    if not supports_actor_names(directory):
        return payload
    ids = collect_actor_ids(payload)
    if not ids:
        return payload
    try:
        names = await directory.names(ids)
    except Exception:  # noqa: BLE001 -- see the docstring
        return payload
    return apply_actor_names(payload, names or {})


async def _conceal_unless_permitted(project_id, request, permission):
    """The same four gates, but a refusal is reported as "not found".

    For a route whose entire subject is content somebody must not see, every "no" has to
    look the same. `authorize_finance_request` answers 403, which is the right answer
    almost everywhere -- it tells an authenticated colleague they need a permission rather
    than pretending the feature is missing. On the original-file route it is the wrong one,
    because a 403 on a guessed id confirms the id.

    So a 403 from ANY of the gates becomes the 404 a missing record produces, and the
    caller cannot tell "no permission" from "wrong project" from "no such file".
    Authentication is untouched: a 401 stays a 401, because being logged out is not a fact
    about the file.
    """
    try:
        return await _resource_scope(project_id, request, permission)
    except HTTPException as refusal:
        if refusal.status_code == 403:
            raise FinanceNotFound() from None
        raise


@router.get("/resources", response_model=list[ResourceResponse])
async def list_resources(projectId: str, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return [ResourceResponse.from_domain(x) for x in await request.app.state.finance_resources_service.list_resources(scope)]

@router.post("/resources", response_model=ResourceResponse, status_code=201)
async def create_resource(projectId: str, payload: ResourceCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.create_resource(scope, payload))

@router.get("/task-resource-mappings")
async def task_resource_mappings(projectId: str, request: Request, page: int = 1, pageSize: int = 100):
    """MPP task <-> finance resource links, read-only, scoped through finance_resources.

    task_id is msp_tasks.id -- the database identity of one task row in one snapshot, not
    the Task ID printed inside the file. Task details come from the progress feed; this
    lists the linkage Finance owns.
    """
    scope = await _resource_scope(projectId, request, "finance.view")
    # Clamped, not validated-and-500'd: page=-1 or pageSize=0 would otherwise reach
    # PostgreSQL as a negative LIMIT/OFFSET and blow up mid-query.
    page = max(1, page)
    page_size = min(max(1, pageSize), 500)
    rows, total = await request.app.state.finance_resources_service.list_task_resource_mappings(
        scope, page, page_size)
    return {"items": [{"id": str(row["id"]), "taskId": row["task_id"],
                       "resourceId": str(row["resource_id"]),
                       "resourceCode": row["resource_code"],
                       "resourceTitle": row["resource_title"],
                       "externalResourceId": row["external_resource_id"]}
                      for row in rows],
            "page": page, "pageSize": page_size, "totalItems": total}

@router.get("/resources/{resourceId}", response_model=ResourceResponse)
async def get_resource(projectId: str, resourceId: UUID, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.get_resource(scope, resourceId))

@router.patch("/resources/{resourceId}", response_model=ResourceResponse)
async def patch_resource(projectId: str, resourceId: UUID, payload: ResourcePatch, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return ResourceResponse.from_domain(await request.app.state.finance_resources_service.update_resource(scope, resourceId, payload))

@router.get("/unit-registry", response_model=UnitRegistryResponse)
async def unit_registry(projectId: str, request: Request):
    await _resource_scope(projectId, request, "finance.view")
    return UnitRegistryResponse(items=[UnitDefinitionResponse(**unit.__dict__) for unit in UNIT_REGISTRY.values()])

@router.get("/activities", response_model=ActivityListResponse)
async def list_project_activities(projectId: str, request: Request,
    query: str | None = Query(None, min_length=1, max_length=200),
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200)):
    scope = await _resource_scope(projectId, request, "finance.view")
    items,total = await request.app.state.finance_resources_service.list_activities(scope, query, status, page, pageSize)
    return ActivityListResponse(
        items=[ActivityResponse.model_validate(item) for item in items],
        page=page, page_size=pageSize, total_items=total,
        total_pages=(total + pageSize - 1) // pageSize,
    )

@router.post("/activities", response_model=ActivityResponse, status_code=201, responses=FINANCE_ERROR_RESPONSES)
async def create_project_activity(projectId: str, payload: ActivityCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return ActivityResponse.model_validate(await request.app.state.finance_resources_service.create_activity(scope, payload))

@router.get("/estimate-lines", response_model=list[EstimateLineResponse])
async def list_estimate_lines(projectId: str, request: Request):
    scope = await _resource_scope(projectId, request, "finance.view")
    return await _named(request, [EstimateLineResponse.from_domain(x) for x in await request.app.state.finance_resources_service.list_estimate_lines(scope)])

@router.post("/estimate-lines", response_model=EstimateLineResponse, status_code=201)
async def create_estimate_line(projectId: str, payload: EstimateLineCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return await _named(request, EstimateLineResponse.from_domain(await request.app.state.finance_resources_service.create_estimate_line(scope, payload)))

@router.post("/estimate-lines/{lineId}/revisions", response_model=EstimateLineResponse, status_code=201)
async def revise_estimate_line(projectId: str, lineId: UUID, payload: EstimateRevisionCreate, request: Request):
    scope = await _resource_scope(projectId, request, "finance.edit")
    return await _named(request, EstimateLineResponse.from_domain(await request.app.state.finance_resources_service.revise_estimate_line(scope, lineId, payload)))

@router.get("/resources/{resourceId}/prices", response_model=list[PriceResponse])
async def resource_prices(projectId:str,resourceId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, [PriceResponse.from_domain(x) for x in await request.app.state.finance_price_service.history(scope,resourceId)])

@router.post("/resources/{resourceId}/prices", response_model=PriceResponse,status_code=201)
async def create_price(projectId:str,resourceId:UUID,payload:PriceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return await _named(request, PriceResponse.from_domain(await request.app.state.finance_price_service.create(scope,resourceId,payload)))

@router.get("/price-history", response_model=PriceHistoryListResponse)
async def price_history(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),
    resourceId:UUID|None=Query(None),dateFrom:date|None=Query(None,alias="from"),dateTo:date|None=Query(None,alias="to")):
    """A page of the price history, newest effective date first.

    Every parameter is optional and the defaults are the same fifty `/invoices` uses, so a
    client that sends none still gets a valid answer -- but it gets a page, and `totalItems`
    is how it learns there is more. `from` and `to` bound the effective date inclusively.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.finance_price_service.history_page(scope,page,pageSize,resourceId,dateFrom,dateTo)
    return await _named(request, PriceHistoryListResponse(items=[PriceResponse.from_domain(x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize))

@router.get("/prices/current",response_model=list[CurrentPriceTrendResponse])
async def current_price_trends(projectId:str,asOf:date,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.finance_price_service.trends(scope,asOf)

@router.get("/unit-conversions",response_model=ConversionListResponse)
async def unit_conversions(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """A page of the unit conversions, oldest first.

    Same envelope and same defaults as the price history above; the ordering differs
    because a conversion list is read forwards and a price history backwards.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.unit_conversion_service.page(scope,page,pageSize)
    return await _named(request, ConversionListResponse(items=[ConversionResponse.from_domain(x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize))

@router.post("/unit-conversions",response_model=ConversionResponse,status_code=201)
async def create_unit_conversion(projectId:str,payload:ConversionCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return await _named(request, ConversionResponse.from_domain(await request.app.state.unit_conversion_service.create(scope,payload)))

@router.patch("/unit-conversions/{conversionId}",response_model=ConversionResponse)
async def revise_unit_conversion(projectId:str,conversionId:UUID,payload:ConversionPatch,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return await _named(request, ConversionResponse.from_domain(await request.app.state.unit_conversion_service.revise(scope,conversionId,payload)))

@router.get("/progress-snapshots",response_model=list[ProgressSnapshotResponse])
async def progress_snapshots(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, await request.app.state.progress_service.list_snapshots(scope))

@router.get("/progress-snapshots/{snapshotId}",response_model=ProgressSnapshotResponse)
async def progress_snapshot(projectId:str,snapshotId:UUID,request:Request):
    """One snapshot's metadata, including its version, without pulling the whole feed."""
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, await request.app.state.progress_service.snapshot(scope,snapshotId))

@router.get("/progress-snapshots/{snapshotId}/feed",response_model=ProgressFeedResponse)
async def progress_feed(projectId:str,snapshotId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, await request.app.state.progress_service.feed(scope,snapshotId))

@router.get("/estimate-lines/{lineId}/progress-overrides",response_model=list[ProgressOverrideResponse])
async def progress_override_history(projectId:str,lineId:UUID,request:Request):
    """Expose the append-only override trail so the UI can show what was replaced and why."""
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, [ProgressOverrideResponse.from_row(row) for row in await request.app.state.progress_service.override_history(scope,lineId)])

@router.post("/estimate-lines/{lineId}/progress-override",response_model=ProgressOverrideResponse,status_code=201)
async def progress_override(projectId:str,lineId:UUID,payload:ProgressOverrideCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.edit")
    return await _named(request, ProgressOverrideResponse.from_domain(await request.app.state.progress_service.override(scope,lineId,payload)))

async def _preview_import(projectId,request,kind,file):
    scope=await _resource_scope(projectId,request,"finance.edit")
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        from .services.imports import ImportValidationError
        raise ImportValidationError("only .xlsx Excel files are accepted")
    return await request.app.state.finance_import_service.preview(scope,kind,await file.read())
@router.post("/imports/estimate/preview",response_model=ImportPreviewResponse,responses=FINANCE_ERROR_RESPONSES)
async def preview_estimate(projectId:str,request:Request,file:UploadFile=File(...)):return await _preview_import(projectId,request,"estimate",file)
@router.post("/imports/prices/preview",response_model=ImportPreviewResponse,responses=FINANCE_ERROR_RESPONSES)
async def preview_prices(projectId:str,request:Request,file:UploadFile=File(...)):return await _preview_import(projectId,request,"prices",file)

async def _preview_import_from_link(projectId,request,kind,payload):
    """The same preview, for a workbook the server fetches instead of the browser.

    The client sends a link and never touches Google: its own API client refuses any
    address outside the page's origin, and the host's CSP names `connect-src 'self'`.
    What comes back is bytes, judged by the same parser an upload reaches -- so there is
    one import contract, not two, and `commit` is unchanged because it works from the
    stored preview rather than from the file.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    content=await fetch_sheet_as_xlsx(payload.source_url)
    return await request.app.state.finance_import_service.preview(scope,kind,content)
@router.post("/imports/estimate/preview-link",response_model=ImportPreviewResponse,responses=FINANCE_ERROR_RESPONSES)
async def preview_estimate_link(projectId:str,payload:ImportFromLink,request:Request):return await _preview_import_from_link(projectId,request,"estimate",payload)
@router.post("/imports/prices/preview-link",response_model=ImportPreviewResponse,responses=FINANCE_ERROR_RESPONSES)
async def preview_prices_link(projectId:str,payload:ImportFromLink,request:Request):return await _preview_import_from_link(projectId,request,"prices",payload)
async def _commit_import(projectId,request,payload):
    scope=await _resource_scope(projectId,request,"finance.edit");return await request.app.state.finance_import_service.commit(scope,payload.preview_id)
@router.post("/imports/estimate/commit",response_model=ImportCommitResponse,responses=FINANCE_ERROR_RESPONSES)
async def commit_estimate(projectId:str,payload:ImportCommit,request:Request):return await _commit_import(projectId,request,payload)
@router.post("/imports/prices/commit",response_model=ImportCommitResponse,responses=FINANCE_ERROR_RESPONSES)
async def commit_prices(projectId:str,payload:ImportCommit,request:Request):return await _commit_import(projectId,request,payload)

@router.get("/invoices",response_model=InvoiceListResponse,responses=FINANCE_ERROR_RESPONSES)
async def invoices(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),query:str|None=Query(None,min_length=1,max_length=200),status:str|None=Query(None,pattern="^(draft|awaitingConfirmation|confirmed|voided|corrected)$"),source:str|None=Query(None,pattern="^(manual|image|voice|reversal|corrective)$"),
    invoiceDateFrom:date|None=None,invoiceDateTo:date|None=None):
    scope=await _resource_scope(projectId,request,"finance.view");items,total=await request.app.state.invoice_service.list(scope,page,pageSize,query,status,source,invoiceDateFrom,invoiceDateTo)
    return await _named(request, InvoiceListResponse(items=[InvoiceResponse.from_domain(x) for x in items],page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize))
@router.post("/invoices",response_model=InvoiceResponse,status_code=201)
async def create_invoice(projectId:str,payload:InvoiceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.create(scope,payload)))
@router.get("/invoices/{invoiceId}",response_model=InvoiceResponse)
async def invoice(projectId:str,invoiceId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.get(scope,invoiceId)))
@router.patch("/invoices/{invoiceId}",response_model=InvoiceResponse)
async def patch_invoice(projectId:str,invoiceId:UUID,payload:InvoicePatch,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.update(scope,invoiceId,payload)))
@router.post("/invoices/{invoiceId}/confirm",response_model=InvoiceResponse)
async def confirm_invoice(projectId:str,invoiceId:UUID,payload:InvoiceConfirm,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.confirm(scope,invoiceId,payload)))
@router.post("/invoices/{invoiceId}/void",response_model=InvoiceResponse,status_code=201)
async def void_invoice(projectId:str,invoiceId:UUID,payload:InvoiceVoid,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.void(scope,invoiceId,payload)))
@router.post("/invoices/{invoiceId}/corrective",response_model=InvoiceResponse,status_code=201)
async def corrective_invoice(projectId:str,invoiceId:UUID,payload:CorrectiveInvoiceCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice");return await _named(request, InvoiceResponse.from_domain(await request.app.state.invoice_service.corrective(scope,invoiceId,payload)))

@router.post("/files",response_model=AttachmentResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def upload_finance_file(projectId:str,request:Request,logicalType:str=Form(...),file:UploadFile=File(...)):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
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

@router.get("/files/{fileId}/content",response_class=Response,responses=ATTACHMENT_CONTENT_RESPONSES)
async def get_finance_file_content(projectId:str,fileId:UUID,request:Request):
    """The uploaded invoice image or recording itself, for invoice managers only.

    The metadata beside it stays on `finance.view` -- a viewer may see that a file exists,
    what it is called, and whether it has been read. The BYTES are different: an invoice
    photograph carries a supplier's name, their prices and often a signature, and that is
    the one thing here that cannot be redacted after somebody has seen it.

    404 rather than 403, and the concealment is the point rather than a side effect. "You
    may not read this file" tells the caller the file is there; on an id they guessed, the
    difference between 403 and 404 is exactly the fact they were probing for. A caller
    without the permission therefore gets the same answer as one asking for a file that
    never existed, and nothing is streamed before the gate is passed.
    """
    scope=await _conceal_unless_permitted(projectId,request,"finance.manage_invoice")
    metadata,content=await request.app.state.finance_attachment_service.content(scope,fileId)
    return Response(content=content,media_type=metadata.mime_type,headers={"Content-Disposition":f'inline; filename="{metadata.original_name_safe}"',"X-Content-Type-Options":"nosniff","Cache-Control":"private, no-store"})

@router.post("/files/{fileId}/extractions",response_model=ExtractionDraftResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def start_extraction(projectId:str,fileId:UUID,payload:ExtractionStart,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.start(scope,fileId,payload.hints))

@router.post("/files/{fileId}/extractions/async",status_code=202,responses=FINANCE_ERROR_RESPONSES)
async def start_extraction_async(projectId:str,fileId:UUID,payload:ExtractionStart,request:Request,
    background:BackgroundTasks):
    """Queue an extraction and answer immediately.

    A local OCR or transcription takes seconds to minutes; the synchronous route holds the
    request open for all of it. Poll `GET /extractions?fileId=` -- the attachment status
    returned here moves uploaded -> processing -> ready | failed on its own.
    """
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    executor=getattr(request.app.state,"finance_background_executor",None)
    if executor is not None:
        enqueue=executor.submit
    elif getattr(request.app.state,"allow_ephemeral_finance_tasks",False):
        # Development only. A production host must provide a durable executor; accepting
        # work into a web-worker callback would lose it on restart after returning 202.
        enqueue=lambda run:background.add_task(run)
    else:
        raise HTTPException(503,"durable extraction execution is not configured")
    attachment,existing=await request.app.state.finance_extraction_service.schedule(
        scope,fileId,enqueue,payload.hints)
    return {"fileId":str(fileId),"processingStatus":attachment.processing_status,
            "extractionId":None if existing is None else str(existing.id),
            "alreadyExtracted":existing is not None}

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
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.reject(scope,draftId,payload))

@router.post("/extractions/{draftId}/retry",response_model=ExtractionDraftResponse,status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def retry_extraction(projectId:str,draftId:UUID,payload:ExtractionRetry,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.retry(scope,draftId,payload.hints))

@router.post("/extractions/{draftId}/confirm",response_model=InvoiceResponse,responses=FINANCE_ERROR_RESPONSES)
async def confirm_extraction(projectId:str,draftId:UUID,payload:ExtractionConfirm,request:Request):
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    return InvoiceResponse.from_domain(await request.app.state.finance_extraction_service.confirm(scope,draftId,payload))

@router.get("/reports/live",response_model=LiveReportResponse)
async def live_report(projectId:str,request:Request,reportingDate:date,progressSnapshotId:UUID|None=None):
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.live(scope,reportingDate,progressSnapshotId)

@router.get("/overview",response_model=OperationalOverviewResponse,summary="Operational Finance Overview")
async def finance_overview(projectId:str,request:Request,reportingDate:date,progressSnapshotId:UUID|None=None):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await request.app.state.finance_live_report_service.overview(scope,reportingDate,progressSnapshotId)

@router.get("/reports/live/by-wbs",response_model=WbsReportResponse,responses=FINANCE_ERROR_RESPONSES)
async def live_report_by_wbs(projectId:str,request:Request,reportingDate:date,progressSnapshotId:UUID|None=None,
    level:int|None=Query(None,ge=1,le=10),parentWbsCode:str|None=Query(None,min_length=1,max_length=120,pattern=r"^[0-9A-Za-z._-]+$")):
    """WBS stages with their rolled-up cost. `parentWbsCode` returns that node's direct children."""
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.by_wbs(scope,reportingDate,progressSnapshotId,level,parentWbsCode)

@router.get("/reports/live/variances",response_model=ReportVarianceListResponse)
async def live_report_variances(projectId:str,request:Request,reportingDate:date,progressSnapshotId:UUID|None=None,
    varianceType:str=Query("all",pattern="^(price|quantity|all)$"),resourceType:str|None=Query(None,pattern="^(material|labor|equipment|general_cost)$"),
    query:str|None=Query(None,min_length=1,max_length=200),page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),
    sortBy:str|None=Query(None,pattern="^(varianceIrr|varianceQuantity|remainingPhysicalCostIrr|forecastFinalIrr|impactSharePercent|actualCostIrr)$"),
    sortDirection:str=Query("desc",pattern="^(asc|desc)$")):
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.variances(scope,reportingDate,progressSnapshotId,varianceType,resourceType,query,page,pageSize,sortBy,sortDirection)

@router.get("/reports/monthly",response_model=MonthlyReportResponse)
async def monthly_report(projectId:str,request:Request,reportingDate:date|None=None,
    progressSnapshotId:UUID|None=None,
    monthCount:int=Query(DEFAULT_MONTH_COUNT,ge=1,le=MAX_MONTH_COUNT)):
    """Persian-month cost series for the trend chart, aggregated server-side.

    The window is an anchor plus a month count rather than a from/to pair: Persian months
    do not line up with Gregorian dates, so an arbitrary range would open and close on
    half a month and the chart would draw those stubs as real dips.
    """
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.monthly(
        scope,reportingDate,monthCount,progressSnapshotId)

@router.post("/report-snapshots",response_model=ReportSnapshotReference,status_code=201)
async def issue_report_snapshot(projectId:str,payload:ReportSnapshotCreate,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.issue")
    return await request.app.state.finance_live_report_service.issue(scope,payload.reporting_date,payload.progress_snapshot_id)

@router.get("/report-snapshots",response_model=ReportSnapshotListResponse)
async def report_snapshots(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),
    reportingDateFrom:date|None=None,reportingDateTo:date|None=None):
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.list_snapshots(scope,page,pageSize,reportingDateFrom,reportingDateTo)

@router.get("/report-snapshots/{reportId}",response_model=ReportSnapshotReference)
async def report_snapshot(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.view")
    return await request.app.state.finance_live_report_service.get_snapshot(scope,reportId)

@router.get("/report-snapshots/{reportId}/csv",response_class=Response,responses=CSV_DOWNLOAD_RESPONSES)
async def report_snapshot_csv(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.export")
    content=await request.app.state.finance_live_report_service.export(scope,reportId,"csv")
    return Response(content,media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="finance-report-{reportId}.csv"'})

@router.get("/report-snapshots/{reportId}/xlsx",response_class=Response,responses=XLSX_DOWNLOAD_RESPONSES)
async def report_snapshot_xlsx(projectId:str,reportId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance_report.export")
    content=await request.app.state.finance_live_report_service.export(scope,reportId,"xlsx")
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="finance-report-{reportId}.xlsx"'})

@router.get("/audit-events",response_model=AuditEventListResponse)
async def audit_events(projectId:str,request:Request,page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200),
    action:str|None=Query(None,min_length=1,max_length=100),entityType:str|None=Query(None,min_length=1,max_length=100),
    occurredFrom:date|None=None,occurredTo:date|None=None,query:str|None=Query(None,min_length=1,max_length=200)):
    scope=await _resource_scope(projectId,request,"finance.view")
    return await _named(request, await request.app.state.finance_audit_service.list(scope,page,pageSize,action,entityType,occurredFrom,occurredTo,query))

# ------------------------------------------------------------------- material prices
#
# Read-only against the database, every one of them. The UI never reaches Google Sheets:
# an import is a server-side job, and a page that fetched a spreadsheet per row would be
# both slow and a way for a third party to decide what a Finance page shows.
#
# `finance.view` to read, `finance.edit` to decide a unit or to start an import -- the same
# two permissions the rest of this router uses, so nothing new has to be granted anywhere.

@router.get("/material-prices/categories",response_model=MaterialCategoryListResponse)
async def material_categories(projectId:str,request:Request):
    """Every category present, counted from the database. No category is assumed to exist."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items=await request.app.state.material_price_service.categories(scope)
    # Each category carries its own table schema. The page builds its header row from this
    # rather than from a list of its own, so a worksheet column can never be shown for a
    # category whose sheet does not state one.
    return MaterialCategoryListResponse(items=[
        _declared(MaterialCategoryResponse,
                  dict(x, label=category_label(x["category"]),
                       columns=category_columns(x["category"])))
        for x in items])

@router.get("/material-prices/current",response_model=MaterialPriceListResponse)
async def material_prices_current(projectId:str,request:Request,
    category:str|None=Query(None,min_length=1,max_length=60),
    asOf:date|None=None,includeInactive:bool=False,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """The newest price per listing, each with the status that says how to read it.

    `asOf` turns freshness on: without it nothing is called stale, because a page that does
    not say which day it means cannot say whether a price is old.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.current(
        scope,category=category,as_of=asOf,page=page,page_size=pageSize,
        only_active=not includeInactive)
    # The worksheet's own values for each row, read from what the importer already stored
    # on `provider_items.metadata`. Nothing is parsed or filled in here: a blank cell is
    # null, and a category whose sheet states no measurements gets an empty object.
    # `metadata` is the raw worksheet object and is NOT part of the response: `ApiModel`
    # forbids unknown fields, and publishing every stored key would put columns on screen
    # that nobody has decided are real. What travels is `specs` -- this category's declared
    # columns, read from that object and nothing else.
    return MaterialPriceListResponse(items=[
        MaterialPriceResponse(**{**{k: v for k, v in x.items() if k != "metadata"},
                                 "specs": specs_of(x.get("category"), x.get("metadata"))})
        for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)

@router.get("/material-prices/{providerItemId}/history",response_model=MaterialPriceHistoryListResponse)
async def material_price_history(projectId:str,providerItemId:UUID,request:Request,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """Every observation for one listing, newest first. Append-only; nothing is rewritten."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.history(scope,providerItemId,page,pageSize)
    return MaterialPriceHistoryListResponse(
        items=[_declared(MaterialPriceHistoryResponse, x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)

@router.get("/material-prices/runs",response_model=ImportRunListResponse)
async def material_price_runs(projectId:str,request:Request,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """What each import did, including the ones that failed and why."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.runs(scope,page,pageSize)
    return ImportRunListResponse(items=[_declared(ImportRunResponse, x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)

@router.get("/material-prices/invalid-rows",response_model=MaterialPriceHistoryListResponse)
async def material_price_invalid_rows(projectId:str,request:Request,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """Rows that were stored and could not be believed. Findable, not hidden."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.invalid_rows(scope,page,pageSize)
    return MaterialPriceHistoryListResponse(
        items=[_declared(MaterialPriceHistoryResponse, x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)

@router.get("/material-prices/unit-settings",response_model=MaterialUnitSettingListResponse)
async def material_unit_settings(projectId:str,request:Request,
    category:str|None=Query(None,min_length=1,max_length=60)):
    """The unit each category is displayed in, as most recently decided."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items=await request.app.state.material_price_service.unit_settings(scope,category)
    return await _named(request, MaterialUnitSettingListResponse(
        items=[_declared(MaterialUnitSettingResponse, x) for x in items]))

@router.post("/material-prices/unit-settings",response_model=MaterialUnitSettingResponse,status_code=201)
async def set_material_unit(projectId:str,payload:MaterialUnitSettingCreate,request:Request):
    """Choose the unit a category is displayed in. `finance.edit`, appended, with a reason.

    The sheet's own unit never becomes this by itself: it is recorded as what the sheet
    said and this is what a person decided, and they are different fields for that reason.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.material_price_service.set_unit(scope,payload,scope.actor_user_id)
    return await _named(request, _declared(MaterialUnitSettingResponse, row))


# ------------------------------------------------------ labels a person writes by hand
#
# The sheet states no unit for six of its seven categories, so for those rows no amount of
# category-wide configuration can produce a price: somebody has to look at «لوله پلی اتیلن
# ۱۱۰» and say what it is and what its price is per. These endpoints are where they say it.
#
# A label is CONFIGURATION. It never changes the imported observation it describes, and it
# cannot invent a price -- it can only make an existing price usable, or leave it withheld.

def _declared(model, row):
    """Only the fields the response declares, from a row that carries more.

    `RETURNING *` hands back every column, including `organization_id` and `project_id`
    which no response says anything about -- and `ApiModel` forbids extras, correctly, so
    the endpoint answered 500. Narrowing here rather than naming columns in each RETURNING
    keeps the scope columns out of one place instead of six, and a field the model DOES
    declare but the row lacks still fails loudly rather than being defaulted.
    """
    return model(**{name: row[name] for name in model.model_fields if name in row})

def _money_text(value):
    """A Decimal amount as a string, or None.

    Money leaves this API as text so it never passes through a float on the way out. None
    stays None: a listing with no readable price has no price, and `"0"` would say the
    material is free.
    """
    return None if value is None else str(value)

def _registry_unit(value, field):
    """A unit code the Finance registry knows, or a 422 naming the field.

    Checked here rather than in the schema so the refusal can list what IS allowed. A label
    that could introduce a unit the rest of Finance has never heard of would be the start of
    a second vocabulary, which is the one thing this whole area is not allowed to grow.
    """
    if value is None:
        return None
    code = str(value).strip()
    if code not in UNIT_REGISTRY:
        raise HTTPException(status_code=422, detail=(
            "%s must be one of the Finance units: %s" % (field, ", ".join(sorted(UNIT_REGISTRY)))))
    return code

@router.get("/material-prices/labels",response_model=ProviderItemLabelListResponse)
async def material_item_labels(projectId:str,request:Request,providerItemId:UUID|None=None):
    """The current label for each listing, or for one of them."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items=await request.app.state.material_price_service.labels(scope,providerItemId)
    return await _named(request, ProviderItemLabelListResponse(
        items=[_declared(ProviderItemLabelResponse, x) for x in items]))

@router.get("/material-prices/{providerItemId}/labels",response_model=ProviderItemLabelListResponse)
async def material_item_label_history(projectId:str,providerItemId:UUID,request:Request):
    """Every version of one listing's label, oldest first. Nothing here was rewritten."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items=await request.app.state.material_price_service.label_history(scope,providerItemId)
    return await _named(request, ProviderItemLabelListResponse(
        items=[_declared(ProviderItemLabelResponse, x) for x in items]))

@router.post("/material-prices/{providerItemId}/labels",response_model=ProviderItemLabelResponse,status_code=201)
async def save_material_item_label(projectId:str,providerItemId:UUID,
    payload:ProviderItemLabelCreate,request:Request):
    """Record what this listing is. `finance.edit`, appended, with a reason.

    Supersedes the previous version rather than replacing it: what was believed last month
    stays readable, which is the same rule every other decision in Finance follows.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    payload.source_unit=_registry_unit(payload.source_unit,"sourceUnit")
    payload.target_unit=_registry_unit(payload.target_unit,"targetUnit")
    row=await request.app.state.material_price_service.save_label(
        scope,providerItemId,payload,scope.actor_user_id)
    return await _named(request, _declared(ProviderItemLabelResponse, row))

@router.get("/material-prices/{providerItemId}/factors",response_model=ProviderItemFactorListResponse)
async def material_item_factors(projectId:str,providerItemId:UUID,request:Request):
    """The conversion factors somebody measured for this one product."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items=await request.app.state.material_price_service.repository.item_unit_factors(scope,providerItemId)
    return await _named(request, ProviderItemFactorListResponse(
        items=[_declared(ProviderItemFactorResponse, x) for x in items]))

@router.post("/material-prices/{providerItemId}/factors",response_model=ProviderItemFactorResponse,status_code=201)
async def save_material_item_factor(projectId:str,providerItemId:UUID,
    payload:ProviderItemFactorCreate,request:Request):
    """Store a measurement of this product, so a crossing between dimensions becomes possible.

    Both units must be Finance units, and they must actually cross a dimension: a factor
    between two units the registry can already convert would be a project quietly redefining
    the gram, and it is refused with the ratio that already exists.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    payload.from_unit=_registry_unit(payload.from_unit,"fromUnit")
    payload.to_unit=_registry_unit(payload.to_unit,"toUnit")
    if payload.from_unit==payload.to_unit:
        raise HTTPException(status_code=422,detail="fromUnit and toUnit must differ")
    if can_convert(payload.from_unit,payload.to_unit):
        raise HTTPException(status_code=422,detail=(
            "%s and %s are the same dimension and already convert at %s; a product factor "
            "is only for a crossing units alone cannot answer"
            % (payload.from_unit,payload.to_unit,quantity_factor(payload.from_unit,payload.to_unit))))
    row=await request.app.state.material_price_service.save_item_factor(
        scope,providerItemId,payload,scope.actor_user_id)
    return await _named(request, _declared(ProviderItemFactorResponse, row))

@router.get("/material-prices/unresolved",response_model=UnresolvedItemListResponse)
async def material_unresolved_items(projectId:str,request:Request,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """Listings nobody has labelled that the sheet said nothing useful about.

    The work queue: these are the rows where no category-wide setting can produce a price,
    so they are the ones worth putting in front of a person.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.unresolved(scope,page,pageSize)
    return UnresolvedItemListResponse(items=[_declared(UnresolvedItemResponse, x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)

# ---------------------------------------------------------------- item -> daily price
#
# The bridge between the two modules. MSP/MPP says an activity consumes a material and how
# much; the daily-price sheet says what a named product costs today. Nothing here matches
# the two by name, by resemblance, or by price -- a mapping exists because a person made
# one, and until then the item reports «محصول قیمت روز انتخاب نشده» rather than a number.

@router.get("/item-price-mappings/candidates",response_model=CandidateListResponse)
async def item_price_candidates(projectId:str,request:Request,
    category:str|None=Query(None,max_length=64),
    query:str|None=Query(None,min_length=1,max_length=120),
    providerId:UUID|None=Query(None),
    productType:str|None=Query(None,max_length=120),
    page:int=Query(1,ge=1),pageSize:int=Query(25,ge=1,le=100)):
    """Listings a person can choose from, with each category's own spec columns.

    Ordered by category and name, never by price: offering the cheapest first is a policy,
    and a policy nobody configured must not arrive disguised as an ordering.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    rows,total=await request.app.state.item_price_mapping_service.candidates(
        scope,category=category,query=query,provider_id=providerId,
        product_type=productType,page=page,page_size=pageSize)
    items=[]
    for row in rows:
        body=dict(row)
        body["provider_item_id"]=str(row["provider_item_id"])
        body["provider_id"]=str(row["provider_id"]) if row.get("provider_id") else None
        body["current_price_irr"]=_money_text(row.get("normalized_price_irr"))
        body["raw_price"]=_money_text(row.get("raw_price"))
        body["source_unit_code"]=canonical_unit(row.get("normalized_unit") or row.get("source_unit"))
        body["category_label"]=category_label(row.get("category"))
        body["specs"]=specs_of(row.get("category"),row.get("metadata"))
        body["spec_columns"]=spec_columns(row.get("category"))
        body["worksheet"]=row.get("source_worksheet")
        items.append(_declared(CandidateProductResponse, body))
    return CandidateListResponse(items=items,page=page,page_size=pageSize,total_items=total)

@router.get("/item-price-mappings/filters",response_model=MappingFiltersResponse)
async def item_price_filters(projectId:str,request:Request,
    category:str|None=Query(None,max_length=64),providerId:UUID|None=Query(None)):
    """What the modal may filter by at THIS point in its cascade.

    Read from the data, never a hard-coded list -- and scoped as the cascade narrows:
    providers by the chosen category, product types by category AND provider. Offering a
    supplier who sells no brick under «آجر», or a type that exists only on somebody else's
    products, yields an empty result list that reads as a broken page rather than as an
    empty category.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    filters=await request.app.state.item_price_component_service.filters(
        scope,category=category,provider_id=providerId)
    categories=await request.app.state.material_price_service.categories(scope)
    return MappingFiltersResponse(
        providers=[{"id":str(p["id"]),"name":p["name"]} for p in filters["providers"]],
        product_types=filters["product_types"],
        usage_modes=filters["usage_modes"],
        categories=[{"category":c["category"],"label":category_label(c["category"]),
                     "itemCount":c["item_count"]} for c in categories],
        units=[{"code":u["code"],"label":u["label"],"dimension":u["dimension"],
                "dimensionLabel":u["dimension_label"]} for u in filters["units"]])

@router.get("/estimate-lines/{lineId}/price-mapping",response_model=ItemPriceMappingResponse|None)
async def read_item_price_mapping(projectId:str,lineId:UUID,request:Request):
    """The live mapping for one line, or null when nobody has made one."""
    scope=await _resource_scope(projectId,request,"finance.view")
    row=await request.app.state.item_price_mapping_service.mapping_for_line(scope,lineId)
    if row is None:return None
    return await _named(request, _declared(ItemPriceMappingResponse, row))

@router.get("/estimate-lines/{lineId}/price-mapping/history",response_model=list[ItemPriceMappingResponse])
async def item_price_mapping_history(projectId:str,lineId:UUID,request:Request):
    """Every version. What a report issued last month was priced against is in here."""
    scope=await _resource_scope(projectId,request,"finance.view")
    rows=await request.app.state.item_price_mapping_service.history_for_line(scope,lineId)
    return await _named(request, [_declared(ItemPriceMappingResponse, r) for r in rows])

@router.get("/estimate-lines/{lineId}/price-preview",response_model=ConvertedPricePreviewResponse)
async def item_price_preview(projectId:str,lineId:UUID,request:Request,
    providerItemId:UUID=Query(...),selectedUnit:str=Query(...,min_length=1,max_length=32)):
    """What this listing would cost in this unit, before anything is saved.

    So «ضریب تبدیل لازم است» is something a person sees while choosing, rather than
    discovers after committing.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    body=await request.app.state.item_price_mapping_service.preview(
        scope,provider_item_id=providerItemId,selected_unit=selectedUnit,
        estimate_line_id=lineId)
    return _declared(ConvertedPricePreviewResponse, body)

@router.post("/estimate-lines/{lineId}/price-mapping",response_model=ItemPriceMappingResponse,
             status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def save_item_price_mapping(projectId:str,lineId:UUID,payload:ItemPriceMappingCreate,
                                  request:Request):
    """Record which listing prices this line, and in which official unit.

    Appended, never edited: the previous version is superseded and stays readable, because
    a report issued against it has to keep meaning what it meant.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.item_price_mapping_service.save_mapping(
        scope,estimate_line_id=lineId,payload=payload,actor_id=scope.actor_user_id)
    return await _named(request, _declared(ItemPriceMappingResponse, row))

# ------------------------------------------------- one item, many materials
#
# An activity is not a material. «کانال‌کنی» is 500 cubic metres of trenching, and it
# consumes rebar and pipe and brick that the schedule never names -- a schedule describes
# work, not a bill of materials. So a line is priced by a LIST of components, each naming a
# real listing, an official unit, and how much of it this activity uses.
#
# Nothing here decides what an activity consumes. A component exists because a person said
# so, with a reason, and the row reports «نیازمند افزودن مصالح» until they do.

def _component_row(row):
    """A stored component version for the wire: decimals as text.

    Money and quantities are Decimals in the database and strings on the wire, because a
    JSON number would pass them through a float and stop them being the figures the database
    holds.
    """
    body=dict(row)
    for field in ("usage_quantity_decimal","component_quantity_decimal",
                  "converted_daily_unit_price_irr","component_daily_cost_irr"):
        body[field]=_money_text(row.get(field))
    return _declared(PriceComponentRow, body)

@router.get("/item-price-mappings/status",response_model=ItemPriceRowStatusListResponse)
async def item_price_row_status(projectId:str,request:Request):
    """Every estimate line's pricing state and total, for the financial-items table.

    One call for the whole table. A line nobody has priced is PRESENT here with
    `needs_components` -- leaving it out would be indistinguishable from a line the caller
    forgot to ask about, and the table needs to show what is waiting.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    answers=await request.app.state.item_price_component_service.table_status(scope)
    return ItemPriceRowStatusListResponse(
        items=[_declared(ItemPriceRowStatusResponse, row) for row in answers.values()])

@router.get("/estimate-lines/{lineId}/price-mapping/components",
            response_model=PriceComponentListResponse)
async def read_price_components(projectId:str,lineId:UUID,request:Request):
    """Every material of one line, priced at today's prices, with the row total.

    Inactive components travel too: somebody who retired a material needs to see that they
    did. Only the active ones enter the total.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    body=await request.app.state.item_price_component_service.components_for_line(scope,lineId)
    return await _named(request, PriceComponentListResponse(
        line=(_declared(PricedLineHeaderResponse, body["line"]) if body["line"] else None),
        components=[_declared(PriceComponentResponse, c) for c in body["components"]],
        total=_declared(ItemPriceRowStatusResponse,
                        dict(body["total"], estimate_line_id=str(lineId)))))

@router.get("/estimate-lines/{lineId}/price-mapping/components/history",
            response_model=list[PriceComponentRow])
async def price_component_history(projectId:str,lineId:UUID,request:Request):
    """Every version of every component of this line. What a past report was priced on."""
    scope=await _resource_scope(projectId,request,"finance.view")
    rows=await request.app.state.item_price_component_service.history_for_line(scope,lineId)
    return await _named(request, [_component_row(r) for r in rows])

@router.get("/estimate-lines/{lineId}/price-component-preview",
            response_model=PriceComponentPreviewResponse)
async def price_component_preview(projectId:str,lineId:UUID,request:Request,
    providerItemId:UUID=Query(...),selectedUnit:str=Query(...,min_length=1,max_length=32),
    usageMode:str=Query(...,max_length=32),usageQuantity:Decimal|None=Query(None)):
    """What one component would cost, before anything is saved.

    Called on every change, so «ضریب تبدیل لازم است» is something a person sees while
    choosing rather than discovers after committing.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    body=await request.app.state.item_price_component_service.preview_component(
        scope,estimate_line_id=lineId,provider_item_id=providerItemId,
        selected_unit=selectedUnit,usage_mode=usageMode,usage_quantity=usageQuantity)
    return _declared(PriceComponentPreviewResponse, body)

@router.get("/estimate-lines/{lineId}/price-total-preview",
            response_model=ItemPriceRowStatusResponse)
async def price_total_preview(projectId:str,lineId:UUID,request:Request,
    providerItemId:UUID|None=Query(None),
    selectedUnit:str|None=Query(None,min_length=1,max_length=32),
    usageMode:str|None=Query(None,max_length=32),usageQuantity:Decimal|None=Query(None)):
    """The line's total as it stands, optionally including one unsaved component.

    The draft is what makes this different from reading the total back: a person sees what
    the row WILL come to before they commit the material, not after.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    draft=None
    if providerItemId is not None and selectedUnit is not None:
        draft={"provider_item_id":providerItemId,"selected_unit":selectedUnit,
               "usage_mode":usageMode,"usage_quantity":usageQuantity}
    total=await request.app.state.item_price_component_service.preview_total(
        scope,lineId,draft)
    return _declared(ItemPriceRowStatusResponse,
                     dict(total, estimate_line_id=str(lineId)))

@router.post("/estimate-lines/{lineId}/price-mapping/components",
             response_model=PriceComponentRow,status_code=201,
             responses=FINANCE_ERROR_RESPONSES)
async def add_price_component(projectId:str,lineId:UUID,payload:PriceComponentCreate,
                              request:Request):
    """Record that this activity uses this much of this material."""
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.item_price_component_service.add_component(
        scope,estimate_line_id=lineId,payload=payload,actor_id=scope.actor_user_id)
    return await _named(request, _component_row(row))

@router.patch("/estimate-lines/{lineId}/price-mapping/components/{componentId}",
              response_model=PriceComponentRow,responses=FINANCE_ERROR_RESPONSES)
async def update_price_component(projectId:str,lineId:UUID,componentId:UUID,
                                 payload:PriceComponentCreate,request:Request):
    """Correct one material. Appended as a new version, never edited in place.

    The previous version is superseded and stays readable, because a report issued against
    it has to keep meaning what it meant.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.item_price_component_service.update_component(
        scope,estimate_line_id=lineId,component_id=componentId,payload=payload,
        actor_id=scope.actor_user_id)
    return await _named(request, _component_row(row))

@router.post("/estimate-lines/{lineId}/price-mapping/components/{componentId}/deactivate",
             response_model=PriceComponentRow,responses=FINANCE_ERROR_RESPONSES)
async def deactivate_price_component(projectId:str,lineId:UUID,componentId:UUID,
                                     payload:PriceComponentDeactivate,request:Request):
    """Retire one material from the line. Appended, never deleted.

    The row stays because a report issued while it was active was calculated with it, and a
    total whose components have vanished cannot be explained afterwards.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.item_price_component_service.deactivate_component(
        scope,estimate_line_id=lineId,component_id=componentId,reason=payload.reason,
        actor_id=scope.actor_user_id)
    return await _named(request, _component_row(row))
