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
from .security.guards import (FinanceNotFound, FinanceScope,
                              authorize_finance_request)
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
from .schemas.extractions import ExtractionConfirm,ExtractionDraftResponse,ExtractionEdit,ExtractionListResponse,ExtractionReject,ExtractionRetry,ExtractionStart
from .domain.monthly import DEFAULT_MONTH_COUNT,MAX_MONTH_COUNT
from .schemas.reports import LiveReportResponse,MonthlyReportResponse,OperationalOverviewResponse,ReportSnapshotCreate,ReportSnapshotListResponse,ReportSnapshotReference,ReportVarianceListResponse,WbsReportResponse
from .schemas.audit import AuditEventListResponse,AuditEventResponse
from .schemas.items_and_estimates import (AssignmentResponse,
    ItemsAndEstimatesResponse, LegacyLineResponse,
    ResourceAggregateResponse, SourceVersionResponse)
from .security import service_key
from .services.material_price_import import MaterialPriceSheetNotConfigured
from .schemas.material_prices import (ManualPriceCreate,ManualPriceResponse,
    MaterialCategoryCreate,ImportRunStartedResponse,ImportRunListResponse,ImportRunResponse,
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
from .schemas.unit_conversion_rules import (ConversionIssueListResponse,
    ConversionIssueResponse,ConversionRuleApprove,ConversionRuleCreate,
    ConversionRuleListResponse,ConversionRulePreviewResponse,ConversionRuleResponse,
    ConversionRuleSupersede,DailyEstimateResponse)
from .services.unit_conversion_rules import registry_units
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


async def _service_scope(project_id, service):
    """The scope an AUTOMATED import runs in. The caller chooses none of it.

    The organization is read from the provider configuration of the project named in the
    path, never from the request. A key that could name a tenant could import one
    tenant's prices into another's books, and nothing about holding the key says which
    tenant the holder speaks for.

    A project with no active spreadsheet provider is not reachable this way at all: there
    is nothing configured to import, so there is no organization to infer and the answer
    is a refusal rather than a guess.

    `actor_user_id` stays None. There is no user, and minting one would put a name in the
    audit trail that belongs to nobody -- the run records `initiatedBy: system` instead,
    which is true.
    """
    for row in await service.repository.projects_with_active_providers():
        if row["project_id"] == project_id:
            return FinanceScope(organization_id=row["organization_id"],
                                project_id=project_id, actor_user_id=None)
    raise MaterialPriceSheetNotConfigured(
        "no active price provider is configured for project %r, so there is nothing "
        "to import" % project_id)


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

@router.get("/items-and-estimates", response_model=ItemsAndEstimatesResponse)
async def items_and_estimates(projectId: str, request: Request):
    """Every MPP resource of the live source version, its assignments, and what they cost.

    A hierarchy rather than the flat list `GET /estimate-lines` returns, and a separate
    endpoint rather than a reshaped one: the flat list is what invoices and the report
    read, and changing its shape would change theirs. This is the Resource -> Assignment
    view the approved model is stated in.

    Read-only. Nothing here creates a resource, an assignment or an estimate line.
    """
    scope = await _resource_scope(projectId, request, "finance.view")
    body = await request.app.state.items_and_estimates_service.listing(scope)
    return ItemsAndEstimatesResponse(
        source_version=(None if body["source_version"] is None
                        else _declared(SourceVersionResponse, body["source_version"])),
        resources=[_declared(ResourceAggregateResponse,
                             dict(r, assignments=[_declared(AssignmentResponse, a)
                                                  for a in r["assignments"]]))
                   for r in body["resources"]],
        legacy_lines=[_declared(LegacyLineResponse, x) for x in body["legacy_lines"]],
        project_current_estimate_irr=body["project_current_estimate_irr"],
        counted_assignments=body["counted_assignments"],
        excluded_assignments=body["excluded_assignments"],
        issue_counts=body["issue_counts"])

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
    # `draft_id`, which is what an ExtractionDraft calls it -- it has no `id` at all. This
    # read `existing.id` and therefore raised AttributeError on the one branch it runs in:
    # a file that ALREADY has a draft. Every such request answered 500 instead of the 202
    # that tells the client «this file was read before, here is the result», and the client
    # -- which ignores the response and polls the file's status -- showed the old draft as
    # though it were new. Nothing was written, because the branch returns before the
    # attachment is claimed, so no figure was ever wrong; the answer was.
    return {"fileId":str(fileId),"processingStatus":attachment.processing_status,
            "extractionId":None if existing is None else str(existing.draft_id),
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

@router.patch("/extractions/{draftId}",response_model=ExtractionDraftResponse,responses=FINANCE_ERROR_RESPONSES)
async def edit_extraction(projectId:str,draftId:UUID,payload:ExtractionEdit,request:Request):
    """Correct a draft before confirming it. Changes nothing financial.

    The review screen needed somewhere to put a reviewer's corrections BEFORE the decision
    to confirm. Until now the only way to state a different value was to send it inside the
    confirmation itself, so a reviewer could not fix a misheard amount, look at the result,
    and then decide. Now they can, as many times as they like.

    An edit writes `confirmedValue` beside what the model read; `extractedValue` is never
    overwritten, so the transcript and the page reading survive it. The draft stays
    `awaitingReview`, its financial effect stays zero, and `confirm` remains the only door
    to the financial engine -- which is the rule this endpoint was built around rather than
    through.
    """
    scope=await _resource_scope(projectId,request,"finance.manage_invoice")
    return ExtractionDraftResponse.from_domain(await request.app.state.finance_extraction_service.edit(scope,draftId,payload))

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
    # `today` so the service can say which equipment rates are in force without
    # reading a clock of its own -- the rule this service has always followed.
    items=await request.app.state.material_price_service.categories(scope,today=date.today())
    # Each category carries its own table schema. The page builds its header row from this
    # rather than from a list of its own, so a worksheet column can never be shown for a
    # category whose sheet does not state one.
    return MaterialCategoryListResponse(items=[
        _declared(MaterialCategoryResponse,
                  # A declared category may carry its own label; otherwise the shared
                  # vocabulary names it, exactly as before.
                  dict(x, label=(x.get("declared_label")
                                 or category_label(x["category"])),
                       columns=category_columns(x["category"])))
        for x in items])

@router.post("/material-prices/categories",response_model=MaterialCategoryResponse,
             status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def declare_material_category(projectId:str,payload:MaterialCategoryCreate,
                                    request:Request):
    """Name a category that does not exist yet, at a level.

    The chips on the prices page are counted from `provider_items.category`, and this
    does not change that. What it adds is the two things a column cannot hold: which
    level the word belongs to, and a category that exists before anything has been
    recorded in it -- which is the state a person is in between naming a category and
    entering the first price for it.

    Permissions are the ones that already exist, gated the way the conversion rules gate
    theirs. The ROUTE asks for `finance.edit`, like every other price write. The SERVICE
    then refuses `organization` and `global` unless the caller also holds
    `finance.manage_settings` -- a word that lands in every project's list is a decision
    about the tenant, and editing THIS project is not consent to that.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.material_price_service.declare_category(
        scope,payload,scope.actor_user_id,permissions=scope.permission_codes)
    return _declared(MaterialCategoryResponse,
                     dict(row,item_count=0,active_count=0,inactive_count=0,
                          declared=True,
                          label=row.get("label") or category_label(row["category"]),
                          columns=category_columns(row["category"])))

@router.post("/material-prices/manual",response_model=ManualPriceResponse,
             status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def record_manual_material_price(projectId:str,payload:ManualPriceCreate,
                                       request:Request):
    """Record a price somebody obtained for a product the sheet does not carry.

    It becomes a listing and an observation in the same tables as every imported price,
    so the prices table, the history and the estimate read it without knowing it was
    typed. Two things mark it: `origin = 'manual'`, and an author and a reason, which are
    required by the database rather than by this handler.

    Recording again for the same product APPENDS. `price_observations` is append-only by
    trigger and correcting a price means stating the new one, so the history shows what
    was believed and when -- exactly as it does for the sheet.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    answer=await request.app.state.material_price_service.record_manual_price(
        scope,payload,scope.actor_user_id)
    return _declared(ManualPriceResponse,dict(answer,
                                              provider_item_id=str(answer["provider_item_id"])))

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
        only_active=not includeInactive,
        # The day to read equipment rates against when the caller named none. It is NOT a
        # default for `asOf`: passing it there would turn freshness on for every sheet row
        # and start calling prices stale on a request that never asked about a date.
        today=date.today())
    # The worksheet's own values for each row, read from what the importer already stored
    # on `provider_items.metadata`. Nothing is parsed or filled in here: a blank cell is
    # null, and a category whose sheet states no measurements gets an empty object.
    # `metadata` is the raw worksheet object and is NOT part of the response: `ApiModel`
    # forbids unknown fields, and publishing every stored key would put columns on screen
    # that nobody has decided are real. What travels is `specs` -- this category's declared
    # columns, read from that object and nothing else.
    # `_declared` rather than `**`: the row now carries the listing's typed columns, the
    # observation's own columns and the join's extras, and the response declares a subset.
    # Spreading everything was fine while the two matched and becomes a 500 the moment they
    # do not, which is exactly what adding columns to provider_items does.
    # `productIdSnapshot` used to be assembled here from a key the service does not put in
    # the row, so it was null on every response. The snapshots now come off the observation
    # in the service, beside the price they belong to, and this layer only adds `specs`.
    # `_named` for the same reason every other listing endpoint calls it: the rows carry
    # `labelledBy` as an id, the response declares `labelledByName`, and without this the
    # name was never looked up. One lookup for the page, not one per row.
    return await _named(request, MaterialPriceListResponse(items=[
        _declared(MaterialPriceResponse,
                  {**{k: v for k, v in x.items() if k != "metadata"},
                   "specs": specs_of(x.get("category"), x.get("metadata"))})
        for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize))

@router.get("/material-prices/{providerItemId}/history",response_model=MaterialPriceHistoryListResponse)
async def material_price_history(projectId:str,providerItemId:UUID,request:Request,
    page:int=Query(1,ge=1),pageSize:int=Query(50,ge=1,le=200)):
    """Every observation for one listing, newest first. Append-only; nothing is rewritten."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items,total=await request.app.state.material_price_service.history(scope,providerItemId,page,pageSize)
    return MaterialPriceHistoryListResponse(
        items=[_declared(MaterialPriceHistoryResponse, x) for x in items],
        page=page,page_size=pageSize,total_items=total,total_pages=(total+pageSize-1)//pageSize)


@router.get("/material-prices/{providerItemId}/latest",response_model=MaterialPriceResponse)
async def material_price_latest(projectId:str,providerItemId:UUID,request:Request):
    """One provider listing's newest usable observation in the authorized project scope."""
    scope=await _resource_scope(projectId,request,"finance.view")
    items,_=await request.app.state.material_price_service.current(
        scope,provider_item_id=providerItemId,page=1,page_size=1)
    if not items:
        raise HTTPException(status_code=404,detail="material price listing not found")
    row=items[0]
    return _declared(MaterialPriceResponse,
                     {**{k:v for k,v in row.items() if k!="metadata"},
                      "specs":specs_of(row.get("category"),row.get("metadata"))})

@router.post("/material-prices/import-runs",response_model=ImportRunStartedResponse,
             status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def start_material_price_import(projectId:str,request:Request,
    force:bool=Query(True,description="import even if one ran recently"),
    dueOnly:bool=Query(False,description="import only if the interval has passed"),
    triggerSource:str|None=Query(None,max_length=64,
                                 description="what asked for this import, for the audit")):
    """Read the configured sheet now, and say what that did.

    THE TRIGGER THIS SYSTEM DID NOT HAVE.

    `price_observations` has exactly one production writer, and until now it was reachable
    only by running `scripts/import_material_prices.py` by hand on a machine with the repo
    checked out. `price_providers.default_interval_minutes` says 1440 on every provider and
    nothing reads it: there is no scheduler, no worker and no webhook. Updating the Google
    Sheet therefore did NOT reach the database, and the newest prices in it were whatever
    date somebody last ran the script.

    WHAT IT ACCEPTS: nothing. The sheet is `FINANCE_MATERIAL_PRICE_SHEET_URL`, deliberately
    -- a caller who could name the sheet could point this host at any sheet at all, and a
    caller who could post rows could write a price nobody published. The body is empty and
    the answer comes from the one configured source.

    IDEMPOTENT. Re-running against an unchanged sheet inserts nothing and reports every row
    as `alreadyPresent`: the fingerprint is (product id, workflow date, price), and a
    partial unique index refuses the second copy. Two simultaneous runs are refused by the
    database, not by a flag.
    """
    service=getattr(request.app.state,"material_price_import_service",None)
    if service is None:
        raise MaterialPriceSheetNotConfigured(
            "this host has no material price import configured; "
            "set FINANCE_MATERIAL_PRICE_SHEET_URL and restart")
    # TWO CALLERS, TWO PROOFS.
    #
    # A person clicking a button carries a host session and is gated on `finance.edit`,
    # exactly as before. n8n carries no session -- it is not a person, has no account and
    # appears in no directory -- so it presents the configured service key instead. A
    # request with NO key takes the human path untouched; a request with a WRONG key is
    # refused rather than being dropped into a permission error about a role the
    # automation was never going to hold.
    automated=service_key.authenticate(request)
    if automated:
        scope=await _service_scope(projectId,service)
    else:
        scope=await _resource_scope(projectId,request,"finance.edit")
    # `force` and `dueOnly` are inverses of one decision: whether to respect the schedule.
    # Both names are accepted because both are how callers ask -- a person clicking a
    # button says force, a scheduler says dueOnly -- and either one asking for the
    # schedule to be respected is enough.
    if dueOnly or not force:
        interval=service.interval_minutes
        due=await service.due_projects(interval)
        if not any(row["project_id"]==scope.project_id for row,_ in due):
            # Nothing read, nothing written, and the reason is a number rather than a
            # shrug: a caller that gets "skipped" with no interval cannot tell a working
            # schedule from a broken one.
            return ImportRunStartedResponse(
                status="skipped",run=None,inserted=0,already_present=0,rejected=0,
                worksheet_report={},
                trigger_source=(triggerSource or ("n8n_daily_material_price_update"
                                                 if automated else "manual")),
                initiated_by=(service_key.SYSTEM_INITIATOR if automated else None),
                message=("skipped: an import for this project succeeded within the last "
                         "%d minutes" % interval))
    outcome=await service.run(scope)
    return ImportRunStartedResponse(
        status=outcome.status,
        run=_declared(ImportRunResponse, outcome.run),
        inserted=outcome.inserted,
        already_present=outcome.already_present,
        rejected=outcome.rejected,
        worksheet_report=outcome.worksheet_report or {},
        trigger_source=(triggerSource or ("n8n_daily_material_price_update" if automated
                                          else "manual")),
        initiated_by=(service_key.SYSTEM_INITIATOR if automated
                      else (None if scope.actor_user_id is None
                            else str(scope.actor_user_id))),
        message=("%d new price(s); %d already recorded; %d row(s) refused"
                 % (outcome.inserted, outcome.already_present, outcome.rejected)))

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
    calculation=body.pop("daily_estimate",None)
    answer=_declared(ConvertedPricePreviewResponse, body)
    if calculation is not None:
        answer.daily_estimate=_declared(
            DailyEstimateResponse, dict(calculation, estimate_line_id=str(lineId)))
    return answer

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

# ---------------------------------------------- unit conversion rules and mismatches
#
# A price per branch and a line measured in kilograms is an ordinary state of a
# half-configured project, not an error. It is answered -- never calculated around, and
# never with a factor of one, which on the reference product is wrong by 22.
#
# A rule is a statement about QUANTITY: `1 from_unit = factor to_unit`. The price
# arithmetic is derived from it in `domain/daily_estimate.py` and stored nowhere, so no
# call site can get the direction backwards.

def _rule_body(row):
    """A stored rule for the wire: exact numbers as text."""
    body=dict(row)
    body["factor_value"]=_money_text(row.get("factor_value"))
    return _declared(ConversionRuleResponse, body)

def _issue_body(row):
    return _declared(ConversionIssueResponse, row)

@router.get("/finance-settings/unit-conversions",response_model=ConversionRuleListResponse)
async def list_unit_conversion_rules(projectId:str,request:Request,
    scopeType:str|None=Query(None,max_length=32),
    status:str|None=Query(None,max_length=16),
    fromUnit:str|None=Query(None,max_length=32),
    toUnit:str|None=Query(None,max_length=32)):
    """Every rule this project may be affected by, including tenant-wide ones.

    A site-wide rule is listed here on purpose: somebody about to write a narrower one
    needs to see that a broader one already answers the question, or they will write a
    second answer that shadows the first.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    rows=await request.app.state.unit_conversion_rule_service.list_rules(
        scope,scope_type=scopeType,status=status,from_unit=fromUnit,to_unit=toUnit)
    return ConversionRuleListResponse(
        items=[_rule_body(r) for r in rows],
        units=[{"code":u["code"],"label":u["label"],"dimension":u["dimension"],
                "dimensionLabel":u["dimension_label"],
                "productDependentFrom":u["product_dependent_from"]}
               for u in registry_units()])

@router.post("/finance-settings/unit-conversions",response_model=ConversionRuleResponse,
             status_code=201,responses=FINANCE_ERROR_RESPONSES)
async def create_unit_conversion_rule(projectId:str,payload:ConversionRuleCreate,
                                      request:Request):
    """Write a conversion down. It arrives as a DRAFT and changes no calculation.

    A rule broader than one product is refused for a crossing that depends on the product:
    `1 branch = 22 kg` is a weighing of one listing and is wrong for the next size, while
    `1 ton = 1000 kg` is arithmetic and may be stated once for everything.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.unit_conversion_rule_service.create_rule(
        scope,payload=payload,actor_id=scope.actor_user_id,
        permissions=scope.permission_codes)
    return await _named(request, _rule_body(row))

@router.get("/finance-settings/unit-conversions/{ruleId}",response_model=ConversionRuleResponse)
async def read_unit_conversion_rule(projectId:str,ruleId:UUID,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view")
    row=await request.app.state.unit_conversion_rule_service.rule(scope,ruleId)
    if row is None:raise HTTPException(status_code=404,detail="conversion rule not found")
    return await _named(request, _rule_body(row))

@router.get("/finance-settings/unit-conversions/{ruleId}/history",
            response_model=list[ConversionRuleResponse])
async def unit_conversion_rule_history(projectId:str,ruleId:UUID,request:Request):
    """Every version of this rule. What a report issued last month was converted by."""
    scope=await _resource_scope(projectId,request,"finance.view")
    rows=await request.app.state.unit_conversion_rule_service.history(scope,ruleId)
    return await _named(request, [_rule_body(r) for r in rows])

@router.get("/finance-settings/unit-conversions/{ruleId}/preview",
            response_model=ConversionRulePreviewResponse,responses=FINANCE_ERROR_RESPONSES)
async def preview_unit_conversion_rule(projectId:str,ruleId:UUID,request:Request,
    priceIrr:Decimal|None=Query(None)):
    """What this rule would do to a price, without letting it near a calculation.

    A draft may be previewed -- that is what a draft is for -- and the answer says plainly
    whether it is in use.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    body=await request.app.state.unit_conversion_rule_service.preview_rule(
        scope,ruleId,price_irr=priceIrr)
    return _declared(ConversionRulePreviewResponse, body)

@router.post("/finance-settings/unit-conversions/{ruleId}/approve",
             response_model=ConversionRuleResponse,responses=FINANCE_ERROR_RESPONSES)
async def approve_unit_conversion_rule(projectId:str,ruleId:UUID,
                                       payload:ConversionRuleApprove,request:Request):
    """Let a rule into calculations, and close the mismatches it answers.

    A rule that outlives this project needs `finance.manage_settings`: approving one is a
    statement about every project this tenant will ever run, and editing THIS project is
    not consent to that.
    """
    scope=await _resource_scope(projectId,request,"finance.edit")
    row,_resolved=await request.app.state.unit_conversion_rule_service.approve_rule(
        scope,ruleId,actor_id=scope.actor_user_id,permissions=scope.permission_codes)
    return await _named(request, _rule_body(row))

@router.post("/finance-settings/unit-conversions/{ruleId}/supersede",
             response_model=ConversionRuleResponse,responses=FINANCE_ERROR_RESPONSES)
async def supersede_unit_conversion_rule(projectId:str,ruleId:UUID,
                                         payload:ConversionRuleSupersede,request:Request):
    """Close a rule's window. The row stays, because a calculation made under it has to
    remain explainable and a deleted rule explains nothing."""
    scope=await _resource_scope(projectId,request,"finance.edit")
    row=await request.app.state.unit_conversion_rule_service.supersede_rule(
        scope,ruleId,effective_to=payload.effective_to,
        permissions=scope.permission_codes)
    return await _named(request, _rule_body(row))

@router.get("/finance-settings/unit-conversion-issues",
            response_model=ConversionIssueListResponse)
async def list_unit_conversion_issues(projectId:str,request:Request,
    status:str|None=Query("open",max_length=16),
    lineId:UUID|None=Query(None)):
    """The mismatches still blocking a daily estimate, oldest question first by last sighting.

    One row per line, product and unit pair: a preview refreshed two hundred times counts
    to two hundred rather than filling this list with the same question.
    """
    scope=await _resource_scope(projectId,request,"finance.view")
    rows=await request.app.state.unit_conversion_rule_service.list_issues(
        scope,status=status,estimate_line_id=lineId)
    return ConversionIssueListResponse(items=[_issue_body(r) for r in rows])


# ----------------------------------------------------------------- MPP mapping, in production
#
# The schedule's own money, turned into estimate lines. The mapping itself has existed
# since 0012 and ran only from the development host, which meant the one production route
# to a fixed-cost line was an import that happened to be followed by a developer calling
# it. These two put the same service behind the same guards every other Finance route
# uses: `finance.view` to look, `finance.edit` to write.
#
# Neither endpoint takes a version id. The version is the project's own active one, read
# through the shared rule -- a caller naming one could ask this project to be mapped from
# another project's schedule, and there is no reason for the API to offer that.

def _mpp_mapping_service(request: Request):
    """The mapping service, or a 503 that says what is missing.

    Optional on purpose: a Finance host with no MPP root configured is a perfectly
    ordinary deployment. Saying so beats an AttributeError raised halfway through a
    request, which reaches the caller as a 500 about nothing they can act on.
    """
    service = getattr(request.app.state, "finance_mpp_mapping_service", None)
    if service is None:
        raise HTTPException(status_code=503,
                            detail="finance MPP mapping is not configured on this host")
    return service


@router.get("/mpp/status", responses=FINANCE_ERROR_RESPONSES)
async def mpp_status(projectId: str, request: Request):
    """What became of every row of the active schedule, and which file it came from.

    Reads and counts; writes nothing and computes no financial figure. The provenance
    fields come from the SAME statement that chose the version the counts were taken
    over, so a reader can never be shown one file's name beside another file's numbers.

    A project that has imported nothing is not an error: it reports zero of everything
    with a null version, which is a different answer from a failure and reads as one.
    """
    scope = await _resource_scope(projectId, request, "finance.view")
    service = _mpp_mapping_service(request)
    organization = str(scope.organization_id)
    status = await service.mapping_status(organization, projectId)
    detail = await service.current_version_detail(organization, projectId)
    status["sourceFileName"] = None if detail is None else detail["source_file_name_safe"]
    status["importedAt"] = None if detail is None else detail["imported_at"]
    # The file's own status date, when it stated one. Null is common and means the file
    # named no reporting date -- not that the import has none.
    status["reportingDate"] = None if detail is None else detail["reporting_date"]
    status["rowCount"] = None if detail is None else detail["row_count"]
    return status


@router.post("/mpp/remap", responses=FINANCE_ERROR_RESPONSES)
async def mpp_remap(projectId: str, request: Request):
    """Re-run the mapping over the project's active schedule and report what changed.

    Idempotent by construction rather than by a flag: every write below is a
    match-or-insert keyed on the file's own identifiers, so running this twice over an
    unchanged schedule reports the second pass as matched and writes nothing. That is
    what makes it safe to expose as an operation somebody can repeat when they are not
    sure whether the first one took.

    A project with no active source version gets a 404 naming that, not a 500: there is
    nothing to map, and the request was well formed.
    """
    scope = await _resource_scope(projectId, request, "finance.edit")
    service = _mpp_mapping_service(request)
    organization = str(scope.organization_id)
    version = await service.current_version_id(organization, projectId)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail="this project has no ready MPP source version to map")
    return await service.map_source_version(organization, projectId, version,
                                            actor_user_id=scope.actor_user_id)
