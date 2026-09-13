"""Production-side composition checks for embedding Finance in the BAMBO host.

This module does not authenticate users, create a pool, or own an application lifespan.
Those are host responsibilities.  It validates the objects the host assembled and exposes
an honest readiness result before Finance traffic is enabled.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Mapping
from uuid import uuid4

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from .domain.errors import FinanceDomainError


REQUIRED_COMPONENTS = (
    "auth_context_provider",
    "scope_authorizer",
    "permission_authorizer",
    "finance_settings_service",
    "finance_resources_service",
    "finance_price_service",
    "unit_conversion_service",
    "progress_service",
    "finance_import_service",
    "invoice_service",
    "finance_attachment_service",
    "finance_extraction_service",
    "finance_live_report_service",
    "finance_audit_service",
)

OPTIONAL_COMPONENTS = (
    "actor_directory",
    "finance_mpp_sync_service",
    "finance_mpp_mapping_service",
    "finance_background_executor",
)


@dataclass(frozen=True, slots=True)
class FinanceAvailability:
    ready: bool
    code: str
    checked_at: datetime
    missing: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()

    def public(self) -> dict:
        """No DSN, table, path, user, or exception text crosses this boundary."""
        return {
            "status": "ready" if self.ready else "unavailable",
            "code": self.code,
            "checkedAt": self.checked_at.isoformat(),
            "optionalCapabilities": list(self.optional),
        }


class FinanceStartupError(RuntimeError):
    """A dedicated Finance process cannot safely accept traffic."""


class FinanceUnavailable(FinanceDomainError):
    status = 503
    code = "FINANCE_UNAVAILABLE"

    def __init__(self):
        super().__init__("Finance is not available on this host.")


async def require_finance_available(request: Request):
    status = getattr(request.app.state, "finance_availability", None)
    if not isinstance(status, FinanceAvailability) or not status.ready:
        raise FinanceUnavailable()


def mount_finance(application, *, prefix="/api"):
    """Mount guarded routes into an existing host without owning its lifespan."""
    from .router import router

    if FinanceUnavailable not in application.exception_handlers:
        async def unavailable_handler(request, _error):
            request_id = getattr(request.state, "finance_request_id", None) or f"req-{uuid4()}"
            return JSONResponse(
                status_code=503,
                content={"error": {
                    "code": "FINANCE_UNAVAILABLE",
                    "message": "Finance is not available on this host.",
                    "requestId": request_id,
                    "details": [],
                }},
                headers={"X-Request-ID": request_id, "Retry-After": "30"},
            )
        application.add_exception_handler(FinanceUnavailable, unavailable_handler)

    unavailable(application)
    application.include_router(
        router,
        prefix=prefix,
        dependencies=[Depends(require_finance_available)],
    )
    return application


def _availability(ready: bool, code: str, *, missing=(), optional=()):
    return FinanceAvailability(
        ready=ready,
        code=code,
        checked_at=datetime.now(timezone.utc),
        missing=tuple(sorted(missing)),
        optional=tuple(sorted(optional)),
    )


def unavailable(application, code="FINANCE_NOT_CONFIGURED", *, missing=()):
    state = _availability(False, code, missing=missing)
    application.state.finance_availability = state
    return state


async def configure_finance(
    application,
    components: Mapping[str, object],
    readiness_probe,
    *,
    dedicated: bool = False,
    operator_notice=None,
) -> FinanceAvailability:
    """Validate, probe, then publish one complete dependency graph atomically.

    In shared-host mode a failure marks only Finance unavailable.  In dedicated mode the
    same failure raises so the process cannot advertise a healthy but unusable service.
    """
    missing = tuple(name for name in REQUIRED_COMPONENTS if components.get(name) is None)
    if readiness_probe is None:
        missing += ("readiness_probe",)
    if missing:
        result = unavailable(application, "FINANCE_DEPENDENCY_MISSING", missing=missing)
    else:
        try:
            answer = readiness_probe.check()
            if isawaitable(answer):
                answer = await answer
            if answer is False:
                raise RuntimeError("readiness probe refused activation")
        except Exception as error:  # the original error is operator-only, never public
            result = unavailable(application, "FINANCE_DEPENDENCY_UNAVAILABLE")
            if operator_notice is not None:
                operator_notice(result.code, type(error).__name__)
        else:
            for name in REQUIRED_COMPONENTS + OPTIONAL_COMPONENTS:
                if name in components and components[name] is not None:
                    setattr(application.state, name, components[name])
            optional = tuple(
                name for name in OPTIONAL_COMPONENTS if components.get(name) is not None
            )
            result = _availability(True, "FINANCE_READY", optional=optional)
            application.state.finance_availability = result

    if not result.ready and operator_notice is not None and result.missing:
        operator_notice(result.code, ",".join(result.missing))
    if not result.ready and dedicated:
        raise FinanceStartupError(result.code)
    return result


class PsycopgFinanceReadinessProbe:
    """Cheap, read-only validation using the host-supplied connection abstraction."""

    SQL = """
        SELECT
            (SELECT version_num FROM finance_alembic_version) AS version_num,
            has_schema_privilege(current_user, current_schema(), 'CREATE') AS can_create,
            has_table_privilege(current_user, 'finance_resources', 'SELECT') AS can_read,
            has_table_privilege(current_user, 'invoices', 'INSERT') AS can_write
    """

    def __init__(self, connection, expected_revision: str):
        self.connection = connection
        self.expected_revision = expected_revision

    async def check(self) -> bool:
        from psycopg.rows import dict_row

        async with self.connection.transaction():
            async with self.connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("SET TRANSACTION READ ONLY")
                await cursor.execute(self.SQL)
                row = await cursor.fetchone()
        return bool(
            row
            and row["version_num"] == self.expected_revision
            and not row["can_create"]
            and row["can_read"]
            and row["can_write"]
        )
