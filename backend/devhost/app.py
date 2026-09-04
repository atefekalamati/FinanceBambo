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

from uuid import UUID, uuid4

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

from coreint.activities import CoreProjectActivityProvider
from coreint.progress import CoreProgressSnapshotProvider
from coreint.security import (CoreAuthContextAssembler, CoreRbacPermissionAuthorizer,
                              CoreScopeAuthorizer)

from . import database, seed
from .connection import ReconnectingConnection
from .environment import (SELF_HOSTED_EXTRACTION, app_env, core_identity_settings,
                          core_progress_enabled, core_url, extraction_provider,
                          migration_url, mpp_import_enabled, mpp_import_interval_minutes,
                          mpp_import_root, mpp_java_home, mpp_max_file_size_mb,
                          seeding_allowed)
from .ports import (ContextPermissionAuthorizer, LocalFileStorage, SeededActivityProvider,
                    SeededProgressSnapshotProvider, SingleTenantScopeAuthorizer,
                    StaticAuthContextProvider, UnavailableExtractor)

#: Unique per process, so a page load after a restart cannot reuse a cached entry
#: point. Not a content hash: the point is to differ from whatever came before,
#: including a different application that used this same path.
BUILD_TOKEN = uuid4().hex[:12]

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"


def host_context(context=None) -> dict:
    """The object the BAMBO shell normally injects before the finance module boots.

    `permissionCodes` comes from the same `AuthContext` the API gates on, whenever one can
    be assembled. That matters more than it looks: the reports page hides the issue button
    unless the context claims `finance_report.issue`, and Core has no such permission. With
    a hardcoded list the browser would offer the button and the API would then refuse it --
    the UI promising something the server has already decided against, which is the worst
    of both answers.

    The static list is the fallback for a host with no Core database wired, which is the
    configuration those permissions were written for.
    """
    fallback = StaticAuthContextProvider(
        seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.ACTOR_ID).context
    context = context or fallback
    return {
        "userId": str(context.user_id),
        "organizationId": str(context.organization_id),
        "organizationName": "گروه ساختمانی بامبو",
        "projectId": context.project_id,
        "projectName": "پروژه مسکونی نمونه",
        "projectCode": "BMB-1405-01",
        "grossBuiltArea": str(seed.GROSS_BUILT_AREA),
        "permissionCodes": list(context.permission_codes),
        "organizationRole": context.organization_role,
        "locale": "fa-IR",
        "timezone": "Asia/Tehran",
    }


#: Which demo user the browser is acting as. DEVELOPMENT HOST ONLY.
#:
#: The dev host has never authenticated anybody -- it has always trusted a static context --
#: so this changes nothing about its security posture. What it adds is the ability to show
#: the Core authorization rules working: switch to the restricted user and watch a role
#: grant lose to a personal denial, or to the outsider and watch an `org_chief` role in
#: another organization grant nothing here.
#:
#: A real host reads identity from its session and would never accept it from a header.
DEMO_USER_HEADER = "X-Demo-User"

#: Which MSP field this host reads an activity code from, for BOTH Core adapters.
#:
#: `coreint.ACTIVITY_CODE_FIELDS` defaults to `("text1", "outline_number", "wbs")` and its
#: own docstring calls the first entry a guess: an activity code in Text1 is a planning
#: convention, not a schema fact. The guess reasons that being wrong "shows up as unmapped
#: lines, which is visible, rather than as wrong pairings, which would not be" -- and that
#: holds only while Text1 is empty.
#:
#: Measured against a real BAMBO schedule (`Sources/زمان بندی پل.mpp`, 328 tasks), Text1 is
#: filled on every single task with a Jalali status date such as `1404/5/18`. The default
#: order therefore resolves each activity code to a DATE: 128 distinct "codes", the worst
#: shared by 27 assignments. Reading the structure instead gives 266 codes with a worst case
#: of 7. Pairing an estimate line to a status date is not a near miss -- every task sharing
#: that date becomes one activity, and a correction meant for one line reaches all of them.
#:
#: The library default is deliberately left alone: a host whose planners really do write
#: codes in Text1 still needs it, and this is a deployment decision, not a library one. The
#: constructors already take the argument, which is what makes this a wiring change.
#:
#: BOTH adapters must be given the same value. `CoreProjectActivityProvider` keys its
#: activities by the same rule, so rewiring one and not the other would offer estimate lines
#: activity codes the progress feed never emits -- worse than leaving both alone.
ACTIVITY_CODE_FIELDS = ("outline_number", "wbs")


