# -*- coding: utf-8 -*-
"""The preflight has to stay true to the migrations, not just exist.

A checklist written once and never updated is worse than none: it reports "ready" while the
chain has grown a dependency nobody re-checked, and the operator finds out eight revisions
into a production upgrade. So the interesting test is not "does the tool print something" --
it is "does its list of Core prerequisites still match what the migrations actually declare".

That list is derived here from the DDL itself, the same way it was derived by hand when the
tool was written: a Core table is one a Finance revision REFERENCES or joins and does NOT
create for itself. If somebody adds a revision touching a new Core table, this fails and the
preflight has to be taught about it before the release.
"""

import re
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.install_preflight import (CORE_REQUIREMENTS, TASK_ID_TYPES, repository_head)

VERSIONS = BACKEND_ROOT / "alembic" / "versions"
PREFLIGHT = (BACKEND_ROOT / "scripts" / "install_preflight.py").read_text(encoding="utf-8")

#: Core's namespace inside the shared database. Finance's own tables are `finance_*`,
#: `estimate_*`, `invoice*`, `price_*`, `progress_*`, `report_*` and `unit_conversions`.
CORE_NAMESPACE = re.compile(r"\bmsp_[a-z_]+\b")


def migration_sources():
    for path in sorted(VERSIONS.glob("*.py")):
        yield path.name, path.read_text(encoding="utf-8")


def core_tables_finance_depends_on():
    """Core tables the DDL reaches for and does not create itself."""
    created, referenced = set(), set()
    for _name, text in migration_sources():
        created.update(CORE_NAMESPACE.findall(
            " ".join(re.findall(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)", text, re.I))))
        for clause in re.findall(r"REFERENCES\s+(\w+)\s*\(", text, re.I):
            referenced.update(CORE_NAMESPACE.findall(clause))
        for clause in re.findall(r"(?:JOIN|FROM)\s+(\w+)", text, re.I):
            referenced.update(CORE_NAMESPACE.findall(clause))
    return referenced - created


class PrerequisiteContractTests(unittest.TestCase):
    def test_the_preflight_lists_exactly_the_core_tables_the_migrations_need(self):
        derived = core_tables_finance_depends_on()
        declared = {table for table, _why in CORE_REQUIREMENTS}
        self.assertEqual(derived, declared,
                         "the migrations and the preflight disagree about Core prerequisites")

    def test_tables_finance_creates_itself_are_not_demanded_of_the_host(self):
        """`msp_resources` and `msp_resource_assignments` are Finance's own, from 0007.

        Listing them as prerequisites would send an operator to ask the host team for
        something this repository already installs, and the install would never start.
        """
        created = set()
        for _name, text in migration_sources():
            created.update(CORE_NAMESPACE.findall(
                " ".join(re.findall(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)",
                                    text, re.I))))
        self.assertIn("msp_resources", created, "0007 no longer creates its own tables")
        for table, _why in CORE_REQUIREMENTS:
            with self.subTest(table=table):
                self.assertNotIn(table, created)

    def test_every_prerequisite_says_which_revision_needs_it(self):
        """A bare table name gives an operator nothing to verify against."""
        for table, why in CORE_REQUIREMENTS:
            with self.subTest(table=table):
                self.assertRegex(why, r"\b00\d\d\b", "the reason names no revision")

    def test_the_foreign_key_type_the_preflight_accepts_matches_the_column_it_protects(self):
        text = (VERSIONS / "0009_finance_task_resource_map.py").read_text(encoding="utf-8")
        declared = re.search(r"task_id\s+(\w+)\s+NOT NULL", text)
        self.assertIsNotNone(declared, "0009 no longer declares task_id the same way")
        self.assertIn(declared.group(1).lower(), TASK_ID_TYPES,
                      "the preflight would accept a Core type the foreign key cannot use")


class HeadTests(unittest.TestCase):
    def test_the_head_is_read_from_the_files_and_is_single(self):
        heads, count = repository_head()
        self.assertEqual(1, len(heads), "a branched chain cannot be installed: %s" % heads)
        self.assertEqual(count, len(list(VERSIONS.glob("*.py"))))
        # Not asserted as a constant: the point is that it is derived, so the release notes
        # and the installer cannot disagree with the repository about where head is.
        self.assertRegex(heads[0], r"^\d{4}$")


class ReadOnlyTests(unittest.TestCase):
    """A tool an operator is invited to run against production must not be able to write."""

    def test_it_opens_a_read_only_transaction(self):
        self.assertIn('db.execute("SET TRANSACTION READ ONLY")', PREFLIGHT)

    def test_every_statement_it_executes_is_a_read(self):
        """Checked against what is actually EXECUTED, not against the file's prose.

        The advice it prints contains the words GRANT and `alembic upgrade head` -- telling
        an operator what to do next is the tool's whole job. What must never appear is a
        statement it runs itself, so the syntax tree is walked and every `.execute()`
        argument is read. A statement built at run time fails too: this can only vouch for
        SQL it can see.
        """
        import ast
        executed = []
        for node in ast.walk(ast.parse(PREFLIGHT)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute" and node.args):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    executed.append(" ".join(first.value.split()))
                else:
                    self.fail("a statement is built rather than written out: %s"
                              % ast.unparse(first)[:60])
        self.assertGreaterEqual(len(executed), 6, "almost no statements were examined")
        for statement in executed:
            with self.subTest(statement=statement[:60]):
                head = statement.upper()
                self.assertTrue(head.startswith("SELECT")
                                or head.startswith("SET TRANSACTION READ ONLY"),
                                "not a read: %s" % statement[:80])


if __name__ == "__main__":
    unittest.main()
