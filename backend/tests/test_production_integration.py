import asyncio
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.integration import (
    FinanceStartupError,
    REQUIRED_COMPONENTS,
    configure_finance,
    mount_finance,
)
from app.finance.pool_connection import HostPoolConnection


class Probe:
    def __init__(self, answer=True, error=None):
        self.answer, self.error, self.calls = answer, error, 0

    async def check(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


def components():
    return {name: object() for name in REQUIRED_COMPONENTS}


class ProductionCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_dependency_fails_only_finance_on_a_shared_host(self):
        app = create_app(strict_readiness=True)
        seen = []
        result = await configure_finance(app, {}, Probe(), operator_notice=lambda *x: seen.append(x))
        self.assertFalse(result.ready)
        self.assertIn("auth_context_provider", result.missing)
        self.assertTrue(seen)
        with TestClient(app) as client:
            self.assertEqual(200, client.get("/healthz/live").status_code)
            response = client.get("/api/projects/p1/finance/settings")
            self.assertEqual(503, response.status_code)
            self.assertEqual("FINANCE_UNAVAILABLE", response.json()["error"]["code"])
            self.assertNotIn("auth_context_provider", response.text)

    async def test_guard_can_be_mounted_into_a_shared_host_without_owning_lifespan(self):
        from fastapi import FastAPI

        host = FastAPI()
        host.get("/unrelated")(lambda: {"ok": True})
        mount_finance(host)
        with TestClient(host) as client:
            self.assertEqual(200, client.get("/unrelated").status_code)
            self.assertEqual(503, client.get(
                "/api/projects/p1/finance/settings").status_code)

    async def test_dedicated_process_refuses_missing_configuration(self):
        with self.assertRaises(FinanceStartupError):
            await configure_finance(create_app(), {}, Probe(), dedicated=True)

    async def test_dedicated_entrypoint_fails_during_startup_when_unconfigured(self):
        with self.assertRaises(RuntimeError):
            with TestClient(create_app(strict_readiness=True,
                                       fail_startup_if_unready=True)):
                pass

    async def test_probe_failure_does_not_publish_partial_components(self):
        app = create_app(strict_readiness=True)
        result = await configure_finance(app, components(), Probe(error=OSError("secret DSN")))
        self.assertFalse(result.ready)
        self.assertFalse(hasattr(app.state, "invoice_service"))
        self.assertNotIn("secret", str(result.public()))

    async def test_complete_graph_is_published_only_after_probe_passes(self):
        app, probe, graph = create_app(strict_readiness=True), Probe(), components()
        graph["actor_directory"] = object()
        result = await configure_finance(app, graph, probe, dedicated=True)
        self.assertTrue(result.ready)
        self.assertEqual(1, probe.calls)
        self.assertIs(graph["invoice_service"], app.state.invoice_service)
        with TestClient(app) as client:
            response = client.get("/healthz/finance", headers={"X-Request-ID": "host-42"})
            self.assertEqual(200, response.status_code)
            # Finance never trusts request headers directly; a host correlation middleware
            # may populate request.state. Without it Finance generates a safe identifier.
            self.assertNotEqual("host-42", response.headers["X-Request-ID"])
            self.assertTrue(response.headers["X-Request-ID"].startswith("req-"))
            self.assertNotIn("missing", response.json())


class FakeCursor:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_error):
        return False


class BrokenContext:
    async def __aenter__(self):
        raise OSError("cannot enter")

    async def __aexit__(self, *_error):
        return False


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.transactions += 1

    async def __aexit__(self, error_type, *_error):
        if error_type:
            self.connection.rollbacks += 1
        else:
            self.connection.commits += 1
        return False


class FakeConnection:
    def __init__(self, identity):
        self.identity = identity
        self.transactions = self.commits = self.rollbacks = 0

    def cursor(self, **_kwargs):
        return FakeCursor()

    def transaction(self, *_args, **_kwargs):
        return FakeTransaction(self)


class FakeLease:
    def __init__(self, pool):
        self.pool, self.connection = pool, None

    async def __aenter__(self):
        self.connection = FakeConnection(len(self.pool.connections) + 1)
        self.pool.connections.append(self.connection)
        self.pool.active += 1
        self.pool.maximum_active = max(self.pool.maximum_active, self.pool.active)
        return self.connection

    async def __aexit__(self, *_error):
        self.pool.active -= 1
        self.pool.releases += 1
        return False


class FakePool:
    def __init__(self):
        self.connections = []
        self.active = self.maximum_active = self.releases = 0
        self.timeouts = []

    def connection(self, timeout):
        self.timeouts.append(timeout)
        return FakeLease(self)


class HostPoolConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_pins_cursor_and_releases_on_success(self):
        pool, db = FakePool(), HostPoolConnection(FakePool())
        pool = db.pool
        async with db.transaction():
            pinned = db._current.get()
            async with db.cursor():
                self.assertIs(pinned, db._current.get())
        self.assertEqual((1, 1, 1), (len(pool.connections), pool.releases,
                                     pool.connections[0].commits))

    async def test_failure_rolls_back_and_releases_before_reuse(self):
        pool, db = FakePool(), None
        db = HostPoolConnection(pool, timeout_seconds=2)
        with self.assertRaises(ValueError):
            async with db.transaction():
                raise ValueError("write failed")
        self.assertEqual((1, 1, 0), (pool.releases, pool.connections[0].rollbacks,
                                     pool.active))
        async with db.cursor():
            pass
        self.assertEqual(2, pool.releases)
        self.assertEqual([2, 2], pool.timeouts)

    async def test_cancellation_also_releases_the_lease(self):
        pool, db = FakePool(), None
        db = HostPoolConnection(pool)
        with self.assertRaises(asyncio.CancelledError):
            async with db.transaction():
                raise asyncio.CancelledError()
        self.assertEqual((1, 1, 0), (pool.connections[0].rollbacks,
                                     pool.releases, pool.active))

    async def test_concurrent_operations_never_share_a_connection(self):
        pool, db = FakePool(), None
        db = HostPoolConnection(pool)

        async def use_cursor():
            async with db.cursor():
                await asyncio.sleep(0)

        await asyncio.gather(use_cursor(), use_cursor())
        self.assertEqual(2, len(pool.connections))
        self.assertEqual(2, pool.releases)

    async def test_cursor_enter_failure_releases_connection(self):
        pool = FakePool()
        db = HostPoolConnection(pool)
        original = FakeConnection.cursor
        FakeConnection.cursor = lambda self, **kwargs: BrokenContext()
        try:
            with self.assertRaises(OSError):
                async with db.cursor():
                    pass
        finally:
            FakeConnection.cursor = original
        self.assertEqual((1, 0), (pool.releases, pool.active))

    async def test_transaction_enter_failure_clears_context_and_releases(self):
        pool = FakePool()
        db = HostPoolConnection(pool)
        original = FakeConnection.transaction
        FakeConnection.transaction = lambda self, *args, **kwargs: BrokenContext()
        try:
            with self.assertRaises(OSError):
                async with db.transaction():
                    pass
        finally:
            FakeConnection.transaction = original
        self.assertIsNone(db._current.get())
        self.assertEqual((1, 0), (pool.releases, pool.active))

    def test_timeout_must_be_explicitly_bounded(self):
        with self.assertRaises(ValueError):
            HostPoolConnection(FakePool(), timeout_seconds=0)
