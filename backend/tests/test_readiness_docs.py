import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class DeclaredDependencyTests(unittest.TestCase):
    """Whatever the suite needs must be written down somewhere installable.

    This exists because it was not. The tests passed for months only because pytest,
    httpx and psycopg's binary libpq happened to be installed globally on one machine; in
    a fresh virtual environment `python -m pytest` failed outright, first on pytest and
    then on "no pq wrapper available" during collection. Nothing caught it, because the
    machine that ran the suite was the machine that had the packages.
    """

    def _declared(self):
        """Requirement lines only.

        Comments are excluded deliberately: the first version of this check read the whole
        file, so commenting a requirement out still satisfied it. A mutation check caught
        that, which is the only reason it is written this way.
        """
        requirements = set()
        for name in ("requirements.txt", "requirements-test.txt", "devhost/requirements.txt"):
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    requirements.add(line)
        return requirements

    @staticmethod
    def _package(requirement):
        return requirement.split("==")[0].split(">=")[0].split("[")[0].strip().lower()

    def test_the_suite_can_be_installed_from_the_repository(self):
        for name in ("requirements.txt", "requirements-test.txt"):
            self.assertTrue((ROOT / name).exists(), name + " is missing")
        declared = self._declared()
        # pytest runs the suite; psycopg's binary wheel is what makes a repository module
        # importable on a machine with no system libpq; httpx is what starlette's
        # TestClient uses, so every API-level test needs it even though none imports it.
        for requirement in ("pytest", "httpx", "psycopg[binary]"):
            self.assertTrue(any(entry.startswith(requirement) for entry in declared),
                            requirement + " is not declared as a requirement")

    def test_test_tooling_stays_out_of_the_runtime_list(self):
        """The finance module is a library: requirements.txt is what a host installs."""
        runtime = {self._package(line.split("#", 1)[0])
                   for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
                   if line.split("#", 1)[0].strip()}
        for tool in ("pytest", "httpx", "uvicorn"):
            self.assertNotIn(tool, runtime, tool + " must not be in the runtime list")

    def test_every_third_party_module_the_tests_import_is_declared(self):
        """Catches the next undeclared dependency, not just this one.

        Indirect needs still slip through -- httpx is reached through starlette, so no
        import statement names it -- which is why it is asserted by name above.
        """
        import ast
        declared = {self._package(entry) for entry in self._declared()}
        first_party = {"app", "devhost", "persian_calendar_golden"}
        undeclared = set()
        for path in sorted((ROOT / "tests").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    root = name.split(".")[0]
                    if not root or root in first_party or root in sys.stdlib_module_names:
                        continue
                    if root.lower() not in declared:
                        undeclared.add("%s (imported by %s)" % (root, path.name))
        self.assertEqual(set(), undeclared)


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
