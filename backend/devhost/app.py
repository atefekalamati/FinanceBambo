"""Development composition root: the part the BAMBO host owns in production.

DEVELOPMENT ONLY. This wires a real PostgreSQL connection into the finance module and
serves the frontend from the same origin, so the browser runs against live data instead
of its mock adapters. It grants every finance permission to one static operator; it is
not an authentication system and must never be deployed.

Two things make the browser leave mock mode:
  * the frontend reads window.__BAMBO_FINANCE_CONTEXT__ to decide host vs standalone,
    so index.html is served with that object injected ahead of the module script;
  * api-client.js refuses cross-origin calls, so the API and the static files must be
    served by one process on one port.
"""

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.main import create_app
from app.finance.repositories.attachments import PsycopgAttachmentRepository
from app.finance.repositories.audit import PsycopgFinanceAuditRepository
from app.finance.repositories.conversions import PsycopgUnitConversionRepository
from app.finance.repositories.extractions import PsycopgExtractionRepository
from app.finance.repositories.imports import PsycopgFinanceImportRepository
from app.finance.repositories.invoices import PsycopgInvoiceRepository
from app.finance.repositories.prices import PsycopgFinancePriceRepository
from app.finance.repositories.progress import PsycopgProgressRepository
from app.finance.repositories.reports import PsycopgLiveReportRepository
from app.finance.repositories.resources import PsycopgFinanceResourcesRepository
from app.finance.repositories.settings import PsycopgFinanceSettingsRepository
from app.finance.services.attachments import FinanceAttachmentService
from app.finance.services.audit import FinanceAuditService
from app.finance.services.conversions import UnitConversionService
from app.finance.services.extractions import FinanceExtractionService
from app.finance.services.imports import FinanceImportService
from app.finance.services.invoices import FinanceInvoiceService
from app.finance.services.prices import FinancePriceService
from app.finance.services.progress import ProgressService
from app.finance.services.reports import FinanceLiveReportService
from app.finance.services.resources import FinanceResourcesService
from app.finance.services.settings import FinanceSettingsService

from . import database, seed
from .connection import ReconnectingConnection
from .ports import (ContextPermissionAuthorizer, LocalFileStorage, SeededActivityProvider,
                    SeededProgressSnapshotProvider, SingleTenantScopeAuthorizer,
                    StaticAuthContextProvider, UnavailableExtractor)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"


def host_context() -> dict:
    """The object the BAMBO shell normally injects before the finance module boots."""
    return {
        "userId": str(seed.ACTOR_ID),
        "organizationId": str(seed.ORGANIZATION_ID),
        "organizationName": "گروه ساختمانی بامبو",
        "projectId": seed.PROJECT_ID,
        "projectName": "پروژه مسکونی نمونه",
        "projectCode": "BMB-1405-01",
        "grossBuiltArea": str(seed.GROSS_BUILT_AREA),
        "permissionCodes": list(StaticAuthContextProvider(
            seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.ACTOR_ID).context.permission_codes),
        "locale": "fa-IR",
        "timezone": "Asia/Tehran",
    }


def wire(application: FastAPI, connection, storage_root: Path) -> None:
    """Populate application.state exactly as INTEGRATION_GUIDE_FA.md requires."""
    auth = StaticAuthContextProvider(seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.ACTOR_ID)
    application.state.auth_context_provider = auth
    application.state.scope_authorizer = SingleTenantScopeAuthorizer(
        seed.ORGANIZATION_ID, seed.PROJECT_ID)
    application.state.permission_authorizer = ContextPermissionAuthorizer()

    storage = LocalFileStorage(storage_root)
    progress_provider = SeededProgressSnapshotProvider(
        seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.PROGRESS_SNAPSHOTS, seed.IMPORTER_ID)
    activity_provider = SeededActivityProvider(seed.ACTIVITIES)

    invoice_service = FinanceInvoiceService(PsycopgInvoiceRepository(connection))
    application.state.finance_settings_service = FinanceSettingsService(
        PsycopgFinanceSettingsRepository(connection))
    application.state.finance_resources_service = FinanceResourcesService(
        PsycopgFinanceResourcesRepository(connection), activity_provider=activity_provider)
    application.state.finance_price_service = FinancePriceService(
        PsycopgFinancePriceRepository(connection))
    application.state.unit_conversion_service = UnitConversionService(
        PsycopgUnitConversionRepository(connection))
    application.state.progress_service = ProgressService(
        PsycopgProgressRepository(connection), progress_provider)
    application.state.finance_import_service = FinanceImportService(
        PsycopgFinanceImportRepository(connection))
    application.state.invoice_service = invoice_service
    application.state.finance_attachment_service = FinanceAttachmentService(
        PsycopgAttachmentRepository(connection), storage)
    application.state.finance_extraction_service = FinanceExtractionService(
        PsycopgExtractionRepository(connection), PsycopgAttachmentRepository(connection), storage,
        UnavailableExtractor("dev-image-extractor"), UnavailableExtractor("dev-voice-extractor"),
        invoice_service=invoice_service)
    application.state.finance_live_report_service = FinanceLiveReportService(
        PsycopgLiveReportRepository(connection), progress_provider)
    application.state.finance_audit_service = FinanceAuditService(
        PsycopgFinanceAuditRepository(connection))


def build(dsn: str, storage_root: Path, reseed: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Repositories keep whatever they are handed, so they get a handle that can
        # reopen itself when the development database restarts underneath the process.
        connection = ReconnectingConnection(dsn)
        await connection.live()
        await database.apply_migrations(connection)
        if reseed or not await database.is_seeded(connection):
            await database.reset(connection)
            await database.load_seed(connection)
        wire(application, connection, storage_root)
        try:
            yield
        finally:
            await connection.close()

    application = create_app()
    application.router.lifespan_context = lifespan
    # One psycopg connection is not safe for concurrent use, so requests are serialised.
    # A deployed host uses a pool instead; this keeps the dev host honest and simple.
    gate = asyncio.Lock()

    @application.middleware("http")
    async def one_request_at_a_time(request: Request, call_next):
        async with gate:
            return await call_next(request)

    @application.get("/", response_class=HTMLResponse)
    @application.get("/index.html", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        injection = (
            "<script>window.__BAMBO_FINANCE_CONTEXT__="
            f"{json.dumps(host_context(), ensure_ascii=False)};</script>"
        )
        # Must land before bootstrap.js, which reads the global while it is still loading.
        html = re.sub(r'(<script type="module")', injection + r"\n  \1", html, count=1)
        return HTMLResponse(html)

    application.mount("/src", StaticFiles(directory=FRONTEND_ROOT / "src"), name="src")
    public = FRONTEND_ROOT / "public"
    if public.is_dir():
        application.mount("/public", StaticFiles(directory=public), name="public")
    return application
