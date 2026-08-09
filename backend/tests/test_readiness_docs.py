import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class ReadinessDocumentationTests(unittest.TestCase):
    def test_review_package_lists_every_migration(self):
        review=(ROOT/"docs"/"PRODUCTION_MIGRATION_REVIEW_FA.md").read_text(encoding="utf-8")
        for migration in sorted((ROOT/"migrations").glob("*.up.sql")):
            self.assertIn(migration.name,review)

    def test_recovery_runbook_separates_restore_and_destructive_down(self):
        runbook=(ROOT/"docs"/"RECOVERY_RUNBOOK_FA.md").read_text(encoding="utf-8")
        self.assertIn("pg_dump --format=custom",runbook)
        self.assertIn("pg_restore --exit-on-error",runbook)
        self.assertIn("تمام جدول‌های مالی را حذف می‌کند",runbook)
        self.assertIn("BLOCKED",runbook)

    def test_review_does_not_claim_environment_pass(self):
        review=(ROOT/"docs"/"PRODUCTION_MIGRATION_REVIEW_FA.md").read_text(encoding="utf-8")
        self.assertIn("PostgreSQL 16 | BLOCKED",review)
        self.assertIn("PostgreSQL 18 | BLOCKED",review)


if __name__=="__main__":unittest.main()
