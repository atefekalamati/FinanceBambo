# -*- coding: utf-8 -*-
r"""Run one material price import, by hand, against a database named on the command line.

    python -m scripts.import_material_prices --dsn postgresql://... \
        --organization <uuid> --project <id> [--dry-run]

The sheet comes from `FINANCE_MATERIAL_PRICE_SHEET_URL` or `--sheet`. It is configuration,
never a request parameter: a caller who could name the sheet could point this at any sheet
at all.

WHAT IT REFUSES

Every database in `FORBIDDEN_DATABASES`, checked twice -- once against the DSN and once
against `current_database()` after connecting, because a tunnel can make anything answer on
loopback and a rule applied to a misread address reads as enforcement while enforcing
something else. Production is not among the databases this can be pointed at from here;
running against it is a separate, approved step.

`--dry-run` fetches and reads the workbook and reports what it WOULD write, without
connecting to a database at all.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.repositories.material_prices import PsycopgMaterialPriceRepository
from app.finance.services.material_price_import import (MaterialPriceImportError,
                                                        MaterialPriceImportService)
from app.finance.services.material_price_sheet import read_workbook, workbook_from_xlsx
from app.finance.services.google_sheet import fetch_sheet_as_xlsx

#: Never, on any host, for any reason. The production database is named here so that
#: pointing this script at it is not a typo away.
FORBIDDEN_DATABASES = frozenset({"bambo", "bambo_canonical_local", "bambo_canonical_test"})


class Scope:
    def __init__(self, organization_id, project_id, actor_user_id):
        self.organization_id = organization_id
        self.project_id = project_id
        self.actor_user_id = actor_user_id


def _selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def database_of(dsn):
    from urllib.parse import urlsplit

    if "://" in dsn:
        return (urlsplit(dsn).path or "").lstrip("/").split("?")[0] or None
    keywords = dict(part.split("=", 1) for part in dsn.split() if "=" in part)
    return keywords.get("dbname")


def refuse_protected(dsn):
    name = database_of(dsn)
    if name is None:
        raise SystemExit("STOP: the DSN names no database, so it cannot be checked.")
    if name in FORBIDDEN_DATABASES:
        raise SystemExit("STOP: %r is protected. Running an import against it is a "
                         "separate, approved step and never this script." % name)
    return name


async def dry_run(link):
    content = await fetch_sheet_as_xlsx(link)
    workbook = read_workbook(await asyncio.to_thread(workbook_from_xlsx, content))
    print("  worksheets read    : %d" % sum(1 for w in workbook.worksheets if w.read))
    print("  refused            : %s" % ([w.reason for w in workbook.refused] or "none"))
    print("  missing            : %s" % (list(workbook.missing_titles) or "none"))
    print("  outside allowlist  : %s" % (list(workbook.unknown_titles) or "none"))
    print("  complete           : %s" % workbook.complete)
    for w in workbook.worksheets:
        print("     %-34s rows=%-5d accepted=%-5d rejected=%d"
              % (w.title, len(w.rows), len(w.accepted), len(w.rejected)))
    print("  NOTHING WAS WRITTEN.")
    return 0


async def execute(dsn, scope, link):
    import psycopg
    from psycopg.rows import dict_row

    expected = refuse_protected(dsn)
    connection = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row,
                                                       autocommit=True)
    try:
        row = await (await connection.execute("SELECT current_database() AS d")).fetchone()
        if row["d"] != expected:
            raise SystemExit("STOP: the DSN said %r but the server answered %r."
                             % (expected, row["d"]))
        refuse_protected("dbname=" + row["d"])
        service = MaterialPriceImportService(
            PsycopgMaterialPriceRepository(connection), sheet_link=link)
        outcome = await service.run(scope)
    finally:
        await connection.close()

    print("  status            : %s" % outcome.status)
    print("  observations new  : %d" % outcome.inserted)
    print("  already present   : %d" % outcome.already_present)
    print("  rejected          : %d" % outcome.rejected)
    print("  run id            : %s" % outcome.run["id"])
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn")
    parser.add_argument("--organization")
    parser.add_argument("--project")
    parser.add_argument("--actor", default="00000000-0000-4000-8000-000000000000")
    parser.add_argument("--sheet", default=os.environ.get("FINANCE_MATERIAL_PRICE_SHEET_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.sheet:
        raise SystemExit("no sheet configured: set FINANCE_MATERIAL_PRICE_SHEET_URL or "
                         "pass --sheet")
    try:
        if args.dry_run:
            return asyncio.run(dry_run(args.sheet), loop_factory=_selector_loop)
        if not (args.dsn and args.organization and args.project):
            raise SystemExit("--dsn, --organization and --project are required unless "
                             "--dry-run is given")
        from uuid import UUID

        scope = Scope(UUID(args.organization), args.project, UUID(args.actor))
        return asyncio.run(execute(args.dsn, scope, args.sheet), loop_factory=_selector_loop)
    except MaterialPriceImportError as exc:
        print("  IMPORT REFUSED. The current prices are unchanged.")
        print("  %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
