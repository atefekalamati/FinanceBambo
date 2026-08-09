"""Parameterized psycopg repository for append-only project settings."""

from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..domain.settings import FinanceProjectSettings, StaleSettingsVersion
from ..security.guards import FinanceScope


class FinanceSettingsRepository(Protocol):
    async def get_current(
        self, scope: FinanceScope
    ) -> FinanceProjectSettings | None: ...

    async def append_revision_with_audit(
        self,
        scope: FinanceScope,
        gross_built_area: Decimal,
        effective_from: date,
        reason: str,
        expected_revision: int,
        actor_user_id: UUID,
        settings_id: UUID,
        audit_id: UUID,
        occurred_at: datetime,
    ) -> FinanceProjectSettings: ...


class PsycopgFinanceSettingsRepository:
    """Uses one supplied connection so revision and audit share a transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    @staticmethod
    def _map(row: dict) -> FinanceProjectSettings:
        return FinanceProjectSettings(
            id=row["id"],
            organization_id=row["organization_id"],
            project_id=row["project_id"],
            gross_built_area=row["gross_built_area"],
            currency=row["currency"],
            revision=row["revision"],
            effective_from=row["effective_from"],
            reason=row["reason"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    async def get_current(self, scope: FinanceScope) -> FinanceProjectSettings | None:
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                """
                SELECT id, organization_id, project_id, gross_built_area, currency,
                       revision, effective_from, reason, created_by, created_at
                FROM finance_project_settings
                WHERE organization_id = %s AND project_id = %s
                ORDER BY revision DESC
                LIMIT 1
                """,
                (scope.organization_id, scope.project_id),
            )
            row = await cursor.fetchone()
        return None if row is None else self._map(row)

    async def append_revision_with_audit(
        self,
        scope: FinanceScope,
        gross_built_area: Decimal,
        effective_from: date,
        reason: str,
        expected_revision: int,
        actor_user_id: UUID,
        settings_id: UUID,
        audit_id: UUID,
        occurred_at: datetime,
    ) -> FinanceProjectSettings:
        try:
            async with self._connection.transaction():
                async with self._connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        SELECT id, gross_built_area, revision
                        FROM finance_project_settings
                        WHERE organization_id = %s AND project_id = %s
                        ORDER BY revision DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (scope.organization_id, scope.project_id),
                    )
                    current = await cursor.fetchone()
                    current_revision = 0 if current is None else current["revision"]
                    if current_revision != expected_revision:
                        raise StaleSettingsVersion()
                    next_revision = current_revision + 1
                    await cursor.execute(
                        """
                        INSERT INTO finance_project_settings (
                            id, organization_id, project_id, revision,
                            gross_built_area, currency, effective_from, reason,
                            created_by, created_at
                        ) VALUES (%s, %s, %s, %s, %s, 'IRR', %s, %s, %s, %s)
                        RETURNING id, organization_id, project_id, gross_built_area,
                                  currency, revision, effective_from, reason,
                                  created_by, created_at
                        """,
                        (
                            settings_id,
                            scope.organization_id,
                            scope.project_id,
                            next_revision,
                            gross_built_area,
                            effective_from,
                            reason,
                            actor_user_id,
                            occurred_at,
                        ),
                    )
                    inserted = await cursor.fetchone()
                    await cursor.execute(
                        """
                        INSERT INTO finance_audit_events (
                            id, organization_id, project_id, actor_user_id,
                            action, entity_type, entity_id, reason,
                            before_values, after_values, occurred_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            audit_id,
                            scope.organization_id,
                            scope.project_id,
                            actor_user_id,
                            "finance_settings.revised",
                            "finance_project_settings",
                            settings_id,
                            reason,
                            Jsonb(
                                None
                                if current is None
                                else {
                                    "id": str(current["id"]),
                                    "grossBuiltArea": str(current["gross_built_area"]),
                                    "revision": current_revision,
                                }
                            ),
                            Jsonb(
                                {
                                    "id": str(settings_id),
                                    "grossBuiltArea": str(gross_built_area),
                                    "revision": next_revision,
                                }
                            ),
                            occurred_at,
                        ),
                    )
        except errors.UniqueViolation as exc:
            raise StaleSettingsVersion() from exc
        return self._map(inserted)