def extraction_providers():
    """The image and voice extractors, and the switch that decides which.

    The default stays `UnavailableExtractor`, which refuses. That is not caution for its own
    sake: an extractor that quietly returns nothing would let a reviewer confirm an invoice
    from an empty draft, so the absent provider says so and the request fails. Turning the
    real models on is an explicit act.

        EXTRACTION_PROVIDER=self_hosted

    The models are imported INSIDE the branch. `extraction.providers` pulls in paddle and
    torch -- several gigabytes and tens of seconds -- and a host that never extracts must
    neither pay for that nor require the packages to be installed at all.

    A failure to import is not swallowed. A host told to use the self-hosted providers and
    unable to load them has a configuration fault, and starting anyway with the refusing
    stand-in would hide it behind a message about the provider being unconfigured.
    """
    if extraction_provider() != SELF_HOSTED_EXTRACTION:
        return (UnavailableExtractor("dev-image-extractor"),
                UnavailableExtractor("dev-voice-extractor"))
    from extraction.adapters import ImageExtractionAdapter, VoiceExtractionAdapter
    print("self-hosted extraction ENABLED: OCR and speech run locally on this machine")
    return ImageExtractionAdapter(), VoiceExtractionAdapter()


def core_identity(default_user, organization_id, project_id):
    """The seam where the host says *who* is calling. See CoreAuthContextAssembler.

    Everything about that identity -- membership, roles, permissions -- is read from Core.
    This only answers the one question Core cannot: which person the request belongs to.
    """
    async def identity(request):
        header = (request.headers.get(DEMO_USER_HEADER) or "").strip() if request else ""
        try:
            user_id = UUID(header) if header else default_user
        except ValueError:
            user_id = default_user
        return user_id, organization_id, project_id
    return identity


