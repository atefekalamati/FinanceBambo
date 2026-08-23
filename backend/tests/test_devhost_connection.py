"""Cover the development host's reconnecting connection handle.

This exercises dev tooling rather than the shipped module, but the handle is the piece
that decides whether a dropped database means one failed request or a dead process, and
that is not something to leave unverified.
"""

import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from psycopg import OperationalError

from devhost import connection as devhost_connection
from devhost.connection import ReconnectingConnection


class FakeCursorContext:
    def __init__(self, owner, fail):
        self.owner, self.fail = owner, fail

    async def __aenter__(self):
        if self.fail:
            raise OperationalError("the connection is closed")
        return self.owner

    async def __aexit__(self, *_):
        return False


class FakeConnection:
    def __init__(self, index):
        self.index = index
        self.closed = False
        self.fail_on_enter = False
        self.cursor_kwargs = None

    def cursor(self, **kwargs):
        self.cursor_kwargs = kwargs
        return FakeCursorContext(self, self.fail_on_enter)

    def transaction(self, *_args, **_kwargs):
        return FakeCursorContext(self, self.fail_on_enter)

    async def close(self):
        self.closed = True


class FakeConnector:
    """Stands in for psycopg's AsyncConnection.connect."""

    def __init__(self):
        self.opened = []

    async def connect(self, dsn, **kwargs):
        self.opened.append((dsn, kwargs))
        created = FakeConnection(len(self.opened))
        return created


class ReconnectingConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.connector = FakeConnector()
        self.original = devhost_connection.AsyncConnection
        devhost_connection.AsyncConnection = self.connector
        self.handle = ReconnectingConnection("postgresql://example/db")

    def tearDown(self):
        devhost_connection.AsyncConnection = self.original

    async def test_the_first_use_opens_one_connection_in_autocommit(self):
        async with self.handle.cursor(row_factory=dict) as cursor:
            self.assertEqual(1, cursor.index)
        self.assertEqual(1, len(self.connector.opened))
        # Repositories own their transaction boundaries, so autocommit has to stay on.
        self.assertEqual({"autocommit": True}, self.connector.opened[0][1])
        self.assertEqual({"row_factory": dict}, cursor.cursor_kwargs)

    async def test_a_second_use_reuses_the_same_open_connection(self):
        async with self.handle.cursor():
            pass
        async with self.handle.cursor():
            pass
        self.assertEqual(1, len(self.connector.opened))

    async def test_a_closed_connection_is_replaced_on_the_next_acquisition(self):
        first = await self.handle.live()
        first.closed = True
        async with self.handle.cursor() as cursor:
            self.assertEqual(2, cursor.index)
        self.assertEqual(2, len(self.connector.opened))

    async def test_a_connection_that_only_looks_open_is_retried_once(self):
        # The database went away without the client noticing: `closed` is still False,
        # and the failure only surfaces when a cursor is opened.
        first = await self.handle.live()
        first.fail_on_enter = True
        async with self.handle.cursor() as cursor:
            self.assertEqual(2, cursor.index)
        self.assertTrue(first.closed, "the dead connection should be discarded")

    async def test_a_second_failure_surfaces_rather_than_looping(self):
        original_connect = self.connector.connect

        async def always_broken(dsn, **kwargs):
            created = await original_connect(dsn, **kwargs)
            created.fail_on_enter = True
            return created

        self.connector.connect = always_broken
        with self.assertRaises(OperationalError):
            async with self.handle.cursor():
                pass
        # One initial attempt and exactly one retry: a real outage must not spin.
        self.assertEqual(2, len(self.connector.opened))

    async def test_transactions_go_through_the_same_recovery(self):
        first = await self.handle.live()
        first.closed = True
        async with self.handle.transaction() as reopened:
            self.assertEqual(2, reopened.index)

    async def test_close_releases_the_underlying_connection(self):
        opened = await self.handle.live()
        await self.handle.close()
        self.assertTrue(opened.closed)
        # And the handle is still usable afterwards.
        async with self.handle.cursor() as cursor:
            self.assertEqual(2, cursor.index)


class SeedGuardTests(unittest.TestCase):
    """Development fixtures must not be loadable into a deployed environment."""

    def setUp(self):
        self.original = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original)

    def test_seeding_is_allowed_only_outside_production(self):
        from devhost.environment import app_env, seeding_allowed
        for value, expected in (("development", True), ("dev", True), ("test", True),
                                ("staging", True), ("production", False), ("PRODUCTION", False),
                                ("prod", False)):
            with self.subTest(app_env=value):
                os.environ["APP_ENV"] = value
                self.assertEqual(expected, seeding_allowed())
                self.assertEqual(value.strip().lower(), app_env())

    def test_the_connection_string_is_never_echoed_with_its_password(self):
        from devhost.environment import redacted
        shown = redacted("postgresql://finance_app:s3cr3t@db.internal:5432/finance")
        self.assertNotIn("s3cr3t", shown)
        self.assertIn("finance_app", shown)
        self.assertIn("db.internal:5432/finance", shown)

    def test_a_missing_dsn_is_an_error_rather_than_a_guessable_default(self):
        from devhost.environment import MissingConfiguration, database_url
        os.environ.pop("FINANCE_DEV_DSN", None)
        import devhost.environment as env
        original = env.ENV_FILE
        env.ENV_FILE = Path("does-not-exist.env")
        try:
            with self.assertRaises(MissingConfiguration):
                database_url()
        finally:
            env.ENV_FILE = original


if __name__ == "__main__":
    unittest.main()
