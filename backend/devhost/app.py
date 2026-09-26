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

import os
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
from app.finance.repositories.items_and_estimates import (
    PsycopgItemsAndEstimatesRepository)
from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
from app.finance.repositories.item_price_mappings import PsycopgItemPriceMappingRepository
from app.finance.repositories.item_price_components import PsycopgItemPriceComponentRepository
from app.finance.repositories.unit_conversion_rules import PsycopgUnitConversionRuleRepository
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
from app.finance.services.items_and_estimates import ItemsAndEstimatesService
from app.finance.services.material_price_import import MaterialPriceImportService
from app.finance.services.material_prices import MaterialPriceService
from app.finance.services.item_price_mappings import ItemPriceMappingService
from app.finance.services.item_price_components import ItemPriceComponentService
from app.finance.services.unit_conversion_rules import UnitConversionRuleService
from app.finance.services.extractions import FinanceExtractionService
from app.finance.services.imports import FinanceImportService
from app.finance.services.invoices import FinanceInvoiceService
from app.finance.services.prices import FinancePriceService
from app.finance.services.progress import ProgressService
from app.finance.services.reports import FinanceLiveReportService
from app.finance.services.resources import FinanceResourcesService
from app.finance.services.settings import FinanceSettingsService

from coreint.activities import CoreProjectActivityProvider
from coreint.finance_activities import FinanceRowsActivityProvider
from coreint.finance_mpp_mapping import FinanceMppMappingService
from coreint.finance_mpp_sync import FinanceMppSyncService
from coreint.finance_progress import FinanceRowsProgressProvider
from coreint.identity import CoreActorDirectory
from coreint.mpp_reader import MpxjMppReader
from coreint.progress import CoreProgressSnapshotProvider
from coreint.security import (CoreAuthContextAssembler, CoreRbacPermissionAuthorizer,
                              CoreScopeAuthorizer)

from . import database, seed
from .connection import ReconnectingConnection
from .environment import (SELF_HOSTED_EXTRACTION, SEED_OPT_IN, app_env,
                          core_identity_settings, core_progress_enabled, core_url,
                          dsn_target, extraction_provider, migration_url,
                          mpp_import_enabled, mpp_import_interval_minutes,
                          MATERIAL_PRICE_SHEET_SETTING, material_price_sheet_url,
                          material_price_import_enabled,
                          material_price_import_interval_minutes,
                          mpp_import_root, mpp_java_home, mpp_max_file_size_mb,
                          seed_refusal, seeding_allowed)
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
    return ImageExtractionAdapter(), VoiceExtractionAdapter(*speech_provider())


def speech_provider():
    """`(provider, adapter_name)` for the voice adapter, chosen by configuration.

    `FINANCE_STT_PROVIDER=avalai` sends transcription to the hosted endpoint; anything
    else, including nothing at all, keeps the local Whisper that was here before. The
    default is deliberately the old behaviour: a host that upgrades and changes no setting
    transcribes exactly as it did yesterday.

    Returns `()` for the local case rather than constructing the provider, because
    `WhisperProvider` loads a model and the adapter already defers that until the first
    request. Constructing it here would pay for the model on every startup, including on
    hosts that never receive a voice file.
    """
    if (os.environ.get("FINANCE_STT_PROVIDER") or "").strip().lower() != "avalai":
        return ()
    from extraction.providers.avalai_speech import AvalAISpeechProvider
    provider = AvalAISpeechProvider()
    # The MODEL is printed because an operator needs to know which one ran. The key is
    # reported as present or absent and its value is never read into a log.
    print("speech provider: avalai/%s  (AVALAI_API_KEY: %s)"
          % (provider.model, "PRESENT" if provider.configured else "MISSING"))
    return provider, "avalai-speech"


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


