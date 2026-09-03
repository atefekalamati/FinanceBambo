"""Application factory for the independently deployable Finance module."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .finance.router import router as finance_router
from .finance.domain.errors import FinanceDomainError


# Public codes for transport-level failures the domain never raises itself.
STATUS_CODES = {
    401: "FINANCE_UNAUTHENTICATED",
    403: "FINANCE_FORBIDDEN",
    404: "FINANCE_NOT_FOUND",
    422: "VALIDATION_ERROR",
}


def _envelope(status: int, code: str, message: str, details: list, headers=None) -> JSONResponse:
    """Wrap every failure in the single error shape the Finance clients parse."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": f"req-{uuid4()}",
                "details": details,
            }
        },
        headers=headers,
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


def create_app() -> FastAPI:
    """Build the application without binding it to BAMBO production adapters."""
    application = FastAPI(title="BAMBO Finance", version="0.0.0")

    @application.exception_handler(FinanceDomainError)
    async def finance_domain_error_handler(_request: Request, exc: FinanceDomainError):
        return _envelope(
            getattr(exc, "status", 422),
            getattr(exc, "code", "VALIDATION_ERROR"),
            str(exc),
            [],
        )

    @application.exception_handler(RequestValidationError)
    async def finance_validation_error_handler(_request: Request, exc: RequestValidationError):
        return _envelope(
            422,
            "VALIDATION_ERROR",
            "Request payload failed Finance validation.",
            _validation_details(exc.errors()),
        )

    @application.exception_handler(StarletteHTTPException)
    async def finance_http_error_handler(_request: Request, exc: StarletteHTTPException):
        return _envelope(
            exc.status_code,
            STATUS_CODES.get(exc.status_code, "FINANCE_REQUEST_FAILED"),
            exc.detail if isinstance(exc.detail, str) else "Finance request could not be completed.",
            [],
            getattr(exc, "headers", None),
        )

    application.include_router(finance_router, prefix="/api")
    return application


app = create_app()
