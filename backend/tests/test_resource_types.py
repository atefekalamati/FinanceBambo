"""Three kinds, stated once, and the old two names read as one of them.

The merge of `labor` and `equipment` into `work` (0038) touched thirteen places in the
service. The risk of a change like that is the fourteenth: a list of kinds somebody
spells out again next year with four entries. So beyond the function's own behaviour,
this reads the source and refuses any module that enumerates the old vocabulary.
"""
import re
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.domain.resource_types import (LEGACY_WORK_TYPES, RESOURCE_TYPES,
                                               STORED_RESOURCE_TYPES, WORK,
                                               canonical_resource_type)


class CanonicalTypeTests(unittest.TestCase):
    def test_the_two_old_names_are_work(self):
        for old in LEGACY_WORK_TYPES:
            self.assertEqual(WORK, canonical_resource_type(old))

    def test_the_three_kinds_pass_through(self):
        for kind in RESOURCE_TYPES:
            self.assertEqual(kind, canonical_resource_type(kind))

    def test_an_unclassified_resource_is_not_quietly_work(self):
        self.assertIsNone(canonical_resource_type(None))

    def test_the_stored_vocabulary_is_the_kinds_plus_the_old_names(self):
        self.assertEqual(set(RESOURCE_TYPES) | set(LEGACY_WORK_TYPES), set(STORED_RESOURCE_TYPES))
        self.assertEqual(("material", "work", "general_cost"), RESOURCE_TYPES)


class NobodyEnumeratesFourKindsTests(unittest.TestCase):
    """No module under app/ or coreint/ lists the kinds with `labor` or `equipment` in it.

    The old names may still be MENTIONED -- a SQL `IN (...)` that admits stored rows, a
    feed that sends them, a comment -- so this looks specifically for a Python tuple or
    list literal that contains "material" together with either old name: the shape of a
    forgotten enumeration.
    """

    ENUMERATION = re.compile(r"""[\(\[][^\)\]\n]*["']material["'][^\)\]\n]*["'](labor|equipment)["']""")

    def test_no_forgotten_enumeration(self):
        offenders = []
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if path.name == "resource_types.py":
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if self.ENUMERATION.search(line):
                        offenders.append("%s:%d: %s" % (path.relative_to(BACKEND_ROOT), number, line.strip()))
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
