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


def _revision(stem):
    """Import an Alembic revision by path; the filenames start with a digit."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "devhost_test_revision_" + stem, BACKEND_ROOT / "alembic" / "versions" / (stem + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    @staticmethod
    def _unconfigured():
        """Detach the .env file so an absent variable is genuinely absent.

        `setting()` reads os.environ first and then falls back to the committed .env, which
        defines APP_ENV=development on a developer machine. Popping the variable alone
        therefore does not produce an unconfigured environment -- the file still supplies
        one, and a test claiming to cover "APP_ENV missing" would be covering "APP_ENV set
        by file" instead, and passing for the wrong reason.
        """
        import devhost.environment as env
        original = env.ENV_FILE
        env.ENV_FILE = Path("does-not-exist.env")
        return env, original

    def test_the_seed_authorization_matrix(self):
        """Every combination that decides whether fixture data may be written.

        Two explicit positive conditions are required and neither has a default. The second
        row is the one that matters most: it is the case where an unconfigured environment
        plus an opt-in used to authorize seeding, because app_env() substitutes
        "development" when APP_ENV is unset.
        """
        from devhost.environment import seeding_allowed
        env, original = self._unconfigured()
        try:
            for app_env_value, opt_in, expected, why in (
                    (None, None, False, "nothing configured at all"),
                    (None, "true", False, "an opt-in cannot substitute for an environment"),
                    ("", "true", False, "blank is not a configured environment"),
                    ("   ", "true", False, "whitespace is not a configured environment"),
                    ("production", "true", False, "production is never seedable"),
                    ("PRODUCTION", "true", False, "case does not create an exception"),
                    ("prod", "true", False, "nor does an abbreviation"),
                    ("staging", "true", False, "staging is deployed; demo data would look real"),
                    ("development", None, False, "a seedable environment is not enough"),
                    ("development", "false", False, "an explicit no is a no"),
                    ("development", "true", True, "both conditions met"),
                    ("dev", "true", True, "both conditions met"),
                    ("test", "true", True, "both conditions met"),
                    ("  Development  ", "true", True, "normalised before comparison"),
            ):
                with self.subTest(app_env=app_env_value, opt_in=opt_in, expect=expected):
                    for name, value in (("APP_ENV", app_env_value),
                                        ("FINANCE_ALLOW_SEED", opt_in)):
                        if value is None:
                            os.environ.pop(name, None)
                        else:
                            os.environ[name] = value
                    self.assertEqual(expected, seeding_allowed(), why)
        finally:
            env.ENV_FILE = original

    def test_an_unconfigured_environment_refuses_even_with_the_opt_in(self):
        """The bug this guard was written for, stated on its own.

        Kept separate from the matrix so it cannot be lost in a table edit. APP_ENV unset
        plus FINANCE_ALLOW_SEED=true must be a refusal, and it was not: seeding_allowed()
        went through app_env(), which returns "development" for an unset variable, so an
        environment nobody had configured satisfied the environment condition by accident.
        """
        from devhost.environment import app_env, seeding_allowed
        env, original = self._unconfigured()
        try:
            os.environ.pop("APP_ENV", None)
            os.environ["FINANCE_ALLOW_SEED"] = "true"
            self.assertEqual("development", app_env(),
                             "app_env keeps its descriptive default, which is not the bug")
            self.assertFalse(seeding_allowed(),
                             "no default may authorize fixture insertion")
        finally:
            env.ENV_FILE = original

    def test_a_configured_environment_from_the_env_file_still_counts(self):
        """Configured in .env is configured. The rule is about absence, not about os.environ."""
        from devhost.environment import seeding_allowed
        import devhost.environment as env
        original = env.ENV_FILE
        configured = Path(self.temporary_env())
        env.ENV_FILE = configured
        try:
            os.environ.pop("APP_ENV", None)
            os.environ["FINANCE_ALLOW_SEED"] = "true"
            self.assertTrue(seeding_allowed())
        finally:
            env.ENV_FILE = original
            configured.unlink(missing_ok=True)

    def temporary_env(self):
        import tempfile
        handle = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8")
        handle.write("APP_ENV=development\n")
        handle.close()
        return handle.name

    def test_the_opt_in_accepts_the_obvious_affirmatives_and_nothing_else(self):
        from devhost.environment import seeding_allowed
        os.environ["APP_ENV"] = "development"
        for value, expected in (("true", True), ("TRUE", True), ("1", True), ("yes", True),
                                ("on", True), ("false", False), ("0", False), ("no", False),
                                ("", False), ("maybe", False), (" true ", True)):
            with self.subTest(value=repr(value)):
                os.environ["FINANCE_ALLOW_SEED"] = value
                self.assertEqual(expected, seeding_allowed())

    def test_the_environment_name_is_still_normalised(self):
        from devhost.environment import app_env
        for value in ("development", "DEVELOPMENT", " Development "):
            with self.subTest(value=repr(value)):
                os.environ["APP_ENV"] = value
                self.assertEqual("development", app_env())

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
        # The schema is defined by the base Alembic revision; the SQL it will execute is
        # what the seed has to satisfy.
        ddl = _revision("0001_finance_core").UPGRADE_SQL
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
class SeedPlanTests(unittest.TestCase):
    """What startup does about fixture data, decided in one place and tested exhaustively."""

    def plan(self, **kwargs):
        from devhost.database import seed_plan
        return seed_plan(**kwargs)

    def test_a_first_seed_loads_without_resetting(self):
        """The correction. Startup used to reset before the first load as well.

        `reset()` exists to discard a developer's working data. Running it against a
        database that has none is harmless in effect and wrong in intent -- it should only
        happen when a developer asks for it.
        """
        self.assertEqual((False, True),
                         self.plan(allowed=True, reseed=False, already_seeded=False))

    def test_an_explicit_reseed_resets_then_loads(self):
        self.assertEqual((True, True),
                         self.plan(allowed=True, reseed=True, already_seeded=False))
        self.assertEqual((True, True),
                         self.plan(allowed=True, reseed=True, already_seeded=True))

    def test_an_already_seeded_database_is_left_alone(self):
        self.assertEqual((False, False),
                         self.plan(allowed=True, reseed=False, already_seeded=True))

    def test_nothing_happens_when_seeding_is_not_allowed(self):
        # Including when a reseed was requested: the environment decides first, and an
        # explicit --reseed is not an override for it.
        for reseed in (False, True):
            for already_seeded in (False, True):
                with self.subTest(reseed=reseed, already_seeded=already_seeded):
                    self.assertEqual((False, False), self.plan(
                        allowed=False, reseed=reseed, already_seeded=already_seeded))

    def test_reset_is_reachable_only_through_the_reseed_path(self):
        # FINANCE_ALLOW_SEED=true alone must never be enough to destroy working data.
        resets = [self.plan(allowed=allowed, reseed=reseed, already_seeded=seeded)[0]
                  for allowed in (True, False) for reseed in (True, False)
                  for seeded in (True, False)]
        self.assertEqual(2, sum(resets), "only the two allowed+reseed combinations reset")


class StartupSafetyTests(unittest.TestCase):
    """Source-level guarantees about what starting the host can do.

    Asserted against the source because the alternative is starting a real host against a
    real database, which is exactly what these rules exist to prevent.
    """

    @staticmethod
    def _code(text):
        """The source with comment lines removed.

        The startup block deliberately tells the developer to run `alembic upgrade head`.
        An assertion searching for "upgrade" finds that instruction and reports the opposite
        of the truth, so these checks look at code rather than at prose.
        """
        return chr(10).join(line for line in text.splitlines()
                            if not line.strip().startswith("#"))

    APP = (BACKEND_ROOT / "devhost" / "app.py").read_text(encoding="utf-8")
    DATABASE = (BACKEND_ROOT / "devhost" / "database.py").read_text(encoding="utf-8")

    def test_startup_never_calls_the_migration_helper(self):
        self.assertNotIn("upgrade_to_head", self._code(self.APP))

    def test_no_startup_path_runs_alembic_at_all(self):
        code = self._code(self.APP)
        for forbidden in ("command.upgrade", "command.downgrade", "command.stamp",
                          "alembic.command", "from alembic"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, code)

    def test_a_configured_migration_dsn_does_not_authorize_ddl(self):
        """Having the owner credential is not the same as being told to use it.

        The DSN is still read -- the seed needs the owner role -- but the only thing it
        gates now is fixture data, and that has its own two-condition guard.
        """
        self.assertIn("migration_url()", self.APP)
        startup = self._code(self.APP.split("def build(")[1].split("connection = ")[0])
        self.assertNotIn("upgrade", startup)

    def test_the_seed_block_is_gated_on_seeding_allowed(self):
        startup = self.APP.split("def build(")[1]
        self.assertIn("seeding_allowed()", startup)
        self.assertIn("database.seed_plan(", startup)

    def test_the_owner_role_is_not_connected_when_seeding_is_disabled(self):
        # Nothing for it to do, so it is not opened at all.
        startup = self.APP.split("def build(")[1].split("connection = ")[0]
        disabled = startup.split("elif admin_dsn:")[0]
        self.assertNotIn("ReconnectingConnection", disabled)

    def test_the_migration_helper_documents_that_startup_must_not_call_it(self):
        self.assertIn("Not called at startup", self.DATABASE)

    def test_a_missing_schema_is_reported_rather_than_repaired(self):
        """Failing clearly beats hidden DDL."""
        self.assertIn("class SchemaNotMigrated", self.DATABASE)
        self.assertIn("alembic upgrade head", self.DATABASE)
        self.assertIn("UndefinedTable", self.DATABASE)
        self.assertNotIn("CREATE TABLE", self.DATABASE)


class SchemaDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    """The message a developer gets when they start the host before migrating."""

    class MissingSchema:
        """A connection whose finance tables do not exist."""

        def cursor(self, *args, **kwargs):
            import psycopg
            outer = self

            class Cursor:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *exc):
                    return False

                async def execute(self, *args, **kwargs):
                    raise psycopg.errors.UndefinedTable(
                        'relation "finance_project_settings" does not exist')

            return Cursor()

    async def test_it_names_the_command_to_run(self):
        from devhost.database import SchemaNotMigrated, is_seeded
        with self.assertRaises(SchemaNotMigrated) as caught:
            await is_seeded(self.MissingSchema())
        message = str(caught.exception)
        self.assertIn("alembic upgrade head", message)
        self.assertIn("does not migrate", message)
