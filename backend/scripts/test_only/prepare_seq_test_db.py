# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL DEVELOPMENT. Build the disposable database the invoice-numbering
and pagination tests ask questions of.

    ..\..\ai-extraction-env\Scripts\python -m scripts.test_only.prepare_seq_test_db

WHY A DATABASE OF ITS OWN

Two of the claims in this work cannot be checked against a double, because what is being
claimed is a property of PostgreSQL rather than of this code:

  * two transactions allocating an invoice number at the same moment get different
    numbers, and the second waits for the first rather than reading a stale counter;
  * walking every page of an append-only listing returns every row exactly once.

Both need a real server. None of the existing local databases may be used for them: the
presentation database is read-only for this work, and the demo database belongs to
`scripts.demo.prepare`, which owns what is in it. So this creates and owns its own, and
the name is checked on both sides -- here before writing and in the tests before reading.

WHAT IT DOES

  1. Drops and recreates `bambo_invoice_seq_test`, and nothing else, on 127.0.0.1.
  2. Applies the Core mirror schema, because revision 0009 declares a foreign key to
     `msp_tasks` and will not run without it.
  3. `alembic upgrade head`.
  4. Loads `devhost/seed.sql` -- the same fixtures the development host uses.

It refuses to run against any other database name, and it never connects to a host that
is not the loopback address.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                        # noqa: E402
from psycopg.rows import dict_row                                     # noqa: E402

DATABASE = "bambo_invoice_seq_test"
HOST = "127.0.0.1"
PORT = 5432
DSN = f"postgresql://postgres@{HOST}:{PORT}/{DATABASE}"
MAINTENANCE = f"postgresql://postgres@{HOST}:{PORT}/postgres"
MIRROR_SQL = BACKEND_ROOT / "scripts" / "demo" / "core_mirror.sql"


def say(label, value=""):
    print(f"  {label:<28} {value}")


def recreate():
    """Drop and create the one database this script is allowed to name."""
    with psycopg.connect(MAINTENANCE, autocommit=True, connect_timeout=5) as admin:
        with admin.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT host(inet_server_addr()) AS host")
            host = cursor.fetchone()["host"]
        if host != HOST:
            raise SystemExit(f"refusing to write: the server answering is {host}, not {HOST}")
        admin.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{DATABASE}"')
    say("database recreated", DATABASE)


def apply_core_mirror():
    """Revision 0009 references `msp_tasks`; without the mirror the chain stops there."""
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as connection:
        connection.execute(MIRROR_SQL.read_text(encoding="utf-8"))
    say("core mirror applied", MIRROR_SQL.name)


def migrate():
    """`alembic upgrade head`, in a subprocess with the DSN passed by environment."""
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=BACKEND_ROOT, capture_output=True, text=True,
                            env=dict(os.environ, FINANCE_MIGRATION_DSN=DSN))
    if result.returncode != 0:
        raise SystemExit("alembic upgrade failed; re-run it directly to see the error")
    for line in result.stderr.splitlines():
        if "Running upgrade" in line:
            say("alembic", line.split("Running upgrade")[-1].strip()[:70])


async def seed():
    from devhost import database
    async with await psycopg.AsyncConnection.connect(
            DSN, autocommit=True, row_factory=dict_row, connect_timeout=10) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT current_database() AS db, host(inet_server_addr()) AS host")
            server = await cursor.fetchone()
        if (server["db"], server["host"]) != (DATABASE, HOST):
            raise SystemExit(f'refusing to write: {server["host"]}/{server["db"]}')
        # The Core mirror rows as well as its schema: the four authorization gates read
        # membership from these tables, so without them every request to the development
        # host is refused before it reaches anything this database was built to show.
        from scripts.demo import seed_core_mirror
        counts = await seed_core_mirror.apply(connection)
        say("core mirror rows", ", ".join(
            "%s=%s" % (table, count) for table, count in counts.items() if count))
        await database.load_seed(connection)
        async with connection.cursor(row_factory=dict_row) as cursor:
            for table in ("invoices", "price_versions", "unit_conversions",
                          "finance_invoice_counters"):
                await cursor.execute(f"SELECT count(*) AS n FROM {table}")
                say(table, (await cursor.fetchone())["n"])


def _loop_factory():
    # psycopg's async driver cannot run on Windows' default ProactorEventLoop, the same
    # way `scripts.demo.prepare` handles it.
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def main():
    say("target", f"{HOST}:{PORT}/{DATABASE}")
    recreate()
    apply_core_mirror()
    migrate()
    asyncio.run(seed(), loop_factory=_loop_factory)
    print("\n  disposable database ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