class FirstAvailableProgressProvider:
    """Ask each source in turn; the first that has the snapshot answers.

    Composition, not dependency. The FILE is asked first because it is the source of
    truth for what the schedule says now. Core is asked second and only if the host
    wired it, so a report issued months ago against a snapshot whose file has since been
    replaced still resolves. A Finance-only deployment has one source in this list and
    behaves exactly as if this class were not here.
    """

    def __init__(self, sources):
        self._sources = [source for source in sources if source is not None]

    async def current_snapshot(self, organization_id, project_id, as_of=None):
        for source in self._sources:
            try:
                found = await source.current_snapshot(organization_id, project_id, as_of)
            except Exception:                                  # noqa: BLE001
                # A source that cannot answer (no file staged, Core unreachable) must not
                # stop the next one; the LAST source's failure is still raised below.
                continue
            if found is not None:
                return found
        return None

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        for source in self._sources:
            try:
                found = await source.get_snapshot(organization_id, project_id, snapshot_id)
            except Exception:                                  # noqa: BLE001
                continue
            if found is not None:
                return found
        return None


def _progress_provider(finance=None, core=None):
    """Which adapter answers "how far along is this project?".

    The order encodes the architecture rather than a preference:

    1. FINANCE'S OWN ROWS, whenever a schedule root is configured. `finance_mpp_sync` has
       read the file into `finance_mpp_source_versions` / `finance_mpp_rows`, and a report
       reads those back -- persisted, reproducible, and needing no MSP table and no JVM
       at request time. The file provider is the sync engine, not the read path.
    2. Core's MSP tables, when the host asks for them (`FINANCE_CORE_PROGRESS`). Still the
       right answer for a snapshot pinned historically whose file is long gone.
    3. The fixtures, so a host with neither still starts and says so.

    `MPP_IMPORT_ROOT` is the one switch for the MPP feature on both sides: it is what the
    sync reads from, and its presence is what turns the Finance-owned read path on.
    """
    root = mpp_import_root()
    rows_source = (FinanceRowsProgressProvider(finance, activity_code_fields=ACTIVITY_CODE_FIELDS)
                   if root and finance is not None else None)
    core_source = (CoreProgressSnapshotProvider(core, activity_code_fields=ACTIVITY_CODE_FIELDS)
                   if core is not None and core_progress_enabled() else None)
    configured = [source for source in (rows_source, core_source) if source is not None]
    if len(configured) == 1:
        # One source needs no composition, and wrapping it would only hide which adapter
        # a host actually installed from anything inspecting the wiring.
        return configured[0]
    if configured:
        return FirstAvailableProgressProvider(configured)
    return SeededProgressSnapshotProvider(seed.ORGANIZATION_ID, seed.PROJECT_ID,
                                          seed.PROGRESS_SNAPSHOTS, seed.IMPORTER_ID)


