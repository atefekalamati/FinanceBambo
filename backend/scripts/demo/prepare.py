# -*- coding: utf-8 -*-
"""Build the local integration demo database from nothing, in one command.

    python -m scripts.demo.prepare            # create if absent, then bring it up to date
    python -m scripts.demo.prepare --recreate # drop it first

WHAT IT DOES, AND WHY IN THIS ORDER
  1. Prove the target is the local disposable demo database. Twice: once by reading the
     connection string, once by asking the server that answers. Nothing below runs until
     both agree.
  2. Create the database if it is not there.
  3. `alembic upgrade head` -- the only way the Finance schema is ever created. There is no
     second code path that writes Finance DDL, so the demo database and a real one are
     built by the same six revisions.
  4. Apply the Core mirror DDL, which is generated from the real Core schema export.
  5. Fill the mirror with synthetic demo rows.
  6. Load the Finance development fixtures.

Steps 4-6 are demo data. Step 3 is schema. They are kept visibly separate because that is
the distinction production depends on: a deployed environment runs step 3 and must never
run steps 4-6.

CREDENTIALS
None are written here, and none are needed for the default target: a local PostgreSQL that
trusts loopback connections. `FINANCE_DEMO_DSN` overrides the default if a password is
required, and is read from the environment so it never reaches the repository. Nothing in
this file prints a connection string.

THE MAIN DATABASE IS NEVER TOUCHED
Not read, not written, not connected to. `scripts.demo.target` refuses its host and its
database by name, and every step here goes through that gate.
"""

import argparse
import asyncio
import os
import selectors
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                          # noqa: E402
from psycopg.rows import dict_row                                       # noqa: E402

from devhost.environment import demo_port                               # noqa: E402
from scripts.demo import seed_core_mirror                               # noqa: E402
from scripts.demo.target import (DEMO_DATABASE, DEMO_HOST, DEMO_PORT,   # noqa: E402
                                 MAINTENANCE_DATABASE, UnsafeTarget,
                                 assert_dsn_targets_demo, assert_server_is_demo)

MIRROR_SQL = Path(__file__).resolve().parent / "core_mirror.sql"

#: The local default: loopback, no password, the approved demo database. Overridable with
#: FINANCE_DEMO_DSN for a local server that requires authentication.
DEFAULT_DSN = f"postgresql://postgres@{DEMO_HOST}:{DEMO_PORT}/{DEMO_DATABASE}"


def demo_dsn() -> str:
    return os.environ.get("FINANCE_DEMO_DSN") or DEFAULT_DSN


def maintenance_dsn(dsn: str) -> str:
    return dsn.replace(f"/{DEMO_DATABASE}", f"/{MAINTENANCE_DATABASE}")


def say(step: str, detail: str = "") -> None:
    print(f"  {step:<44} {detail}")


def ensure_database(dsn: str, recreate: bool) -> None:
    """Create the demo database, dropping it first when asked.

    Runs against the maintenance database, because CREATE DATABASE cannot be issued from
    inside the database being created. That is the only reason `allow_maintenance` exists,
    and it widens the database check alone -- host and port are still pinned.
    """
    admin = maintenance_dsn(dsn)
    assert_dsn_targets_demo(admin, allow_maintenance=True)
    with psycopg.connect(admin, autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        server = assert_server_is_demo(connection, allow_maintenance=True)
        say("server", server["version"].split(" on ")[0])
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DEMO_DATABASE,)).fetchone()
        if exists and recreate:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (DEMO_DATABASE,))
            connection.execute(f'DROP DATABASE "{DEMO_DATABASE}"')
            say("dropped", DEMO_DATABASE)
            exists = None
        if not exists:
            connection.execute(f'CREATE DATABASE "{DEMO_DATABASE}"')
            say("created", DEMO_DATABASE)
        else:
            say("database already present", DEMO_DATABASE)


