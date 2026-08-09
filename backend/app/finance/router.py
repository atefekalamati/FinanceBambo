"""Finance API composition root.

Feature endpoints are intentionally added only in their approved delivery stage.
"""

from fastapi import APIRouter, Request, UploadFile, File, Form
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
from .schemas.prices import PriceCreate, PriceResponse
from .schemas.conversions import ConversionCreate,ConversionPatch,ConversionResponse
from .schemas.progress import ProgressFeedResponse,ProgressOverrideCreate,ProgressOverrideResponse,ProgressSnapshotResponse
from .schemas.imports import ImportCommit,ImportCommitResponse,ImportPreviewResponse
from .schemas.invoices import InvoiceCreate,InvoicePatch,InvoiceConfirm,InvoiceResponse
from datetime import date

router = APIRouter(prefix="/projects/{projectId}/finance", tags=["finance"])


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

@router.get("/invoices",response_model=list[InvoiceResponse])
async def invoices(projectId:str,request:Request):
    scope=await _resource_scope(projectId,request,"finance.view");return [InvoiceResponse.from_domain(x) for x in await request.app.state.invoice_service.list(scope)]
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