def wire(application: FastAPI, connection, storage_root: Path, core=None) -> None:
    """Populate application.state exactly as INTEGRATION_GUIDE_FA.md requires.

    With `core` set, the three security ports and the two schedule ports are backed by the
    real Core tables instead of fixtures. The eleven finance services below are unchanged
    either way -- which is the point of the port boundary, and worth seeing in one function.
    """
    # Explicitly development-only. Production composition never enables this flag and must
    # provide a durable `finance_background_executor` before the async route returns 202.
    application.state.allow_ephemeral_finance_tasks = True
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
        progress_provider = _progress_provider(connection, core)
        # The activity catalogue follows the progress source. When Finance reads its own
        # rows, the stages come from those same rows -- otherwise `by_wbs` would be the
        # one report still needing msp_tasks, and a Finance-only deployment could compute
        # every figure except the one broken down by stage.
        activity_provider = (FinanceRowsActivityProvider(connection)
                             if mpp_import_root()
                             else CoreProjectActivityProvider(
                                 core, activity_code_fields=ACTIVITY_CODE_FIELDS))

    # Names for the actor ids every finance record stores. Core's `users` lives on the same
    # database as Finance, so this reads whichever connection this host actually has -- and
    # when that database has no `users` at all, the adapter says so once and every actor
    # renders as the id it always did. Nothing is copied into a Finance table either way.
    application.state.actor_directory = CoreActorDirectory(core if core is not None else connection)

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
    # Material prices read from the database only. The import that fills those tables
    # is a server-side job; no request path here reaches Google Sheets, and the unit
    # conversion repository is handed over so one conversion boundary answers both
    # the existing unit registry and a converted material price.
    # The one production writer of `price_observations`, now reachable over HTTP as well
    # as from the CLI. Wired ONLY when a sheet is configured: an endpoint that exists but
    # has nothing to read from would answer 409 forever, and a host that cannot import
    # should say so at startup rather than once per request.
    sheet_link = material_price_sheet_url()
    if sheet_link:
        application.state.material_price_import_service = MaterialPriceImportService(
            PsycopgMaterialPriceRepository(connection), sheet_link=sheet_link,
            interval_minutes=material_price_import_interval_minutes())
        print("material price import ENABLED -- sheet configured")
    else:
        print("material price import DISABLED -- %s is not set"
              % MATERIAL_PRICE_SHEET_SETTING)

    # Items and Estimates reads the schedule that is authoritative for what exists.
    application.state.items_and_estimates_service = ItemsAndEstimatesService(
        PsycopgItemsAndEstimatesRepository(connection))
    application.state.material_price_service = MaterialPriceService(
        PsycopgMaterialPriceRepository(connection),
        conversion_repository=PsycopgUnitConversionRepository(connection))
    # The bridge between the two modules: which market listing prices which schedule item.
    # It reads both sides and writes only its own table -- nothing here can change a
    # material price or a schedule row.
    _conversion_rules = UnitConversionRuleService(
        PsycopgUnitConversionRuleRepository(connection))
    application.state.item_price_mapping_service = ItemPriceMappingService(
        PsycopgItemPriceMappingRepository(connection),
        conversion_rules=_conversion_rules)
    # An activity is not a material: «کانال‌کنی» consumes rebar and pipe and brick that the
    # schedule never names. This prices one line from a LIST of materials somebody entered,
    # and it too writes only its own table.
    application.state.item_price_component_service = ItemPriceComponentService(
        PsycopgItemPriceComponentRepository(connection),
        # The rule ladder, behind each listing's own measurement. Without it a crossing
        # nobody measured for THIS product ends at «ضریب تبدیل لازم است» even where an
        # approved project rule says exactly how to cross the two units.
        conversion_rules=_conversion_rules)
    # What a price per branch means on a line measured in kilograms -- and, when nobody
    # has said, the record of the question. Writes only its own two tables.
    application.state.unit_conversion_rule_service = _conversion_rules
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


async def publish_readiness(application, connection):
    """Run the production composition over what `wire` just built.

    WHY THIS WAS MISSING AND WHY IT MATTERS

    `/healthz/finance` reads `app.state.finance_availability`, which only
    `configure_finance` sets. Nothing outside the tests ever called it, so the development
    host answered 503 FINANCE_NOT_CONFIGURED for its entire life -- while serving every
    Finance endpoint perfectly. The readiness answer was not wrong, it was UNASKED: the
    host set each service on `app.state` by hand and never performed the composition step
    that checks the graph is complete and says so.

    That is worth fixing rather than bypassing, because the check earns its keep. It is the
    same function the real host calls, so a component this file forgets to build is
    reported here by name instead of surfacing later as an AttributeError on one endpoint.
    `dedicated=False`: a development host that cannot reach its database should still start
    and say why, rather than refusing to boot.

    The probe is the module's own, pointed at the revision the code expects. A database at
    a different revision is a real reason to report not-ready.
    """
    from app.finance.integration import (PsycopgFinanceReadinessProbe, REQUIRED_COMPONENTS,
                                         OPTIONAL_COMPONENTS, configure_finance)

    components = {name: getattr(application.state, name, None)
                  for name in REQUIRED_COMPONENTS + OPTIONAL_COMPONENTS}
    return await configure_finance(
        application, components,
        PsycopgFinanceReadinessProbe(connection, expected_revision()),
        dedicated=False,
        # Named, never the underlying error: the reason is operator-only and the code is
        # what a reader needs.
        operator_notice=lambda code, detail: print(
            "  finance readiness: %s (%s)" % (code, detail)))


