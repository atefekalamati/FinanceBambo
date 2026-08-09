"""Finance project settings application service."""

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ..domain.settings import FinanceProjectSettings, FinanceSettingsNotFound
from ..repositories.settings import FinanceSettingsRepository
from ..schemas.settings import FinanceSettingsPatch
from ..security.context import AuthContext
from ..security.guards import FinanceScope


def settings_edit_permission(context: AuthContext) -> str:
    """Apply PRD role policy using only existing coarse host permissions."""

    return "finance.view" if context.organization_role == "org_chief" else "finance.edit"


class FinanceSettingsService:
    def __init__(
        self,
        repository: FinanceSettingsRepository,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock

    async def get(self, scope: FinanceScope) -> FinanceProjectSettings:
        current = await self._repository.get_current(scope)
        if current is None:
            raise FinanceSettingsNotFound()
        return current

    async def summary(self, scope: FinanceScope) -> FinanceProjectSettings:
        return await self.get(scope)

    async def update(
        self, scope: FinanceScope, command: FinanceSettingsPatch
    ) -> FinanceProjectSettings:
        if scope.actor_user_id is None:
            raise PermissionError("authenticated actor is required")
        return await self._repository.append_revision_with_audit(
            scope=scope,
            gross_built_area=command.gross_built_area,
            effective_from=command.effective_from,
            reason=command.reason.strip(),
            expected_revision=command.expected_revision,
            actor_user_id=scope.actor_user_id,
            settings_id=self._id_factory(),
            audit_id=self._id_factory(),
            occurred_at=self._clock(),
        )
