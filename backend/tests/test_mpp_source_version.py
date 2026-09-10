# -*- coding: utf-8 -*-
"""One project, one schedule — decided in one place and asked for by everyone.

Four services used to carry their own copy of "which source version is this project on".
The copies agreed, and that is exactly why it was dangerous: they would agree until one was
edited, and then the estimate would be priced from one file while the chart beside it read
progress from another, with neither answer saying so.

These run the real statement against a database, because what has to hold is a property of
the query and not of a docstring: it must be scoped to the project, refuse a version that
belongs to somebody else, prefer the newest READY one, and stay out of the way when a
caller names a version explicitly.
"""

import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.mpp_source_version import (SOURCE_VERSION_TABLE,
                                                   active_source_version,
                                                   active_source_version_for)

ORG = "org-1"
OTHER_ORG = "org-2"


def database():
    """A stand-in carrying the columns the rule reads, and two projects that share ids."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE %s (id TEXT, organization_id TEXT, project_id TEXT, "
               "status TEXT, imported_at TEXT)" % SOURCE_VERSION_TABLE)
    rows = [
        # terrace: an older ready version, a newer ready one, and a newer UNREADY one.
        ("v-old", ORG, "terrace", "ready", "2026-09-01T10:00"),
        ("v-new", ORG, "terrace", "ready", "2026-09-05T10:00"),
        ("v-importing", ORG, "terrace", "importing", "2026-09-09T10:00"),
        # another project of the same organisation, imported later than any of terrace's.
        ("v-other-project", ORG, "sample_site_01", "ready", "2026-09-20T10:00"),
        # the same project id under a different organisation.
        ("v-other-org", OTHER_ORG, "terrace", "ready", "2026-09-21T10:00"),
    ]
    db.executemany("INSERT INTO %s VALUES (?,?,?,?,?)" % SOURCE_VERSION_TABLE, rows)
    return db


def ask(db, organization=ORG, project="terrace"):
    sql = active_source_version(organization=":organization_id", project=":project_id")
    found = db.execute(sql, {"organization_id": organization, "project_id": project}).fetchone()
    return None if found is None else found[0]


class ActiveVersionTests(unittest.TestCase):
    def setUp(self):
        self.db = database()

    def test_the_newest_ready_version_of_this_project_is_the_active_one(self):
        self.assertEqual("v-new", ask(self.db))

    def test_a_version_still_importing_is_not_active_however_new_it_is(self):
        # It was imported last and is the wrong answer: its rows are not all written yet,
        # and half a schedule priced as a whole one is worse than yesterday's schedule.
        self.assertNotEqual("v-importing", ask(self.db))

    def test_another_project_never_answers_for_this_one(self):
        # `v-other-project` is the newest ready row in the table.
        self.assertEqual("v-new", ask(self.db))
        self.assertEqual("v-other-project", ask(self.db, project="sample_site_01"))

    def test_another_organisation_using_the_same_project_id_is_a_different_project(self):
        self.assertEqual("v-other-org", ask(self.db, organization=OTHER_ORG))

    def test_a_project_with_nothing_imported_has_no_active_version(self):
        self.assertIsNone(ask(self.db, project="a_project_with_no_schedule"))

    def test_every_caller_asks_the_same_question(self):
        # The four call sites differ only in how they spell the scope: a named parameter,
        # a positional one, or the columns of the row the subquery stands beside.
        named = active_source_version()
        positional = active_source_version(organization="%s", project="%s")
        correlated = active_source_version_for("l")
        for statement in (named, positional, correlated):
            self.assertIn("status = 'ready'", statement)
            self.assertIn("ORDER BY imported_at DESC, id DESC LIMIT 1", statement)
            self.assertIn(SOURCE_VERSION_TABLE, statement)
        self.assertIn("organization_id = l.organization_id", correlated)
        self.assertIn("project_id = l.project_id", correlated)
        self.assertTrue(correlated.startswith("(") and correlated.endswith(")"),
                        "the correlated form is a subquery and must be parenthesised")

    def test_naming_a_version_explicitly_does_not_go_through_the_ordering(self):
        # A report pinned to a version, or a baseline comparison, is not asking which file
        # is newest. `finance_progress._BY_ID` is that path; it is scoped and unordered.
        from coreint.finance_progress import _BY_ID
        self.assertIn("id = %(version_id)s", _BY_ID)
        self.assertIn("organization_id = %(organization_id)s", _BY_ID)
        self.assertIn("project_id = %(project_id)s", _BY_ID)
        self.assertNotIn("ORDER BY", _BY_ID)


if __name__ == "__main__":
    unittest.main()
