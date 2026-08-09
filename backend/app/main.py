"""Application factory for the independently deployable Finance module."""

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .finance.router import router as finance_router
from .finance.domain.errors import FinanceDomainError


def create_app() -> FastAPI:
    """Build the application without binding it to BAMBO production adapters."""
    application = FastAPI(title="BAMBO Finance", version="0.0.0")

    @application.exception_handler(FinanceDomainError)
    async def finance_domain_error_handler(_request: Request, exc: FinanceDomainError):
        return JSONResponse(
            status_code=getattr(exc, "status", 422),
            content={
                "error": {
                    "code": getattr(exc, "code", "VALIDATION_ERROR"),
                    "message": str(exc),
                    "requestId": f"req-{uuid4()}",
                    "details": [],
                }
            },
        )

    application.include_router(finance_router, prefix="/api")
    return application


app = create_app()
