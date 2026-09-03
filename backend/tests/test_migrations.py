"""What the schema migrations must guarantee, read from the Alembic revisions.

These assertions predate Alembic: they were written against `migrations/*.sql`, which was
the schema source of truth until that mechanism was replaced. The requirements did not
change with the tooling, so the assertions did not either -- only where the SQL is read
from, and one assertion that had to be inverted: a revision must NOT open its own
transaction, because Alembic opens one around it and a nested BEGIN is an error.

The SQL is read from each revision's UPGRADE_SQL / DOWNGRADE_SQL rather than from the
module source, so these tests check what will actually be executed.
"""

import importlib.util
import re
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND_ROOT / "alembic" / "versions"


def revision(stem):
    """Import one revision by path.

    Revision filenames begin with a digit and the directory is deliberately not a package,
    so they are not importable by name. Loading by path is what Alembic itself does.
    """
    spec = importlib.util.spec_from_file_location("finance_revision_" + stem,
                                                  VERSIONS / (stem + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CORE = revision("0001_finance_core")
CONFIRMATION = revision("0002_invoice_confirmation")
LINKED = revision("0003_invoice_linked_documents")
REPORT = revision("0004_report_snapshot_payload")
SOURCE = revision("0005_progress_snapshot_source_type")
HOST_REFERENCE = revision("0006_progress_snapshot_host_reference")

#: The chain, oldest first. Order is part of the contract: 0004 backfills rows that 0001
#: created, and 0005 alters a table 0001 defined.
CHAIN = (CORE, CONFIRMATION, LINKED, REPORT, SOURCE, HOST_REFERENCE)

#: Revision id to the rest of its filename, so a test can find a revision's source.
MODULE_SUFFIX = {"0001": "finance_core", "0002": "invoice_confirmation",
                 "0003": "invoice_linked_documents", "0004": "report_snapshot_payload",
                 "0005": "progress_snapshot_source_type",
                 "0006": "progress_snapshot_host_reference"}

TABLES = (
    "finance_project_settings",
    "finance_resources",
    "estimate_lines",
    "estimate_revisions",
    "price_versions",
    "unit_conversions",
    "progress_snapshot_refs",
    "progress_overrides",
    "invoices",
    "invoice_lines",
    "finance_attachments",
    "extraction_drafts",
    "report_snapshots",
    "finance_audit_events",
    "finance_import_batches",
)


class FinanceMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = CORE.UPGRADE_SQL
        cls.down = CORE.DOWNGRADE_SQL

    def test_the_base_revision_carries_both_directions(self):
        self.assertTrue(CORE.UPGRADE_SQL.strip())
        self.assertTrue(CORE.DOWNGRADE_SQL.strip())
        self.assertEqual("0001", CORE.revision)
        self.assertIsNone(CORE.down_revision)

    def test_all_conceptual_entities_have_tables(self):
        for table in TABLES:
            self.assertRegex(
                self.up,
                rf"(?i)create\s+table\s+if\s+not\s+exists\s+{table}\b",
                table,
            )

    def test_every_finance_table_has_dual_scope_and_scope_index(self):
        for table in TABLES:
            match = re.search(
                rf"(?is)create\s+table\s+if\s+not\s+exists\s+{table}\s*\((.*?)\);",
                self.up,
            )
            self.assertIsNotNone(match, table)
            definition = match.group(1)
            self.assertRegex(definition, r"(?i)organization_id\s+uuid\s+not\s+null")
            self.assertRegex(definition, r"(?i)project_id\s+text\s+not\s+null")
            self.assertRegex(
                self.up,
                rf"(?i)create\s+index\s+if\s+not\s+exists\s+\w+\s+on\s+{table}\s*\(organization_id,\s*project_id",
                table,
            )

    def test_financial_types_and_postgresql_compatibility(self):
        lowered = self.up.lower()
        self.assertIn("numeric(18,0)", lowered)
        self.assertIn("numeric(18,4)", lowered)
        for forbidden in ("create type", " enum", "double precision", " real", " money", "on delete cascade", "unique nulls not distinct"):
            self.assertNotIn(forbidden, lowered)

    def test_v11_money_columns_are_integer_irr(self):
        for column in (
            "original_unit_price_irr",
            "unit_price_irr",
            "unit_price_snapshot_irr",
        ):
            self.assertRegex(self.up, rf"(?i){column}\s+numeric\(18,0\)")

    def test_v11_price_history_is_strictly_append_only(self):
        definition = re.search(
            r"(?is)create\s+table\s+if\s+not\s+exists\s+price_versions\s*\((.*?)\);",
            self.up,
        ).group(1)
        self.assertNotIn("effective_to", definition.lower())
        self.assertRegex(definition, r"(?i)version\s+integer\s+not\s+null")
        self.assertIn("price_versions_immutable", self.up)

    def test_v11_file_and_extraction_lifecycles_are_separate(self):
        self.assertRegex(
            self.up,
            r"(?is)finance_attachments.*?processing_status\s+text.*?"
            r"uploaded.*?processing.*?ready.*?failed",
        )

    def test_unit_conversions_are_versioned_and_immutable(self):
        definition = re.search(r"(?is)create\s+table\s+if\s+not\s+exists\s+unit_conversions\s*\((.*?)\);", self.up).group(1)
        self.assertRegex(definition, r"(?i)version\s+integer\s+not\s+null")
        self.assertIn("unit_conversions_immutable", self.up)
        self.assertRegex(
            self.up,
            r"(?is)extraction_drafts.*?review_status\s+text.*?"
            r"awaitingReview.*?accepted.*?rejected",
        )

    def test_statuses_are_text_with_checks(self):
        self.assertRegex(self.up, r"(?is)invoices.*?status\s+text\s+not\s+null.*?check\s*\(status\s+in")
        self.assertRegex(self.up, r"(?is)extraction_drafts.*?review_status\s+text\s+not\s+null.*?check\s*\(review_status\s+in")

    def test_history_and_confirmed_records_have_immutability_guards(self):
        for trigger in (
            "finance_project_settings_immutable",
            "estimate_revisions_immutable",
            "price_versions_immutable",
            "unit_conversions_immutable",
            "progress_snapshot_refs_immutable",
            "progress_overrides_immutable",
            "report_snapshots_immutable",
            "finance_audit_events_immutable",
            "estimate_original_fields_immutable",
            "confirmed_invoice_immutable",
        ):
            self.assertIn(trigger, self.up)

    def test_rollback_covers_every_created_table(self):
        for table in TABLES:
            self.assertRegex(self.down, rf"(?i)drop\s+table\s+if\s+exists\s+{table}\b")

    def test_revisions_leave_the_transaction_to_alembic_and_stay_rerunnable(self):
        """The one assertion the move to Alembic inverted.

        As files these scripts opened and closed their own transaction. Alembic opens one
        around each revision, so a BEGIN inside the body would be a nested transaction and
        an error. Atomicity is not lost -- it moved to env.py, which is asserted below --
        but the revision itself must not try to control it.
        """
        for script in (self.up, self.down):
            self.assertNotRegex(script, r"(?im)^\s*begin\s*;")
            self.assertNotRegex(script, r"(?im)^\s*commit\s*;")
            self.assertNotRegex(script, r"(?im)^\s*rollback\s*;")
        self.assertNotRegex(self.up, r"(?i)create\s+extension")
        self.assertNotRegex(self.up, r"(?i)create\s+table(?!\s+if\s+not\s+exists)")
        self.assertNotRegex(self.up, r"(?i)create\s+index(?!\s+if\s+not\s+exists)")

    def test_confirmation_idempotency_migration_is_scoped_and_reversible(self):
        up, down = CONFIRMATION.UPGRADE_SQL, CONFIRMATION.DOWNGRADE_SQL
        self.assertIn("confirmation_idempotency_key", up)
        self.assertRegex(up, r"(?is)unique\s+index.*?organization_id\s*,\s*project_id\s*,\s*confirmation_idempotency_key")
        self.assertIn("DROP COLUMN IF EXISTS confirmation_idempotency_key", down)

    def test_report_payload_migration_pins_full_inputs_and_is_reversible(self):
        up, down = REPORT.UPGRADE_SQL, REPORT.DOWNGRADE_SQL
        self.assertIn("snapshot_payload jsonb", up)
        self.assertIn("resource_version_ids jsonb", up)
        self.assertRegex(up, r"(?i)alter column snapshot_payload set not null")
        self.assertIn("DROP COLUMN IF EXISTS snapshot_payload", down)
        # The order is the point: nullable, then backfilled, then NOT NULL. Reversing it
        # would fail on any database that already holds an issued report.
        self.assertLess(up.index("ADD COLUMN IF NOT EXISTS snapshot_payload"),
                        up.index("UPDATE report_snapshots"))
        self.assertLess(up.index("UPDATE report_snapshots"),
                        up.lower().index("alter column snapshot_payload set not null"))

    def test_snapshot_source_type_migration_adds_no_default_and_backfills_nothing(self):
        """The column must not be written into existing rows.

        progress_snapshot_refs carries a BEFORE UPDATE OR DELETE immutability trigger, so a
        backfilling UPDATE would be rejected outright. ADD COLUMN with no DEFAULT is a
        catalog-only change, which is why this migration can run at all -- and it is also
        the honest outcome: the rows already there have no recorded source.
        """
        up = SOURCE.UPGRADE_SQL
        self.assertIn("ADD COLUMN IF NOT EXISTS source_type text", up)
        self.assertNotIn("DEFAULT", up.upper().replace("NO DEFAULT", ""))
        self.assertNotIn("UPDATE progress_snapshot_refs", up)

    def test_snapshot_source_type_is_constrained_and_admits_unknown(self):
        up = SOURCE.UPGRADE_SQL
        self.assertIn("source_type IS NULL", up)
        for allowed in ("microsoft_project", "primavera", "manual", "other"):
            self.assertIn("'%s'" % allowed, up)
        # A filename extension is not evidence of a tool, so an unrecorded source stays
        # unrecorded rather than being labelled.
        self.assertNotIn(".mpp", up.lower().split("--")[0] if "--" in up else up.lower())

    def test_snapshot_source_type_migration_is_reversible_and_rerunnable(self):
        up, down = SOURCE.UPGRADE_SQL, SOURCE.DOWNGRADE_SQL
        self.assertIn("DROP CONSTRAINT IF EXISTS progress_snapshot_refs_source_type_check", down)
        self.assertIn("DROP COLUMN IF EXISTS source_type", down)
        # Re-runnable: the column guard is IF NOT EXISTS and the constraint guard is the
        # explicit pg_constraint lookup ADD CONSTRAINT cannot express.
        self.assertIn("IF NOT EXISTS", up)
        self.assertIn("pg_constraint", up)

    def test_the_rollback_drops_only_what_the_migration_added(self):
        down = SOURCE.DOWNGRADE_SQL
        self.assertNotIn("DROP TABLE", down.upper())
        self.assertNotIn("DELETE FROM", down.upper())
        self.assertNotIn("TRUNCATE", down.upper())

    def test_only_one_scoped_reversal_can_link_to_an_original(self):
        up, down = LINKED.UPGRADE_SQL, LINKED.DOWNGRADE_SQL
        self.assertRegex(up, r"(?is)unique\s+index.*?organization_id\s*,\s*project_id\s*,\s*original_invoice_id.*?source\s*=\s*'reversal'")
        self.assertIn("DROP INDEX IF EXISTS ux_invoices_one_reversal_per_original", down)


if __name__ == "__main__":
    unittest.main()


class AlembicChainTests(unittest.TestCase):
    """The guarantees that belong to Alembic rather than to any one revision.

    Two migration mechanisms over one schema is one too many: they can disagree about what
    has been applied, and only one of them records anything. These tests are what keeps the
    second one from coming back.
    """

    def test_the_chain_is_linear_and_in_the_historical_order(self):
        self.assertEqual(["0001", "0002", "0003", "0004", "0005", "0006"],
                         [module.revision for module in CHAIN])
        expected_parents = [None, "0001", "0002", "0003", "0004", "0005"]
        self.assertEqual(expected_parents, [module.down_revision for module in CHAIN])

    def test_there_is_exactly_one_head(self):
        # A second head means two branches of schema history and an ambiguous "latest".
        revisions = {module.revision for module in CHAIN}
        parents = {module.down_revision for module in CHAIN} - {None}
        self.assertEqual({"0006"}, revisions - parents)

    def test_every_revision_file_is_named_for_the_revision_it_declares(self):
        for path in sorted(VERSIONS.glob("*.py")):
            with self.subTest(path.name):
                module = revision(path.stem)
                self.assertTrue(path.name.startswith(module.revision + "_"),
                                "%s declares revision %s" % (path.name, module.revision))

    def test_the_directory_holds_exactly_the_approved_revisions(self):
        # A stray revision file is a second head waiting to happen.
        self.assertEqual(
            ["0001_finance_core", "0002_invoice_confirmation", "0003_invoice_linked_documents",
             "0004_report_snapshot_payload", "0005_progress_snapshot_source_type",
             "0006_progress_snapshot_host_reference"],
            sorted(path.stem for path in VERSIONS.glob("*.py")))

    def test_every_revision_runs_both_directions(self):
        for module in CHAIN:
            with self.subTest(module.revision):
                self.assertTrue(callable(module.upgrade))
                self.assertTrue(callable(module.downgrade))
                self.assertTrue(module.UPGRADE_SQL.strip())
                self.assertTrue(module.DOWNGRADE_SQL.strip())

    def test_every_revision_can_also_run_offline(self):
        """`alembic upgrade head --sql` must work, and once did not.

        Offline mode hands revisions a mock connection that has no `exec_driver_sql`, so a
        revision calling it crashes with AttributeError instead of emitting SQL -- which is
        exactly what happened here before this was caught. A DDL construct works in both
        modes and, unlike a plain string passed to op.execute, is not scanned for `:name`
        bind parameters that would misread a PostgreSQL cast or a dollar-quoted body.
        """
        for module in CHAIN:
            source = (VERSIONS / ("%s_%s.py" % (module.revision, MODULE_SUFFIX[module.revision]))).read_text(encoding="utf-8")
            with self.subTest(module.revision):
                self.assertIn("op.execute(DDL(UPGRADE_SQL))", source)
                self.assertIn("op.execute(DDL(DOWNGRADE_SQL))", source)
                self.assertNotIn("get_bind()", source)

    def test_no_revision_opens_its_own_transaction(self):
        for module in CHAIN:
            for direction, sql in (("up", module.UPGRADE_SQL), ("down", module.DOWNGRADE_SQL)):
                with self.subTest("%s %s" % (module.revision, direction)):
                    self.assertNotRegex(sql, r"(?im)^\s*(begin|commit|rollback)\s*;")


def executable(sql):
    """The SQL with comment lines removed.

    Assertions about what a migration *does* must not be satisfied or defeated by prose. The
    0006 downgrade explains in a comment that it refuses to delete rows; a naive search for
    "DELETE" finds that sentence and concludes the opposite of the truth.
    """
    return chr(10).join(line for line in sql.splitlines()
                     if not line.strip().startswith("--"))


class HostReferenceRevisionTests(unittest.TestCase):
    """Revision 0006, in both directions."""

    UP = HOST_REFERENCE.UPGRADE_SQL
    DOWN = HOST_REFERENCE.DOWNGRADE_SQL

    def test_each_constraint_check_is_scoped_to_this_table(self):
        """A constraint name is unique per relation, not per schema.

        Testing `conname` alone means an unrelated table carrying a constraint of the same
        name makes this migration believe its own work is already done and skip it -- so the
        CHECK silently never exists, and nothing reports that.
        """
        scoped = executable(self.UP).count("conrelid = 'progress_snapshot_refs'::regclass")
        self.assertEqual(2, scoped, "both existence checks must name the relation")
        self.assertEqual(2, executable(self.UP).count("FROM pg_constraint"),
                         "every pg_constraint lookup is one of the two scoped checks")

    def test_the_downgrade_returns_the_column_to_its_0005_state(self):
        # Dropping the added columns is not the whole revision: it also relaxed
        # source_file_version_id. A downgrade that skipped this would leave a schema
        # matching neither revision, with nothing to say why.
        self.assertIn("ALTER COLUMN source_file_version_id SET NOT NULL", executable(self.DOWN))

    def test_the_downgrade_checks_for_rows_that_cannot_be_restored(self):
        down = executable(self.DOWN)
        self.assertIn("source_file_version_id IS NULL", down)
        self.assertIn("RAISE EXCEPTION", down)

    def test_the_refusal_is_actually_wired_to_the_count(self):
        """The count and the refusal must be the same decision.

        Asserting only that a count and a RAISE both appear leaves the two unconnected: a
        guard changed to `IF false` still contains both, still reads plausibly, and would
        restore NOT NULL on a database holding rows that cannot satisfy it -- failing at the
        ALTER instead, with a constraint-violation message that explains nothing.
        """
        down = executable(self.DOWN)
        self.assertIn("SELECT count(*) INTO ingested", down)
        self.assertIn("IF ingested > 0 THEN", down)
        self.assertLess(down.index("SELECT count(*) INTO ingested"),
                        down.index("IF ingested > 0 THEN"))
        self.assertLess(down.index("IF ingested > 0 THEN"),
                        down.index("ALTER COLUMN source_file_version_id SET NOT NULL"))

    def test_the_downgrade_refuses_rather_than_inventing_or_destroying(self):
        """The two ways to satisfy the old constraint, both forbidden.

        Asserted against executable SQL only. The comments deliberately discuss deleting
        rows and inventing UUIDs, because explaining what is refused is the point.
        """
        down = executable(self.DOWN).upper()
        for forbidden in ("GEN_RANDOM_UUID", "UPDATE PROGRESS_SNAPSHOT_REFS",
                          "DELETE FROM", "TRUNCATE", "INSERT INTO"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, down)

    def test_the_check_runs_after_the_host_columns_are_dropped(self):
        # The requested order, and the safe one: the abort then rolls back a complete
        # downgrade attempt rather than a partial one.
        down = executable(self.DOWN)
        self.assertLess(down.index("DROP COLUMN IF EXISTS host_snapshot_id"),
                        down.index("source_file_version_id IS NULL"))

    def test_the_refusal_explains_itself(self):
        # An operator who hits this at 2am needs to know why, not just that it failed.
        for phrase in ("Downgrade to 0005 refused", "MESSAGE =", "HINT ="):
            with self.subTest(phrase):
                self.assertIn(phrase, self.DOWN)

    def test_neither_direction_contains_a_percent_sign(self):
        """`op.execute(DDL(...))` performs percent-substitution.

        A stray `%` -- the obvious way to format a count into RAISE EXCEPTION -- would make
        the statement fail at execution time rather than here. The message is built by
        concatenation for exactly this reason.
        """
        self.assertNotIn("%", self.UP)
        self.assertNotIn("%", self.DOWN)


class AlembicConfigurationTests(unittest.TestCase):
    """How Alembic gets its connection, and what it must never do."""

    ENV = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    INI = (BACKEND_ROOT / "alembic.ini").read_text(encoding="utf-8")

    def test_the_migration_role_is_used_and_the_runtime_role_is_not(self):
        """The application role deliberately cannot issue DDL.

        Asserted against what the module imports and calls, not against the words in it:
        the docstring and the error message both name FINANCE_DEV_DSN on purpose, to say
        that it is the wrong DSN for this job.
        """
        self.assertIn("from devhost.environment import MissingConfiguration, migration_url",
                      self.ENV)
        self.assertIn("migration_url()", self.ENV)
        # database_url() is the runtime accessor. It must never be called here.
        self.assertNotIn("database_url(", self.ENV)

    def test_no_connection_string_is_committed(self):
        # Neither a real one nor a placeholder that could silently become usable.
        self.assertNotIn("sqlalchemy.url", self.INI)
        for hazard in ("postgresql://", "postgres://", "driver://", "@localhost", "@127.0.0.1"):
            with self.subTest(hazard):
                self.assertNotIn(hazard, self.INI)
        self.assertNotRegex(self.ENV, r"postgresql(\+\w+)?://\w+:")

    def test_an_absent_dsn_fails_instead_of_guessing_a_database(self):
        # The one thing worse than a failed migration is a successful one somewhere
        # unintended, so there is no default and no fallback.
        self.assertIn("MissingConfiguration", self.ENV)
        self.assertIn("FINANCE_MIGRATION_DSN is not set", self.ENV)

    def test_the_environment_is_read_through_the_project_loader(self):
        # Not a second .env parser that could drift from the one everything else uses.
        self.assertIn("from devhost.environment import", self.ENV)

    def test_autogenerate_is_impossible_by_construction(self):
        # There are no SQLAlchemy models: repositories are raw parameterised SQL. Comparing
        # an empty metadata against a real schema would propose dropping the entire schema.
        self.assertIn("target_metadata = None", self.ENV)

    def test_each_migration_still_runs_inside_a_transaction(self):
        # The atomicity the revisions gave up when their BEGIN/COMMIT was removed lives
        # here instead. Without it a half-applied revision could be committed.
        self.assertEqual(2, self.ENV.count("context.begin_transaction()"))


class NoSecondMigrationMechanismTests(unittest.TestCase):
    """Alembic is the source of schema truth, and is the only one."""

    def test_the_hand_written_sql_runner_is_gone(self):
        database = (BACKEND_ROOT / "devhost" / "database.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_migrations", database)
        self.assertIn("upgrade_to_head", database)
        # The mechanism, not the word: the docstring explains what was removed and names
        # the old files legitimately. What must not exist is code that finds and runs them.
        self.assertNotRegex(database, r"glob\(\s*[\"'][^\"']*\.sql")
        self.assertNotIn("MIGRATIONS =", database)

    def test_the_development_host_does_not_migrate_at_startup(self):
        """Inverted deliberately. Startup used to call upgrade_to_head().

        Launching a process is not consent to alter a schema, and a configured
        FINANCE_MIGRATION_DSN is a credential rather than an instruction. Alembic is still
        the only schema mechanism -- it is invoked explicitly by an operator.
        """
        app = (BACKEND_ROOT / "devhost" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("upgrade_to_head", app)
        self.assertNotIn("apply_migrations", app)
        # Call expressions only. The module comment tells the developer to run
        # "alembic upgrade head", and that instruction is the point, not a violation.
        for forbidden in ("command.upgrade", "command.downgrade", "command.stamp",
                          "alembic.command"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, app)

    def test_no_sql_migration_directory_remains(self):
        # Git history is the archive. A second copy in the tree is a second source of truth.
        self.assertFalse((BACKEND_ROOT / "migrations").exists(),
                         "backend/migrations still exists alongside the Alembic revisions")

    def test_the_seed_is_not_a_migration_mechanism(self):
        # reset() and load_seed() are development fixtures behind an environment guard.
        # They must never become the way a schema is prepared.
        database = (BACKEND_ROOT / "devhost" / "database.py").read_text(encoding="utf-8")
        self.assertIn("seeding_allowed", database)
        for fixture in ("def reset", "def load_seed", "def is_seeded"):
            self.assertIn(fixture, database)