# -*- coding: utf-8 -*-
r"""TEST_ONLY -- DISPOSABLE. Is this fixture one the seed script will accept?

Answers that by calling the seed script's OWN checks rather than reimplementing them --
`check_resources` and `summarise` need no connection, so the compatibility claim is tested
against the real code instead of against a copy of it that can drift.

What it cannot answer without a database: whether every `task_uid` exists in `msp_tasks`
for the target snapshot. That check is `check_tasks`, it needs the server, and it is the
one most likely to refuse -- see README.md.

    ..\..\..\.venv312\Scripts\python check_fixture.py fixture.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.test_only.seed_msp_resource_assignments import (  # noqa: E402
    ASSIGNMENT_COLUMNS, RESOURCE_COLUMNS, Refused, check_resources, summarise)


def floats_in(node, path="fixture"):
    """Every float in the document, with its path.

    Money and quantities travel as strings so nothing passes through binary floating point
    on its way to a `numeric` column. A float here is a real defect, not a style point.
    """
    if isinstance(node, float):
        return [path]
    if isinstance(node, dict):
        return [hit for key, value in node.items()
                for hit in floats_in(value, "%s.%s" % (path, key))]
    if isinstance(node, list):
        return [hit for index, value in enumerate(node)
                for hit in floats_in(value, "%s[%d]" % (path, index))]
    return []


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    path = Path((argv or sys.argv[1:])[0])
    fixture = json.loads(path.read_text(encoding="utf-8"))
    resources, assignments = fixture["resources"], fixture["assignments"]
    problems = []

    print("\n  checking %s against seed_msp_resource_assignments.py\n" % path.name)

    # 1. Keys the seed script indexes directly. It does `row["resource_uid"]`, not
    #    `row.get(...)`, so an absent key is a KeyError in the middle of a run rather than a
    #    refusal at the start.
    for label, rows, required in (("resource", resources, ("resource_uid",)),
                                  ("assignment", assignments,
                                   ("assignment_uid", "task_uid", "resource_uid"))):
        for index, row in enumerate(rows):
            missing = [key for key in required if key not in row]
            if missing:
                problems.append("%s[%d] has no %s" % (label, index, ", ".join(missing)))
    print("  required keys present              %s"
          % ("no -- %d row(s)" % len(problems) if problems else "yes"))

    # 2. Unknown keys. Harmless -- the insert reads a fixed column list -- but a
    #    misspelling would otherwise be silently dropped and the column left null.
    known_resource = set(RESOURCE_COLUMNS) | {"raw_fields_json"}
    known_assignment = set(ASSIGNMENT_COLUMNS) | {"raw_fields_json"}
    stray = ({key for row in resources for key in row} - known_resource) | \
            ({key for row in assignments for key in row} - known_assignment)
    print("  keys the seed script would ignore   %s" % (sorted(stray) or "none"))

    # 3. Columns that would be inserted null everywhere, which is worth seeing: it is
    #    either a field this MPP does not carry or one the probe forgot to map.
    for label, rows, columns in (("resource", resources, RESOURCE_COLUMNS),
                                 ("assignment", assignments, ASSIGNMENT_COLUMNS)):
        empty = [c for c in columns if all(row.get(c) is None for row in rows)]
        print("  %-11s columns always null      %s" % (label, ", ".join(empty) or "none"))

    # 4. No floats.
    floats = floats_in(fixture)
    print("  float values (must be none)        %s"
          % ("%d, first at %s" % (len(floats), floats[0]) if floats else "none"))
    if floats:
        problems.append("%d float value(s)" % len(floats))

    # 5. The seed script's own integrity and summary checks, verbatim.
    print("\n  --- the seed script's own checks ---")
    try:
        check_resources(resources, assignments)
        summarise(resources, assignments)
        print("\n  seed script checks                 passed")
    except Refused as refusal:
        print("\n  seed script checks                 REFUSED")
        print("  %s" % refusal)
        problems.append("seed script refused the fixture")

    print("\n  %s" % ("COMPATIBLE -- the remaining check needs a database (see README)."
                      if not problems else
                      "NOT COMPATIBLE: %s" % "; ".join(problems[:5])))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
