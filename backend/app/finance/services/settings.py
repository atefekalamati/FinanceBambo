"""Finance project settings application service."""

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ..domain.settings import FinanceProjectSettings, FinanceSettingsNotFound
from ..repositories.settings import FinanceSettingsRepository
from ..schemas.settings import FinanceSettingsPatch, FinanceSettingsRevisionResponse
from ..security.guards import FinanceScope


#: What editing project settings costs. One permission, for everybody.
#:
#: This used to read `finance.view if context.organization_role == "org_chief" else
#: finance.edit`, which meant a role NAME decided what a caller could change: an org chief
#: edited the gross built area -- the divisor under every per-square-metre figure in the
#: module -- holding read-only permission, and revoking `finance.edit` from them changed
#: nothing. A permission that can be bypassed by being called something is not a permission,
#: and a host that renames its roles would have silently moved the gate.
#:
#: Roles still exist and still travel on the context; the host needs them and other
#: interfaces read them. They simply no longer decide authorization here.
SETTINGS_EDIT_PERMISSION = "finance.edit"


def may_edit_settings(scope) -> bool:
    """Answer the same question the PATCH gate asks, so the UI cannot drift from enforcement."""

    return SETTINGS_EDIT_PERMISSION in scope.permission_codes


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

    async def revisions(self, scope: FinanceScope) -> list[FinanceSettingsRevisionResponse]:
        """Pair each revision with the area it replaced; the oldest one replaced nothing."""
        trail = await self._repository.list_revisions(scope)
        return [
            FinanceSettingsRevisionResponse.from_domain(
                value,
                trail[index + 1].gross_built_area if index + 1 < len(trail) else None,
            )
            for index, value in enumerate(trail)
        ]

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