def migrate(dsn: str) -> str:
    """`alembic upgrade head`, in a subprocess with the DSN passed by environment.

    A subprocess rather than an in-process call so this runs the same command an operator
    would, and so nothing Alembic imports can end up sharing a connection with the steps
    that follow.
    """
    environment = dict(os.environ, FINANCE_MIGRATION_DSN=dsn)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=BACKEND_ROOT, capture_output=True, text=True,
                            env=environment)
    if result.returncode != 0:
        # The DSN can appear in a driver error, so nothing captured is echoed verbatim.
        raise SystemExit("alembic upgrade failed; re-run it directly to see the error")
    return result.stdout


async def build(dsn: str) -> None:
    async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, row_factory=dict_row, connect_timeout=10) as connection:
        # Gate 2 again, on the connection that is about to write. The one in
        # `ensure_database` proved a different connection to a different database.
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""
                SELECT current_database() AS database, host(inet_server_addr()) AS host,
                       inet_server_port() AS port, current_user AS usr, version() AS version
            """)
            server = await cursor.fetchone()
        if (server["database"] != DEMO_DATABASE or server["host"] != DEMO_HOST
                or int(server["port"]) != DEMO_PORT):
            raise UnsafeTarget(
                f'refusing to write: the server answering is {server["host"]}/{server["database"]}')
        say("write target confirmed", f'{server["host"]}:{server["port"]}/{server["database"]}')

        await connection.execute(MIRROR_SQL.read_text(encoding="utf-8"))
        say("core mirror schema applied", f"{MIRROR_SQL.name}")

        counts = await seed_core_mirror.apply(connection)
        say("core mirror rows", ", ".join(
            f"{table}={count}" for table, count in counts.items() if count))

        from devhost import database
        await database.reset(connection)
        await database.load_seed(connection)
        say("finance fixtures loaded", "devhost/seed.sql")

        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT version_num FROM finance_alembic_version")
            version = await cursor.fetchone()
            await cursor.execute("""
                SELECT count(*) AS tables FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            tables = await cursor.fetchone()
        say("finance_alembic_version", version["version_num"] if version else "MISSING")
        say("public tables", str(tables["tables"]))


def _loop_factory():
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recreate", action="store_true",
                        help="drop the demo database before rebuilding it")
    parser.add_argument("--serve", action="store_true",
                        help="start the development host against the demo database")
    # The default lives in devhost.environment so the script and the host it starts
    # cannot disagree about which port the demo is on.
    parser.add_argument("--port", type=int, default=demo_port())
    arguments = parser.parse_args(argv)

    dsn = demo_dsn()
    try:
        host, port, database = assert_dsn_targets_demo(dsn)
    except UnsafeTarget as refusal:
        print(f"  STOP: {refusal}")
        return 2
    say("target", f"{host}:{port}/{database}")

    ensure_database(dsn, arguments.recreate)
    for line in migrate(dsn).splitlines():
        if line.strip():
            say("alembic", line.strip()[:100])
    # psycopg's async driver cannot run on Windows' default ProactorEventLoop. The dev
    # host solves this the same way; the two are kept identical rather than one of them
    # being subtly different about it.
    asyncio.run(build(dsn), loop_factory=_loop_factory)
    print("\n  demo database ready.")
    if arguments.serve:
        serve(dsn, arguments.port)
    return 0


def serve(dsn: str, port: int) -> None:
    """Start the development host against the demo database, in one process.

    Both DSNs are passed by environment rather than written anywhere: `FINANCE_DEV_DSN`
    for the finance tables, `FINANCE_CORE_DSN` for the Core mirror. They point at the same
    database here and are still two settings -- see `devhost.environment.core_url`.

    `FINANCE_MIGRATION_DSN` is deliberately cleared. The schema was migrated a moment ago,
    explicitly, by the step above; leaving a DDL-capable credential in the running host
    environment would grant it rights it has no use for.
    """
    environment = dict(os.environ, FINANCE_DEV_DSN=dsn, FINANCE_CORE_DSN=dsn)
    environment.pop("FINANCE_MIGRATION_DSN", None)
    # The host checks the port again before binding, and refuses port 8000 outright --
    # see devhost.__main__.check_port. Nothing here duplicates that decision.
    print(f"  starting the development host on http://127.0.0.1:{port}")
    print("  the browser uses the real API against this database, not mock adapters.\n")
    subprocess.run([sys.executable, "-m", "devhost", "--port", str(port)],
                   cwd=BACKEND_ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
