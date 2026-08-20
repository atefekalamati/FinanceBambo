"""Shared four-gate authorization and scoped-object concealment."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Mapping
from uuid import UUID

from fastapi import Request

from ..adapters.ports import AuthContextProvider
from ..domain.errors import FinanceDomainError
from .context import AuthContext
from .ports import PermissionAuthorizer, ScopeAuthorizer


@dataclass(frozen=True, slots=True)
class FinanceScope:
    """Effective scope derived only from validated host context and route path."""

    organization_id: UUID
    project_id: str
    actor_user_id: UUID | None = None
    locale: str = "fa"
    # Carried so a handler can report what this actor may do without re-asking the host.
    # Reporting a capability never grants one: every request is still gated independently.
    organization_role: str | None = None
    permission_codes: tuple[str, ...] = ()


class FinanceNotFound(FinanceDomainError):
    status = 404
    code = "FINANCE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Finance record was not found in this scope.")


async def authorize_finance_request(
    request: Request,
    project_id: str,
    permission_code: str | Callable[[AuthContext], str],
    auth_provider: AuthContextProvider,
    scope_authorizer: ScopeAuthorizer,
    permission_authorizer: PermissionAuthorizer,
) -> FinanceScope:
    """Apply authentication, organization, project, and permission gates in order."""

    context = await auth_provider.current(request)
    organization_id = str(context.organization_id)
    await scope_authorizer.require_organization(context, organization_id)
    await scope_authorizer.require_project(context, organization_id, project_id)
    resolved_permission = (
        permission_code(context) if callable(permission_code) else permission_code
    )
    await permission_authorizer.require(context, resolved_permission)
    return FinanceScope(
        organization_id=context.organization_id,
        project_id=project_id,
        actor_user_id=context.user_id,
        locale=context.locale,
        organization_role=context.organization_role,
        permission_codes=tuple(context.permission_codes),
    )


def require_scoped_record(
    record: Mapping[str, object] | None,
    scope: FinanceScope,
) -> Mapping[str, object]:
    """Return a record only when both tenant keys match; otherwise conceal it."""

    if (
        record is None
        or str(record.get("organization_id")) != str(scope.organization_id)
        or record.get("project_id") != scope.project_id
    ):
        raise FinanceNotFound()
    return record
