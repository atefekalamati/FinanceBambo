# -*- coding: utf-8 -*-
r"""Import the material price sheet into one scope of a local Finance test database.

    python -m scripts.ops.import_into_terrace --dsn postgresql://u@127.0.0.1:5432/bambo_canonical_test \
        --organization c4ee6a23-... --project terrace
    ... --apply

Dry run by default: it fetches the sheet, reads it through the real contract and reports
what it WOULD import, without opening a database connection at all. `--apply` runs the
import.

WHY THIS EXISTS BESIDE `scripts/import_material_prices.py`

That script refuses `bambo_canonical_test` by name, and that refusal is correct and is left
alone: it exists so an unattended run cannot reach the canonical test database. This script
is for the attended, reviewed case, and it reaches the same database by satisfying the same
checks explicitly -- not by turning that guard off. `bambo` and `bambo_canonical_local` are
refused here too, and no flag changes that.

IT GOES THROUGH THE APPLICATION SERVICE

`MaterialPriceImportService`, the same one the rest of the system uses, so every rule comes
with it: the workbook must be complete or nothing is written, a missing required header
refuses the whole worksheet by name, a blank price is stored as a rejected observation and
never as a zero, Toman becomes IRR by one multiplication, and re-running inserts nothing it
has already inserted. Bypassing it to write rows directly would be writing prices that
never passed any of that.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
from app.finance.services.google_sheet import fetch_sheet_as_xlsx
from app.finance.services.material_price_import import (MaterialPriceImportError,
                                                        MaterialPriceImportService)
from app.finance.services.material_price_sheet import read_workbook, workbook_from_xlsx
from scripts.ops._common import (CANONICAL_TEST, Refused, confirm_identity, dry_run_banner,
                                 refuse_protected, require_dsn, selector_loop)


class Scope:
    """The three attributes the repositories read. Supplied explicitly, never defaulted."""

    def __init__(self, organization_id, project_id, actor_user_id):
        self.organization_id = UUID(organization_id)
        self.project_id = project_id
        self.actor_user_id = UUID(actor_user_id)


async def preview(link):
    """Fetch and read the sheet. No database is opened, so nothing can be written."""
    content = await fetch_sheet_as_xlsx(link)
    workbook = read_workbook(await asyncio.to_thread(workbook_from_xlsx, content))
    print("   worksheets read   : %d" % sum(1 for w in workbook.worksheets if w.read))
    print("   refused           : %s" % ([w.reason for w in workbook.refused] or "none"))
    print("   missing           : %s" % (list(workbook.missing_titles) or "none"))
    print("   outside allowlist : %s" % (list(workbook.unknown_titles) or "none"))
    print("   complete          : %s" % workbook.complete)
    for w in workbook.worksheets:
        print("      %-34s rows %-5d accepted %-5d rejected %d"
              % (w.title, len(w.rows), len(w.accepted), len(w.rejected)))
    if not workbook.complete:
        # The same rule the importer applies, stated here so a dry run fails for the same
        # reason a real one would rather than looking fine and failing later.
        raise Refused("the workbook is incomplete. An import would write nothing and the "
                      "current prices would be unchanged.")
    return sum(len(w.rows) for w in workbook.worksheets)


async def execute(dsn, database, scope, link):
    connection = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row,
                                                       autocommit=True)
    try:
        # Asked of the server after connecting, not read off the DSN: a tunnel can make
        # anything answer on loopback.
        row = await (await connection.execute(
            "SELECT current_database() AS d, host(inet_server_addr()) AS h,"
            " inet_server_port() AS p, current_user AS u,"
            " current_setting('server_version') AS v")).fetchone()
        print("   %s | %s:%s | user %s | PostgreSQL %s"
              % (row["d"], row["h"], row["p"], row["u"], row["v"]))
        if row["d"] != database:
            raise Refused("expected %r, the server answered %r." % (database, row["d"]))
        refuse_protected("dbname=" + row["d"], action="import into")
        if row["h"] not in ("127.0.0.1", "::1"):
            raise Refused("%r is not loopback." % row["h"])

        before = await (await connection.execute(
            "SELECT count(*) AS n FROM price_observations WHERE project_id=%s",
            (scope.project_id,))).fetchone()
        elsewhere_before = await (await connection.execute(
            "SELECT count(*) AS n FROM price_observations WHERE project_id <> %s",
            (scope.project_id,))).fetchone()
        print("   observations in %s before : %d" % (scope.project_id, before["n"]))

        service = MaterialPriceImportService(
            PsycopgMaterialPriceRepository(connection), sheet_link=link)
        outcome = await service.run(scope)

        after = await (await connection.execute(
            "SELECT count(*) AS n FROM price_observations WHERE project_id=%s",
            (scope.project_id,))).fetchone()
        elsewhere_after = await (await connection.execute(
            "SELECT count(*) AS n FROM price_observations WHERE project_id <> %s",
            (scope.project_id,))).fetchone()

        print()
        print("   status          : %s" % outcome.status)
        print("   inserted        : %d" % outcome.inserted)
        print("   already present : %d" % outcome.already_present)
        print("   rejected        : %d" % outcome.rejected)
        print("   run id          : %s" % outcome.run["id"])
        print("   observations in %s after : %d" % (scope.project_id, after["n"]))
        print("   observations in every OTHER scope : %d -> %d"
              % (elsewhere_before["n"], elsewhere_after["n"]))
        if elsewhere_after["n"] != elsewhere_before["n"]:
            raise Refused("an import changed rows outside its own scope. That should be "
                          "impossible; investigate before trusting this run.")
    finally:
        await connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="target DSN; or set FINANCE_OPS_DSN")
    parser.add_argument("--database", default=CANONICAL_TEST,
                        help="the database the DSN must reach (default: %s)" % CANONICAL_TEST)
    parser.add_argument("--organization", help="organization uuid")
    parser.add_argument("--project", help="project id, for example terrace")
    parser.add_argument("--actor", default="00000000-0000-4000-8000-000000000000",
                        help="the uuid recorded as having run this import")
    parser.add_argument("--sheet", default=os.environ.get("FINANCE_MATERIAL_PRICE_SHEET_URL"),
                        help="sheet link; or set FINANCE_MATERIAL_PRICE_SHEET_URL")
    parser.add_argument("--apply", action="store_true",
                        help="actually import (default: dry run, no database opened)")
    arguments = parser.parse_args(argv)

    if not arguments.sheet:
        raise Refused("no sheet configured. Pass --sheet or set "
                      "FINANCE_MATERIAL_PRICE_SHEET_URL.")

    print("### the sheet ###")
    try:
        rows = asyncio.run(preview(arguments.sheet), loop_factory=selector_loop)
    except MaterialPriceImportError as exc:
        raise Refused(str(exc))

    print()
    if not dry_run_banner(arguments.apply):
        print("   %d rows would be imported. Re-run with --apply, after a backup." % rows)
        return 0

    dsn = require_dsn(arguments.dsn, "FINANCE_OPS_DSN", "target DSN")
    refuse_protected(dsn, action="import into")
    if not (arguments.organization and arguments.project):
        raise Refused("--organization and --project are required with --apply.")

    print()
    print("### target ###")
    scope = Scope(arguments.organization, arguments.project, arguments.actor)
    try:
        asyncio.run(execute(dsn, arguments.database, scope, arguments.sheet),
                    loop_factory=selector_loop)
    except MaterialPriceImportError as exc:
        print("   IMPORT REFUSED. The current prices are unchanged.")
        print("   %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