def expected_revision():
    """The Alembic revision this code was written against.

    Read from the migration directory rather than pinned in a constant, so adding a
    revision does not leave the readiness probe asserting yesterday's schema. The highest
    numbered file IS the head in this project: the chain is linear and
    `test_migrations` holds it that way.
    """
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    revisions = sorted(path.stem.split("_", 1)[0] for path in versions.glob("[0-9]*.py"))
    return revisions[-1] if revisions else ""


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
            #
            # The reason is printed, not just the verdict: this line used to read
            # "seed DISABLED (APP_ENV=development)", which names the one condition that
            # had PASSED and sends the reader to change the setting that was already right.
            print(f"development seed DISABLED -- {seed_refusal()}")
        elif admin_dsn:
            # Loud, and by name. Fixture rows are about to be written, and `--reseed`
            # DELETEs from sixteen Finance tables first with the immutability triggers
            # turned off. Whoever reads this log gets to see which database that lands in
            # before it lands, rather than inferring it from two environment variables.
            seed_host, seed_database = dsn_target(admin_dsn)
            print("development seed ENABLED -- writing fixture rows into "
                  f"{seed_database!r} on {seed_host or 'the configured host'} "
                  f"(APP_ENV={app_env()}, {SEED_OPT_IN}=yes"
                  + (", --reseed: existing rows for the demo project are deleted first"
                     if reseed else "") + ")")
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

        # The composition step the production host performs, run over what `wire` just
        # built. Without it `/healthz/finance` answers NOT_CONFIGURED forever, because
        # nothing else sets `finance_availability` -- see `publish_readiness`.
        readiness = await publish_readiness(application, connection)
        print("  finance readiness: %s" % readiness.code)

        # ------------------------------------------------------------------ MPP import
        # Core-host duty, so it lives here and not in app/finance. The service opens its
        # OWN connections: the request path serialises the shared handle behind a lock,
        # and an import transaction held there would stall the host for a whole parse.
        periodic = None
        price_periodic = None
        root = mpp_import_root()
        if root:
            import psycopg as _psycopg
            from psycopg.rows import dict_row as _dict_row
            from coreint.mpp_import import MppImportService

            def _mpp_connection():
                return _psycopg.AsyncConnection.connect(
                    dsn, autocommit=True, row_factory=_dict_row)

            reader = MpxjMppReader(java_home=mpp_java_home())
            application.state.mpp_import_service = MppImportService(
                _mpp_connection, reader,
                import_root=root, max_size_mb=mpp_max_file_size_mb())
            print("mpp import CONFIGURED: root is set; POST /api/projects/{id}/mpp-imports")
            # Turning those rows into financial records, and the one decision the file
            # cannot make: whether a WORK resource is labour or equipment.
            #
            # Built BEFORE the sync service so it can be handed to it. An import that is
            # not followed by a mapping leaves the schedule read but the estimate empty,
            # and the only thing that used to close that gap was a developer remembering
            # to call the mapper afterwards.
            application.state.finance_mpp_mapping_service = FinanceMppMappingService(
                _mpp_connection)
            # The Finance half of the same file, into Finance's own tables. Same reader,
            # same root, its own persistence: a Finance-only host runs this alone.
            application.state.finance_mpp_sync_service = FinanceMppSyncService(
                _mpp_connection, reader,
                import_root=root, max_size_mb=mpp_max_file_size_mb(),
                mapping_service=application.state.finance_mpp_mapping_service)
            print("finance mpp sync CONFIGURED; POST /api/projects/{id}/finance/mpp-sync")

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
                        try:
                            synced = await application.state.finance_mpp_sync_service.periodic_tick()
                            if synced:
                                print("finance mpp periodic sync:",
                                      [(o.get("projectId"), o.get("status")) for o in synced])
                        except Exception as error:  # noqa: BLE001 -- the loop must survive
                            print("finance mpp periodic sync failed:", error)

                periodic = asyncio.create_task(_periodic())
                print(f"mpp periodic import ENABLED every {interval // 60} minutes")

        # The daily price import, on its own loop. Separate from the MPP one because it
        # has its own interval, its own gate and its own failure mode: a schedule file
        # that will not parse must not stop the prices, and a sheet Google will not serve
        # must not stop the schedules.
        if material_price_import_enabled():
            price_service = getattr(application.state, "material_price_import_service", None)
            if price_service is None:
                print("material price periodic import NOT STARTED -- %s is not set"
                      % MATERIAL_PRICE_SHEET_SETTING)
            else:
                price_interval = material_price_import_interval_minutes()

                async def _price_periodic():
                    # One tick immediately, then every interval. A host restarted after a
                    # day of downtime should not wait another full day before catching up,
                    # and the due check is what keeps that from being an extra import: a
                    # project that already ran today is reported skipped and read nothing.
                    while True:
                        try:
                            outcomes = await price_service.periodic_tick(price_interval)
                            for outcome in outcomes:
                                print("material price import [%s] %s %s"
                                      % (outcome.get("projectId"), outcome.get("status"),
                                         {k: v for k, v in outcome.items()
                                          if k not in ("projectId", "status")}))
                        except Exception as error:  # noqa: BLE001 -- the loop must survive
                            print("material price periodic import failed:", error)
                        await asyncio.sleep(price_interval * 60)

                price_periodic = asyncio.create_task(_price_periodic())
                print("material price periodic import ENABLED every %d minutes"
                      % price_interval)
        try:
            yield
        finally:
            if price_periodic is not None:
                price_periodic.cancel()
                try:
                    await price_periodic
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
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

    @application.post("/api/projects/{projectId}/finance/mpp-sync", status_code=201)
    async def run_finance_mpp_sync(projectId: str, request: Request):
        """Read a schedule file into Finance's own tables. Idempotent.

        Finance's write permission, not MSP's: this touches only Finance-owned tables and
        must work on a host with no MSP module at all.

        The body may name a `fileName` INSIDE the configured root -- an operator stages a
        schedule under whatever name it arrived with, and the project it belongs to is a
        separate fact. Absent, the project's own `<projectId>.mpp` is read. Either way the
        path gate resolves the name against MPP_IMPORT_ROOT and refuses anything that
        escapes it, so the body chooses a file, never a directory.
        """
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse
        from coreint.finance_mpp_sync import FinanceMppSyncRefused
        context = await _mpp_guard(request, projectId, "finance.edit")
        service = getattr(request.app.state, "finance_mpp_sync_service", None)
        if service is None:
            raise HTTPException(503, "Finance MPP sync is not configured on this host "
                                     "(set MPP_IMPORT_ROOT)")
        body = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 -- an empty body means "the project's own file"
            pass
        if not isinstance(body, dict):
            body = {}          # a JSON scalar or array is not a request, it is an accident
        file_name = body.get("fileName") or None
        refresh = bool(body.get("refresh"))
        try:
            return await service.sync(str(context.organization_id), projectId,
                                      actor_user_id=context.user_id,
                                      refresh=refresh,
                                      file_name=str(file_name) if file_name else None)
        except FinanceMppSyncRefused as refused:
            return JSONResponse(status_code=_IMPORT_STATUS.get(refused.code, 422),
                                content={"error": {"code": refused.code,
                                                   "message": str(refused)}})

    def _mapping_service(request: Request):
        from fastapi import HTTPException
        service = getattr(request.app.state, "finance_mpp_mapping_service", None)
        if service is None:
            raise HTTPException(503, "Finance MPP mapping is not configured on this host "
                                     "(set MPP_IMPORT_ROOT)")
        return service

    @application.get("/api/projects/{projectId}/finance/mpp-work-resources")
    async def unclassified_work_resources(projectId: str, request: Request):
        """WORK resources nobody has decided about yet, commonest first.

        MS Project says only "WORK"; Finance separates labour from equipment. Nothing in
        the file distinguishes them, so this lists what is waiting on a person rather than
        letting anything guess. `fileUnit` is MS Project's `initials` -- usually the first
        letter of the name -- reported so a reader can see it is not a unit.
        """
        context = await _mpp_guard(request, projectId, "finance.view")
        return {"items": await _mapping_service(request).list_unclassified(
            str(context.organization_id), projectId)}

    @application.get("/api/projects/{projectId}/finance/mpp-mapping-status")
    async def mpp_mapping_status(projectId: str, request: Request):
        """What became of every row of the current schedule.

        Reads and counts; writes nothing and computes no financial figure. The three
        states are exhaustive, so they sum to the total -- a reader who sees them add up
        knows nothing was left out of the reckoning, which is the point of publishing a
        status at all. `unclassified` is the one worth acting on: a resource assigned in
        the file with no estimate line naming it. It is expected to be empty.
        """
        context = await _mpp_guard(request, projectId, "finance.view")
        return await _mapping_service(request).mapping_status(
            str(context.organization_id), projectId)

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
