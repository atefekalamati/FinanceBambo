import unittest
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.settings import StaleSettingsVersion
from app.finance.repositories.settings import PsycopgFinanceSettingsRepository
from app.finance.security.guards import FinanceScope


ORG_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SETTING_ID = UUID("10000000-0000-4000-8000-000000000002")
AUDIT_ID = UUID("90000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def setting_row(revision=2):
    return {
        "id": SETTING_ID,
        "organization_id": ORG_ID,
        "project_id": "sample_site_01",
        "gross_built_area": Decimal("5000.1250"),
        "currency": "IRR",
        "revision": revision,
        "effective_from": date(2026, 8, 7),
        "reason": "اصلاح نقشه",
        "created_by": ACTOR_ID,
        "created_at": NOW,
    }


class AsyncContext:
    def __init__(self, owner):
        self.owner = owner

    async def __aenter__(self):
        self.owner.entered += 1
        return self.owner

    async def __aexit__(self, exc_type, _exc, _traceback):
        self.owner.exited += 1
        self.owner.exception_type = exc_type


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executions = []
        self.entered = 0
        self.exited = 0
        self.exception_type = None

    def context(self):
        return AsyncContext(self)

    async def execute(self, query, parameters):
        self.executions.append((query, parameters))

    async def fetchone(self):
        return self.rows.pop(0)


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.transaction_state = type(
            "TransactionState",
            (),
            {"entered": 0, "exited": 0, "exception_type": None},
        )()

    def cursor(self, **_kwargs):
        return self.cursor_instance.context()

    def transaction(self):
        return AsyncContext(self.transaction_state)


class SettingsRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = FinanceScope(ORG_ID, "sample_site_01", ACTOR_ID)

    async def test_append_uses_one_transaction_parameterized_scope_and_audit(self):
        current = {
            "id": UUID("10000000-0000-4000-8000-000000000001"),
            "gross_built_area": Decimal("4250.0000"),
            "revision": 1,
        }
        connection = FakeConnection((current, setting_row()))
        repository = PsycopgFinanceSettingsRepository(connection)
        result = await repository.append_revision_with_audit(
            scope=self.scope,
            gross_built_area=Decimal("5000.1250"),
            effective_from=date(2026, 8, 7),
            reason="اصلاح نقشه",
            expected_revision=1,
            actor_user_id=ACTOR_ID,
            settings_id=SETTING_ID,
            audit_id=AUDIT_ID,
            occurred_at=NOW,
        )
        self.assertEqual(2, result.revision)
        self.assertEqual(1, connection.transaction_state.entered)
        self.assertEqual(1, connection.transaction_state.exited)
        self.assertIsNone(connection.transaction_state.exception_type)
        self.assertEqual(3, len(connection.cursor_instance.executions))
        for query, parameters in connection.cursor_instance.executions:
            self.assertIn("%s", query)
            self.assertNotIn(str(ORG_ID), query)
            self.assertIsInstance(parameters, tuple)
        first_parameters = connection.cursor_instance.executions[0][1]
        self.assertEqual((ORG_ID, "sample_site_01"), first_parameters)

    async def test_stale_version_aborts_before_insert_and_audit(self):
        connection = FakeConnection(
            ({"id": SETTING_ID, "gross_built_area": Decimal("5000"), "revision": 2},)
        )
        repository = PsycopgFinanceSettingsRepository(connection)
        with self.assertRaises(StaleSettingsVersion):
            await repository.append_revision_with_audit(
                scope=self.scope,
                gross_built_area=Decimal("6000"),
                effective_from=date(2026, 8, 7),
                reason="نسخه قدیمی",
                expected_revision=1,
                actor_user_id=ACTOR_ID,
                settings_id=SETTING_ID,
                audit_id=AUDIT_ID,
                occurred_at=NOW,
            )
        self.assertEqual(1, len(connection.cursor_instance.executions))
        self.assertIs(connection.transaction_state.exception_type, StaleSettingsVersion)


if __name__ == "__main__":
    unittest.main()
