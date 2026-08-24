import re
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
UP = BACKEND_ROOT / "migrations" / "0001_finance_core.up.sql"
DOWN = BACKEND_ROOT / "migrations" / "0001_finance_core.down.sql"
CONFIRM_UP = BACKEND_ROOT / "migrations" / "0002_invoice_confirmation.up.sql"
CONFIRM_DOWN = BACKEND_ROOT / "migrations" / "0002_invoice_confirmation.down.sql"
LINKED_UP = BACKEND_ROOT / "migrations" / "0003_invoice_linked_documents.up.sql"
LINKED_DOWN = BACKEND_ROOT / "migrations" / "0003_invoice_linked_documents.down.sql"
REPORT_UP = BACKEND_ROOT / "migrations" / "0004_report_snapshot_payload.up.sql"
REPORT_DOWN = BACKEND_ROOT / "migrations" / "0004_report_snapshot_payload.down.sql"
SOURCE_UP = BACKEND_ROOT / "migrations" / "0005_progress_snapshot_source_type.up.sql"
SOURCE_DOWN = BACKEND_ROOT / "migrations" / "0005_progress_snapshot_source_type.down.sql"

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
        cls.up = UP.read_text(encoding="utf-8")
        cls.down = DOWN.read_text(encoding="utf-8")

    def test_migration_files_exist(self):
        self.assertTrue(UP.is_file())
        self.assertTrue(DOWN.is_file())

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

    def test_scripts_are_transactional_and_rerunnable_by_contract(self):
        for script in (self.up, self.down):
            self.assertRegex(script.strip(), r"(?is)^begin\s*;")
            self.assertRegex(script.strip(), r"(?is)commit\s*;$")
        self.assertNotRegex(self.up, r"(?i)create\s+extension")
        self.assertNotRegex(self.up, r"(?i)create\s+table(?!\s+if\s+not\s+exists)")
        self.assertNotRegex(self.up, r"(?i)create\s+index(?!\s+if\s+not\s+exists)")

    def test_confirmation_idempotency_migration_is_scoped_and_reversible(self):
        up = CONFIRM_UP.read_text(encoding="utf-8")
        down = CONFIRM_DOWN.read_text(encoding="utf-8")
        self.assertIn("confirmation_idempotency_key", up)
        self.assertRegex(up, r"(?is)unique\s+index.*?organization_id\s*,\s*project_id\s*,\s*confirmation_idempotency_key")
        self.assertIn("DROP COLUMN IF EXISTS confirmation_idempotency_key", down)
        for script in (up, down):
            self.assertRegex(script.strip(), r"(?is)^begin\s*;.*commit\s*;$")

    def test_report_payload_migration_pins_full_inputs_and_is_reversible(self):
        up = REPORT_UP.read_text(encoding="utf-8")
        down = REPORT_DOWN.read_text(encoding="utf-8")
        self.assertIn("snapshot_payload jsonb", up)
        self.assertIn("resource_version_ids jsonb", up)
        self.assertRegex(up, r"(?i)alter column snapshot_payload set not null")
        self.assertIn("DROP COLUMN IF EXISTS snapshot_payload", down)
        for script in (up, down):
            self.assertRegex(script.strip(), r"(?is)^begin\s*;.*commit\s*;$")

    def test_snapshot_source_type_migration_adds_no_default_and_backfills_nothing(self):
        """The column must not be written into existing rows.

        progress_snapshot_refs carries a BEFORE UPDATE OR DELETE immutability trigger, so a
        backfilling UPDATE would be rejected outright. ADD COLUMN with no DEFAULT is a
        catalog-only change, which is why this migration can run at all -- and it is also
        the honest outcome: the rows already there have no recorded source.
        """
        up = SOURCE_UP.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS source_type text", up)
        self.assertNotIn("DEFAULT", up.upper().replace("NO DEFAULT", ""))
        self.assertNotIn("UPDATE progress_snapshot_refs", up)

    def test_snapshot_source_type_is_constrained_and_admits_unknown(self):
        up = SOURCE_UP.read_text(encoding="utf-8")
        self.assertIn("source_type IS NULL", up)
        for allowed in ("microsoft_project", "primavera", "manual", "other"):
            self.assertIn("'%s'" % allowed, up)
        # A filename extension is not evidence of a tool, so an unrecorded source stays
        # unrecorded rather than being labelled.
        self.assertNotIn(".mpp", up.lower().split("--")[0] if "--" in up else up.lower())

    def test_snapshot_source_type_migration_is_reversible_and_rerunnable(self):
        up, down = SOURCE_UP.read_text(encoding="utf-8"), SOURCE_DOWN.read_text(encoding="utf-8")
        for script in (up, down):
            self.assertTrue(script.strip().startswith("BEGIN;"))
            self.assertTrue(script.strip().endswith("COMMIT;"))
        self.assertIn("DROP CONSTRAINT IF EXISTS progress_snapshot_refs_source_type_check", down)
        self.assertIn("DROP COLUMN IF EXISTS source_type", down)
        # Re-runnable: the column guard is IF NOT EXISTS and the constraint guard is the
        # explicit pg_constraint lookup ADD CONSTRAINT cannot express.
        self.assertIn("IF NOT EXISTS", up)
        self.assertIn("pg_constraint", up)

    def test_the_rollback_drops_only_what_the_migration_added(self):
        down = SOURCE_DOWN.read_text(encoding="utf-8")
        self.assertNotIn("DROP TABLE", down.upper())
        self.assertNotIn("DELETE FROM", down.upper())
        self.assertNotIn("TRUNCATE", down.upper())

    def test_only_one_scoped_reversal_can_link_to_an_original(self):
        up = LINKED_UP.read_text(encoding="utf-8")
        down = LINKED_DOWN.read_text(encoding="utf-8")
        self.assertRegex(up, r"(?is)unique\s+index.*?organization_id\s*,\s*project_id\s*,\s*original_invoice_id.*?source\s*=\s*'reversal'")
        self.assertIn("DROP INDEX IF EXISTS ux_invoices_one_reversal_per_original", down)


if __name__ == "__main__":
    unittest.main()