def wire(application: FastAPI, connection, storage_root: Path, core=None) -> None:
    """Populate application.state exactly as INTEGRATION_GUIDE_FA.md requires.

    With `core` set, the three security ports and the two schedule ports are backed by the
    real Core tables instead of fixtures. The eleven finance services below are unchanged
    either way -- which is the point of the port boundary, and worth seeing in one function.
    """
    if core is None:
        auth = StaticAuthContextProvider(seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.ACTOR_ID)
        application.state.auth_context_provider = auth
        application.state.scope_authorizer = SingleTenantScopeAuthorizer(
            seed.ORGANIZATION_ID, seed.PROJECT_ID)
        application.state.permission_authorizer = ContextPermissionAuthorizer()
        progress_provider = SeededProgressSnapshotProvider(
            seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.PROGRESS_SNAPSHOTS, seed.IMPORTER_ID)
        activity_provider = SeededActivityProvider(seed.ACTIVITIES)
    else:
        # Against a real Core database the fixture identifiers name nobody, so Core refuses
        # them -- correctly, and in a way that reads as a permission problem rather than the
        # configuration one it is. These three settings say who the host stands in for; they
        # grant nothing, and every gate below still asks Core about whoever is named.
        actor, organization, project = core_identity_settings()
        application.state.auth_context_provider = CoreAuthContextAssembler(
            core, core_identity(actor or seed.ACTOR_ID,
                                organization or seed.ORGANIZATION_ID,
                                project or seed.PROJECT_ID))
        application.state.scope_authorizer = CoreScopeAuthorizer(core)
        application.state.permission_authorizer = CoreRbacPermissionAuthorizer(core)
        # Progress is the one port Core cannot fill on its own -- see
        # `environment.core_progress_enabled` and `coreint/progress.py`. The seeded feed
        # stands in for the host's progress module, which is where assignment-level
        # quantities actually come from in production.
        #
        # Both adapters are given ACTIVITY_CODE_FIELDS from one constant rather than two
        # literals: the two must agree, and two literals are how they stop agreeing.
        progress_provider = (
            CoreProgressSnapshotProvider(core, activity_code_fields=ACTIVITY_CODE_FIELDS)
            if core_progress_enabled()
            else SeededProgressSnapshotProvider(seed.ORGANIZATION_ID, seed.PROJECT_ID,
                                                seed.PROGRESS_SNAPSHOTS, seed.IMPORTER_ID))
        activity_provider = CoreProjectActivityProvider(
            core, activity_code_fields=ACTIVITY_CODE_FIELDS)

    storage = LocalFileStorage(storage_root)

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
    image_extractor, voice_extractor = extraction_providers()
    application.state.finance_extraction_service = FinanceExtractionService(
        PsycopgExtractionRepository(connection), PsycopgAttachmentRepository(connection), storage,
        image_extractor, voice_extractor,
        invoice_service=invoice_service)
    application.state.finance_live_report_service = FinanceLiveReportService(
        PsycopgLiveReportRepository(connection), progress_provider,
        # The WBS rollup reads its stages from the activity catalogue. Same provider the
        # resource service already holds, so both see one plan rather than two.
        activity_provider=activity_provider)
    application.state.finance_audit_service = FinanceAuditService(
        PsycopgFinanceAuditRepository(connection))


