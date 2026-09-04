# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL DEVELOPMENT. Run devhost against bambo_canonical_test as the real admin.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.run_devhost_terrace

THE PROBLEM THIS SOLVES

A finance request answered:

    {"error": {"code": "FINANCE_FORBIDDEN", "message": "project membership is required"}}

while `project_memberships` plainly held the row. Both statements were true, because the
message did not come from the database at all.

`devhost.wire` only installs the Core adapters when `FINANCE_CORE_DSN` is set. Without it
the host wires `SingleTenantScopeAuthorizer(seed.ORGANIZATION_ID, seed.PROJECT_ID)`, which
grants membership for exactly one hardcoded project -- `sample_site_01` -- and refuses
everything else with:

    raise HTTPException(403, "project membership is required")

That is the identical sentence `CoreScopeAuthorizer` uses when a real membership is missing.
So a request for `terrace` was refused by a fixture that never opened a connection, and the
error read as a data problem. `.env` sets FINANCE_DEV_DSN and FINANCE_MIGRATION_DSN but not
FINANCE_CORE_DSN, so this was the state on every run.

THE FIX IS CONFIGURATION, NOT CODE

Nothing here patches anything. It sets the four settings devhost already reads, then hands
off to `python -m devhost`:

    FINANCE_CORE_DSN              -> use Core's tables for membership/roles/permissions
    FINANCE_DEMO_USER_ID          -> which real person the host stands in for
    FINANCE_DEMO_ORGANIZATION_ID  -> that person's organization
    FINANCE_DEMO_PROJECT_ID       -> the project the injected browser context names

Naming a user grants them nothing: every gate still asks Core about whoever is named, which
is exactly what a real host session does.

SEEDING STAYS OFF. `seeding_allowed()` needs APP_ENV to name a seedable environment AND
FINANCE_ALLOW_SEED to say yes; the second is unset and this script never sets it. Demo
fixtures must not land in a database holding real project data.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DATABASE = "bambo_canonical_test"
DSN = "postgresql://postgres@127.0.0.1:5432/%s" % DATABASE

#: The identity the host stands in for. Read from the database below before use, so a typo
#: fails with "no such user" rather than with the 403 this script exists to explain.
USER_ID = "53a1ac1b-d87f-4125-9ba9-a7d64166af88"
ORGANIZATION_ID = "c4ee6a23-b2a8-4afe-94c8-63baba552ca4"
PROJECT_ID = "terrace"

#: Refused outright. This launcher points a *development* host at a database, and neither of
#: these may ever be that database.
FORBIDDEN = frozenset({"bambo", "bambo_canonical_local"})


def redacted(dsn):
    parts = urlsplit(dsn)
    return "%s/%s" % (parts.hostname or "?", (parts.path or "").lstrip("/"))


def verify(dsn):
    """Prove the identity exists and the gates will pass, before starting anything.

    Runs the same two queries `CoreScopeAuthorizer` runs. If they fail here, they would
    have failed as a 403 in the browser with nothing saying why.
    """
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as connection:
        row = connection.execute("SELECT current_database() AS database").fetchone()
        if row["database"] in FORBIDDEN:
            raise SystemExit("STOP: %r is not a database a development host may use."
                             % row["database"])
        print("  database                      %s" % row["database"])

        checks = (
            ("user exists",
             "SELECT email FROM users WHERE id = %(user)s", "email"),
            ("organization membership",
             "SELECT role FROM organization_memberships "
             "WHERE user_id = %(user)s AND organization_id = %(org)s", "role"),
            ("project membership",
             "SELECT membership.role FROM project_memberships AS membership "
             "JOIN projects AS project ON project.id = membership.project_id "
             "WHERE membership.user_id = %(user)s AND membership.project_id = %(project)s "
             "AND project.organization_id = %(org)s", "role"),
        )
        failed = []
        for label, sql, column in checks:
            found = connection.execute(sql, {"user": USER_ID, "org": ORGANIZATION_ID,
                                             "project": PROJECT_ID}).fetchone()
            print("  %-29s %s" % (label, found[column] if found else "NOT FOUND"))
            if found is None:
                failed.append(label)

        version = connection.execute(
            "SELECT version_num FROM finance_alembic_version").fetchone()
        print("  finance_alembic_version       %s"
              % (version["version_num"] if version else "MISSING"))
        if version is None:
            failed.append("finance schema")

        counts = connection.execute("""
            SELECT (SELECT count(*) FROM msp_snapshots) AS snapshots,
                   (SELECT count(*) FROM msp_tasks) AS tasks,
                   (SELECT count(*) FROM msp_resource_assignments) AS assignments,
                   (SELECT count(*) FROM estimate_lines WHERE deleted_at IS NULL) AS lines
        """).fetchone()
        print("  msp snapshots / tasks         %s / %s"
              % (counts["snapshots"], counts["tasks"]))
        print("  msp assignments               %s%s"
              % (counts["assignments"],
                 "  (empty: the feed falls back to task percentages)"
                 if not counts["assignments"] else ""))
        print("  estimate lines                %s%s"
              % (counts["lines"],
                 "  (empty: a live report will have no financial items)"
                 if not counts["lines"] else ""))

    if failed:
        raise SystemExit("STOP: %s. Fix the data before starting the host."
                         % ", ".join(failed))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--check-only", action="store_true",
                        help="run the preflight and stop")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  LOCAL DEVELOPMENT HOST -- Core adapters against %s\n" % DATABASE)
    print("  target                        %s" % redacted(arguments.dsn))
    verify(arguments.dsn)

    environment = dict(
        os.environ,
        # Both point at the same database here because this one carries both schemas. They
        # stay separate settings because Core and Finance are separate schemas owned by
        # separate teams and may well be separate databases.
        FINANCE_DEV_DSN=arguments.dsn,
        FINANCE_CORE_DSN=arguments.dsn,
        FINANCE_DEMO_USER_ID=USER_ID,
        FINANCE_DEMO_ORGANIZATION_ID=ORGANIZATION_ID,
        FINANCE_DEMO_PROJECT_ID=PROJECT_ID,
        # A SEPARATE switch from FINANCE_CORE_DSN, and easy to miss. That one wires
        # membership, roles and permissions to Core; progress stays on the seeded feed
        # until this is on, because in production the assignment-level quantities come
        # from the host's progress module rather than from Core.
        #
        # Without it every report answered 404 "progress snapshot not found for reporting
        # date" even though the Core adapter, called directly, returned all 1248 rows for
        # snapshot 38 -- the seeded feed simply knows nothing about `terrace`.
        FINANCE_CORE_PROGRESS="on",
    )
    # Removed rather than overridden: `build()` connects the owner role only to decide
    # whether to seed, and this database holds real project data. Absent means it cannot.
    environment.pop("FINANCE_MIGRATION_DSN", None)
    environment.pop("FINANCE_ALLOW_SEED", None)

    print("\n  standing in for                admin@bambo.local / %s" % PROJECT_ID)
    print("  seeding                       disabled (no FINANCE_MIGRATION_DSN, "
          "no FINANCE_ALLOW_SEED)")
    print("  serving on                    http://%s:%s\n" % (arguments.host,
                                                              arguments.port))
    if arguments.check_only:
        print("  --check-only: not starting the host.")
        return 0

    return subprocess.call(
        [sys.executable, "-m", "devhost", "--dsn", arguments.dsn,
         "--port", str(arguments.port), "--host", arguments.host],
        cwd=str(BACKEND_ROOT), env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
