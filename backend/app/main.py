"""Application factory for the independently deployable Finance module."""

import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .finance.router import router as finance_router
from .finance.domain.errors import FinanceDomainError
from .finance.integration import FinanceAvailability, mount_finance, unavailable
from .version import VERSION


# Public codes for transport-level failures the domain never raises itself.
STATUS_CODES = {
    401: "FINANCE_UNAUTHENTICATED",
    403: "FINANCE_FORBIDDEN",
    404: "FINANCE_NOT_FOUND",
    422: "VALIDATION_ERROR",
}


REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def _request_id(request: Request | None) -> str:
    if request is not None:
        existing = getattr(request.state, "finance_request_id", None)
        if existing:
            return existing
    return f"req-{uuid4()}"


def _envelope(request: Request | None, status: int, code: str, message: str,
              details: list, headers=None) -> JSONResponse:
    """Wrap every failure in the single error shape the Finance clients parse."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": _request_id(request),
                "details": details,
            }
        },
        headers={**(headers or {}), "X-Request-ID": _request_id(request)},
    )


def _validation_details(errors) -> list:
    """Name the offending field for each rejected input, without echoing its value back."""
    details = []
    for error in errors:
        location = [str(part) for part in error.get("loc", ())]
        details.append({
            # loc starts with the source ("body", "query", "path"); the rest is the field path.
            "field": ".".join(location[1:] or location),
            "message": error.get("msg", "value is not valid"),
        })
    return details


def create_app(*, strict_readiness: bool = False,
               fail_startup_if_unready: bool = False) -> FastAPI:
    """Build the application without binding it to BAMBO production adapters."""
    @asynccontextmanager
    async def dedicated_lifespan(app):
        status = getattr(app.state, "finance_availability", None)
        if not isinstance(status, FinanceAvailability) or not status.ready:
            raise RuntimeError("FINANCE_DEPENDENCY_UNAVAILABLE")
        yield

    application = FastAPI(
        title="BAMBO Finance",
        version=VERSION,
        description=(
            "Finance module for the BAMBO host. Authentication is performed by the "
            "host's trusted opaque session; Finance receives validated identity and "
            "effective scope through adapters. No bearer-token contract is defined here."
        ),
        lifespan=dedicated_lifespan if fail_startup_if_unready else None,
    )

    @application.middleware("http")
    async def finance_runtime_boundary(request: Request, call_next):
        # A shared host may set either value in its trusted middleware. Finance does not
        # read request headers (identity/session/origin handling stays host-owned).
        supplied = str(
            getattr(request.state, "requestId", "")
            or getattr(request.state, "correlationId", "")
        ).strip()
        request.state.finance_request_id = (
            supplied if REQUEST_ID.fullmatch(supplied) else f"req-{uuid4()}"
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.finance_request_id
        return response

    @application.get("/healthz/live", include_in_schema=False)
    async def liveness():
        return {"status": "alive"}

    @application.get("/healthz/finance", include_in_schema=False)
    async def finance_readiness(request: Request):
        status = getattr(request.app.state, "finance_availability", None)
        if not isinstance(status, FinanceAvailability):
            status = unavailable(request.app)
        response = JSONResponse(status_code=200 if status.ready else 503,
                                content=status.public())
        response.headers["X-Request-ID"] = request.state.finance_request_id
        return response

    @application.exception_handler(FinanceDomainError)
    async def finance_domain_error_handler(request: Request, exc: FinanceDomainError):
        return _envelope(
            request,
            getattr(exc, "status", 422),
            getattr(exc, "code", "VALIDATION_ERROR"),
            str(exc),
            [],
        )

    @application.exception_handler(RequestValidationError)
    async def finance_validation_error_handler(request: Request, exc: RequestValidationError):
        return _envelope(
            request,
            422,
            "VALIDATION_ERROR",
            "Request payload failed Finance validation.",
            _validation_details(exc.errors()),
        )

    @application.exception_handler(StarletteHTTPException)
    async def finance_http_error_handler(request: Request, exc: StarletteHTTPException):
        return _envelope(
            request,
            exc.status_code,
            STATUS_CODES.get(exc.status_code, "FINANCE_REQUEST_FAILED"),
            exc.detail if isinstance(exc.detail, str) else "Finance request could not be completed.",
            [],
            getattr(exc, "headers", None),
        )

    if strict_readiness:
        mount_finance(application)
    else:
        application.include_router(finance_router, prefix="/api")
    return application


app = create_app(strict_readiness=True, fail_startup_if_unready=True)