def build(dsn: str, storage_root: Path, reseed: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Startup does NOT migrate. Launching a process is not consent to alter a schema,
        # and a configured FINANCE_MIGRATION_DSN is a credential, not an instruction. Apply
        # migrations deliberately instead:
        #
        #     cd backend && alembic upgrade head
        #
        # If the schema is absent, is_seeded below says so plainly rather than repairing it.
        admin_dsn = migration_url()
        if admin_dsn and not seeding_allowed():
            # A deployed environment never gets the demo project, and there is nothing else
            # for the owner role to do here, so it is not connected at all.
            print(f"development seed DISABLED (APP_ENV={app_env()})")
        elif admin_dsn:
            admin = ReconnectingConnection(admin_dsn)
            try:
                # The query is skipped when reseeding, because the answer cannot change what
                # happens next.
                already_seeded = False if reseed else await database.is_seeded(admin)
                reset_first, load = database.seed_plan(
                    allowed=True, reseed=reseed, already_seeded=already_seeded)
                if reset_first:
                    await database.reset(admin)
                if load:
                    await database.load_seed(admin)
            finally:
                await admin.close()

        # Repositories keep whatever they are handed, so they get a handle that can
        # reopen itself when the development database restarts underneath the process.
        connection = ReconnectingConnection(dsn)
        await connection.live()

        # A second handle, because Core may be a different database entirely. In the
        # integration demo it is the same one, and opening it separately keeps that a
        # deployment detail rather than an assumption baked into the wiring.
        core_dsn = core_url()
        core = ReconnectingConnection(core_dsn) if core_dsn else None
        if core is not None:
            await core.live()
            print("core integration ENABLED: membership, roles and permissions come from Core")

        wire(application, connection, storage_root, core)

        # ------------------------------------------------------------------ MPP import
        # Core-host duty, so it lives here and not in app/finance. The service opens its
        # OWN connections: the request path serialises the shared handle behind a lock,
        # and an import transaction held there would stall the host for a whole parse.
        periodic = None
        root = mpp_import_root()
        if root:
            import psycopg as _psycopg
            from psycopg.rows import dict_row as _dict_row
            from coreint.mpp_import import MppImportService
            from coreint.mpp_reader import MpxjMppReader

            def _mpp_connection():
                return _psycopg.AsyncConnection.connect(
                    dsn, autocommit=True, row_factory=_dict_row)

            application.state.mpp_import_service = MppImportService(
                _mpp_connection, MpxjMppReader(java_home=mpp_java_home()),
                import_root=root, max_size_mb=mpp_max_file_size_mb())
            print("mpp import CONFIGURED: root is set; POST /api/projects/{id}/mpp-imports")

            if mpp_import_enabled():
                interval = mpp_import_interval_minutes() * 60

                async def _periodic():
                    service = application.state.mpp_import_service
                    while True:
                        await asyncio.sleep(interval)
                        try:
                            outcomes = await service.periodic_tick()
                            if outcomes:
                                print("mpp periodic import:",
                                      [(o.get("projectId"), o.get("status"))
                                       for o in outcomes])
                        except Exception as error:  # noqa: BLE001 -- the loop must survive
                            print("mpp periodic import failed:", error)

                periodic = asyncio.create_task(_periodic())
                print(f"mpp periodic import ENABLED every {interval // 60} minutes")
        try:
            yield
        finally:
            if periodic is not None:
                periodic.cancel()
                # Await the cancellation: an in-flight import gets to unwind its
                # transaction before the connections underneath it are closed.
                try:
                    await periodic
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            await connection.close()
            if core is not None:
                await core.close()

    application = create_app()
    application.router.lifespan_context = lifespan
    # One psycopg connection is not safe for concurrent use, so requests are serialised.
    # A deployed host uses a pool instead; this keeps the dev host honest and simple.
    gate = asyncio.Lock()

    @application.middleware("http")
    async def one_request_at_a_time(request: Request, call_next):
        async with gate:
            response = await call_next(request)
        # Nothing this host serves may be cached by the browser.
        #
        # StaticFiles sends an ETag and Last-Modified, so a browser revalidates and, on a
        # 304, re-runs whatever copy it already had. That is right for a CDN and wrong for
        # source files that change every time someone edits them.
        #
        # The failure it produces is a bad one to debug: the server sends the correct bytes,
        # the browser never asks for them, and the page renders from a stale module whose
        # imports no longer exist. Nothing in the server log says anything is wrong except a
        # 304 and a scatter of 404s for files this repository has never contained.
        #
        # `no-store` rather than `no-cache`: no-cache still stores the response and
        # revalidates, which is the behaviour that produces the 304 in the first place.
        response.headers["Cache-Control"] = "no-store"
        if request.url.path.startswith("/api/"):
            # So a developer can tell a real answer from a mock one in the network panel.
            # Development host only; the deployed module sets no such header.
            response.headers["X-Finance-Data-Source"] = "postgresql"
            response.headers["X-Finance-Environment"] = app_env()
        return response

    # ----------------------------------------------------------------- MPP import API
    # Registered on the HOST application, not the finance router: importing a schedule is
    # a Core-host duty, and app/finance must stay ignorant of files and parsers. The
    # permissions are Core's own msp.* codes, resolved through the same ports every other
    # request goes through.
    _IMPORT_STATUS = {
        "MPP_FILE_NOT_FOUND": 404,
        "MPP_PATH_NOT_ALLOWED": 422,
        "MPP_FILE_TOO_LARGE": 413,
        "MPP_FILE_EMPTY": 422,
        "MPP_FILE_CORRUPTED": 422,
        "MPP_FORMAT_UNSUPPORTED": 422,
        "MPP_PARSE_FAILED": 422,
        "MPXJ_NOT_AVAILABLE": 503,
        "JAVA_RUNTIME_NOT_AVAILABLE": 503,
        "MPP_IMPORT_ALREADY_RUNNING": 409,
        "MPP_DUPLICATE_FILE": 409,
        "MPP_IMPORT_REFUSED": 403,
    }

    async def _mpp_guard(request: Request, project_id: str, permission: str):
        state = request.app.state
        context = await state.auth_context_provider.current(request)
        await state.scope_authorizer.require_project(
            context, context.organization_id, project_id)
        await state.permission_authorizer.require(context, permission)
        return context

    def _mpp_service(request: Request):
        service = getattr(request.app.state, "mpp_import_service", None)
        if service is None:
            from fastapi import HTTPException
            raise HTTPException(503, "MPP import is not configured on this host "
                                     "(set MPP_IMPORT_ROOT)")
        return service

    @application.post("/api/projects/{projectId}/mpp-imports", status_code=201)
    async def run_mpp_import(projectId: str, request: Request):
        from fastapi.responses import JSONResponse
        from coreint.mpp_import import MppImportRefused
        context = await _mpp_guard(request, projectId, "msp.upload")
        service = _mpp_service(request)
        body = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 -- an empty body means "the configured file"
            pass
        if not isinstance(body, dict):
            body = {}          # a JSON scalar/array is not a request, it is an accident
        # The service accepts exactly the project's own file, `<projectId>.mpp`; a body
        # naming anything else is refused before the filesystem is consulted.
        file_name = str(body.get("fileName") or f"{projectId}.mpp")
        try:
            # organization_id comes from the authenticated context, never from the body.
            return await service.run_import(str(context.organization_id), projectId,
                                            file_name,
                                            actor_user_id=context.user_id)
        except MppImportRefused as refused:
            return JSONResponse(status_code=_IMPORT_STATUS.get(refused.code, 422),
                                content={"error": {"code": refused.code,
                                                   "message": str(refused)}})

    @application.get("/api/projects/{projectId}/mpp-imports/latest")
    async def latest_mpp_import(projectId: str, request: Request):
        from fastapi import HTTPException
        await _mpp_guard(request, projectId, "msp.view")
        service = _mpp_service(request)
        for result in reversed(list(service.recent.values())):
            if result.get("projectId") == projectId:
                return result
        raise HTTPException(404, "no import has run for this project in this process")

    @application.get("/api/projects/{projectId}/mpp-imports/{importId}")
    async def get_mpp_import(projectId: str, importId: str, request: Request):
        from fastapi import HTTPException
        await _mpp_guard(request, projectId, "msp.view")
        service = _mpp_service(request)
        result = service.recent.get(importId)
        if result is None or result.get("projectId") != projectId:
            raise HTTPException(404, "unknown import id")
        return result

    @application.get("/", response_class=HTMLResponse)
    @application.get("/index.html", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        # Ask the wired provider rather than assuming. A failure here must not stop the
        # page loading -- the API is still the authority on every request -- so the static
        # context stands in and the browser simply sees the development defaults.
        try:
            context = await application.state.auth_context_provider.current(request)
        except Exception:
            context = None
        injection = (
            "<script>window.__BAMBO_FINANCE_CONTEXT__="
            f"{json.dumps(host_context(context), ensure_ascii=False)};</script>"
        )
        # Must land before bootstrap.js, which reads the global while it is still loading.
        html = re.sub(r'(<script type="module")', injection + r"\n  \1", html, count=1)
        # Give the entry point a URL unique to this process.
        #
        # `no-store` stops the browser caching what we serve from now on, but it cannot undo
        # what is already stored: StaticFiles sends Last-Modified and no max-age, so a
        # browser is free to reuse an existing copy for a heuristic fraction of its age
        # without asking us at all. A stale entry point therefore survives the header fix and
        # keeps running until the cache expires on its own.
        #
        # A per-process query defeats that: nothing is stored under a URL never seen before.
        # Only the entry point needs it -- once the right bootstrap runs, every module it
        # imports is fetched under this same fresh page load.
        html = html.replace('src="./src/app/bootstrap.js"',
                            f'src="./src/app/bootstrap.js?build={BUILD_TOKEN}"')
        return HTMLResponse(html)

    application.mount("/src", StaticFiles(directory=FRONTEND_ROOT / "src"), name="src")
    public = FRONTEND_ROOT / "public"
    if public.is_dir():
        application.mount("/public", StaticFiles(directory=public), name="public")
    return application
