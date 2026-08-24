"""Cover the development host's reconnecting connection handle.

This exercises dev tooling rather than the shipped module, but the handle is the piece
that decides whether a dropped database means one failed request or a dead process, and
that is not something to leave unverified.
"""

import os
import sys
import unittest
from pathlib import Path
from uuid import UUID

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


class FixtureIdentityTests(unittest.TestCase):
    """Telling a fixture from real activity must not depend on business columns."""

    def test_every_seeded_id_belongs_to_a_declared_family(self):
        import re
        from devhost import seed
        sql = (Path(seed.__file__).parent / "seed.sql").read_text(encoding="utf-8")
        # Ids the seed writes, excluding the tenant and actor ids it merely references.
        referenced = {str(seed.ORGANIZATION_ID)[:8], str(seed.ACTOR_ID)[:8],
                      str(seed.IMPORTER_ID)[:8], "44444444",
                      str(seed.PROGRESS_OVERRIDE["created_by"])[:8]}
        written = {value[:8] for value in
                   re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", sql)}
        undeclared = written - set(seed.FIXTURE_ID_PREFIXES) - referenced
        self.assertEqual(set(), undeclared,
                         "seed.sql writes ids outside FIXTURE_ID_PREFIXES; --changes would "
                         "report them as user activity")

    def test_every_seeded_line_declares_the_source_its_own_data_implies(self):
        """`source` says how a line entered the system, so each value is pinned per line.

        The old assertion only checked that both values appeared somewhere in the list,
        which would have passed with every source swapped. It also could not notice the
        real defect this replaced: a value corrected here while the seeded database row
        kept the old one. `devhost.inspect --drift` is what compares the two.
        """
        from devhost import seed
        by_id = {str(line[0]): line[6] for line in seed.ESTIMATE_LINES}
        self.assertEqual({
            # Quantified lines linked to a schedule assignment: the progress feed's rows.
            "30000000-0000-4000-8000-000000000001": "progress_feed",
            "30000000-0000-4000-8000-000000000002": "progress_feed",
            "30000000-0000-4000-8000-000000000003": "progress_feed",
            "30000000-0000-4000-8000-000000000004": "progress_feed",
            # The permit is an amount a person entered, not a measured quantity the
            # schedule reported. It carries an activity link because the user chose one.
            "30000000-0000-4000-8000-000000000005": "manual_entry",
        }, by_id)

    def test_the_seed_sql_agrees_with_the_seed_module_on_every_source(self):
        """seed.sql is generated from seed.py, so a stale copy would ship a wrong origin."""
        import re
        from devhost import seed
        sql = (BACKEND_ROOT / "devhost" / "seed.sql").read_text(encoding="utf-8")
        written = {}
        for line in sql.splitlines():
            if "INSERT INTO estimate_lines" not in line:
                continue
            identifier = re.search(r"'([0-9a-f]{8}-[0-9a-f-]{27})'", line)
            source = re.search(r"'(progress_feed|excel_import|manual_entry)'", line)
            if identifier and source:
                written[identifier.group(1)] = source.group(1)
        self.assertEqual({str(line[0]): line[6] for line in seed.ESTIMATE_LINES}, written)

    def test_every_declared_source_is_one_the_schema_admits(self):
        import re
        from devhost import seed
        ddl = (BACKEND_ROOT / "migrations" / "0001_finance_core.up.sql").read_text(encoding="utf-8")
        clause = re.search(r"source text NOT NULL CHECK \(source IN \(([^)]*)\)\)", ddl)
        self.assertIsNotNone(clause, "the estimate_lines source CHECK moved")
        allowed = set(re.findall(r"'([a-z_]+)'", clause.group(1)))
        self.assertEqual({"progress_feed", "excel_import", "manual_entry"}, allowed)
        self.assertTrue({line[6] for line in seed.ESTIMATE_LINES} <= allowed)

    def test_the_seed_mirrors_the_frontend_mock_line_for_line(self):
        """The seed exists so the dev database shows what the mock showed.

        Compared against the mock itself rather than against a copied list, because a copy
        is what lets the two drift while both look correct on their own.
        """
        import re
        from devhost import seed
        mock = (BACKEND_ROOT.parent / "frontend" / "src" / "adapters" / "mock"
                / "financial-items-adapter.js").read_text(encoding="utf-8")
        mocked = {}
        for entry in re.finditer(r'lineId:\s*"([0-9a-f-]{36})"(.*?)source:\s*"([a-z_]+)"', mock):
            mocked[entry.group(1)] = entry.group(3)
        self.assertTrue(mocked, "no estimate lines found in the mock adapter")
        self.assertEqual({str(line[0]): line[6] for line in seed.ESTIMATE_LINES}, mocked)


if __name__ == "__main__":
    unittest.main()


class SeededProgressProviderTests(unittest.IsolatedAsyncioTestCase):
    """What the development host says when it does not have the snapshot.

    Finance treats an empty header and a missing reply the same way now, so this is not
    about avoiding a 500 any more. It is about the shape a production provider author
    reads here and copies: a header with nothing in it claims "here is the snapshot you
    asked for" and then describes no snapshot, which is a worse contract than saying
    nothing.
    """

    from datetime import date as _date, datetime as _datetime, timezone as _timezone

    ORG = UUID("11111111-1111-4111-8111-111111111111")
    OTHER = UUID("22222222-2222-4222-8222-222222222222")
    SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")

    def provider(self):
        from devhost.ports import SeededProgressSnapshotProvider
        return SeededProgressSnapshotProvider(
            self.ORG, "sample_site_01",
            [{"progress_snapshot_id": self.SNAPSHOT, "source_file_version_id": UUID(int=7),
              "source_file_name_safe": "plan.mpp", "reporting_date": self._date(2026, 8, 2),
              "imported_at": self._datetime(2026, 8, 2, tzinfo=self._timezone.utc),
              "assignments": [{"assignmentExternalId": "AS1"}]}],
            UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"))

    async def test_a_scope_it_does_not_serve_gets_no_reply_rather_than_an_empty_one(self):
        provider = self.provider()
        for label, args in {
                "another organisation": (str(self.OTHER), "sample_site_01", str(self.SNAPSHOT)),
                "another project": (str(self.ORG), "other_site", str(self.SNAPSHOT)),
                "an unknown snapshot": (str(self.ORG), "sample_site_01", str(UUID(int=99)))}.items():
            with self.subTest(label):
                self.assertIsNone(await provider.get_snapshot(*args))

    async def test_the_scope_it_does_serve_gets_a_header_naming_that_exact_scope(self):
        feed = await self.provider().get_snapshot(str(self.ORG), "sample_site_01", str(self.SNAPSHOT))
        self.assertEqual((str(self.ORG), "sample_site_01", str(self.SNAPSHOT)),
                         (feed["snapshot"]["organizationId"], feed["snapshot"]["projectId"],
                          feed["snapshot"]["progressSnapshotId"]))
        # Copies, so a caller mutating the feed cannot corrupt the next request's answer.
        feed["assignments"][0]["assignmentExternalId"] = "changed"
        again = await self.provider().get_snapshot(str(self.ORG), "sample_site_01", str(self.SNAPSHOT))
        self.assertEqual("AS1", again["assignments"][0]["assignmentExternalId"])
