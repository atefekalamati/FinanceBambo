"""Independent scope and permission gates required by the public contract."""

from typing import Protocol

from .context import AuthContext


class ScopeAuthorizer(Protocol):
    async def require_organization(
        self, context: AuthContext, organization_id: str
    ) -> None: ...

    async def require_project(
        self, context: AuthContext, organization_id: str, project_id: str
    ) -> None: ...


class PermissionAuthorizer(Protocol):
    async def require(self, context: AuthContext, permission_code: str) -> None: ...
