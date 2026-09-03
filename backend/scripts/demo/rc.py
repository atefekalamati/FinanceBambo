# -*- coding: utf-8 -*-
"""Build the release-candidate environment: the closest local thing to production.

    python -m scripts.demo.rc                 # build bambo_finance_rc
    python -m scripts.demo.rc --database bambo_finance_rc_clean
    python -m scripts.demo.rc --serve --port 8020

HOW THIS DIFFERS FROM THE DEMO BUILDER
`scripts.demo.prepare` targets the PostgreSQL 16 demo on 5432. This targets the disposable
PostgreSQL 18 cluster on 5440 -- the version production runs -- and uses a separate database
so the validated demo is never touched.

Everything else is deliberately the same: the schema comes from Alembic and nothing else,
the Core mirror comes from the committed DDL generated off the real Core schema, and the
rows come from the same fixture the demo uses. If the RC needed its own build path, it
would be testing a build path production will never run.

THE GATE
Three facts are checked against the server itself before any write: the address, the port,
and the major version. The database name must appear in `RC_DATABASES` -- an allowlist, so a
typo is a refusal rather than a new database. `bambo` and the main server's address are
refused by name, as they are everywhere else in this repository.
"""

import argparse
import asyncio
import os
import selectors
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from scripts.demo import seed_core_mirror                         # noqa: E402
from scripts.demo.target import (FORBIDDEN_DATABASES, FORBIDDEN_HOSTS,  # noqa: E402
                                 UnsafeTarget)

RC_HOST = "127.0.0.1"
RC_PORT = 5440
RC_MAJOR_VERSION = 18

#: An allowlist rather than a pattern. A pattern would happily accept a database this phase
#: never meant to create, and creating one is the irreversible half of this script.
RC_DATABASES = frozenset({
    "bambo_finance_rc", "bambo_finance_rc_restore", "bambo_finance_rc_clean",
})
MAINTENANCE_DATABASE = "postgres"
MIRROR_SQL = Path(__file__).resolve().parent / "core_mirror.sql"
DEFAULT_RC_PORT = 8020


def dsn_for(database: str) -> str:
    return f"postgresql://postgres@{RC_HOST}:{RC_PORT}/{database}"


def say(step: str, detail: str = "") -> None:
    print(f"  {step:<42} {detail}")


def check_name(database: str, *, allow_maintenance: bool = False) -> str:
    permitted = RC_DATABASES | ({MAINTENANCE_DATABASE} if allow_maintenance else frozenset())
    if database in FORBIDDEN_DATABASES:
        raise UnsafeTarget(f"refusing database {database!r}: that is the Main/Core database")
    if database not in permitted:
        raise UnsafeTarget(f"{database!r} is not a release-candidate database; "
                           f"expected one of {sorted(permitted)}")
    return database


def check_server(connection, expected_database: str) -> dict:
    """Ask the server who it is. The DSN is a claim; this is the answer."""
    row = connection.execute("""
        SELECT current_database() AS database, host(inet_server_addr()) AS host,
               inet_server_port() AS port, current_user AS usr, version() AS version,
               current_setting('server_version_num') AS version_num
    """).fetchone()
    major = int(row["version_num"]) // 10000
    if row["host"] in FORBIDDEN_HOSTS or row["database"] in FORBIDDEN_DATABASES:
        raise UnsafeTarget(f'the server answering is {row["host"]}/{row["database"]}')
    if row["host"] != RC_HOST or int(row["port"]) != RC_PORT:
        raise UnsafeTarget(f'server reports {row["host"]}:{row["port"]}, '
                           f"expected {RC_HOST}:{RC_PORT}")
    if row["database"] != expected_database:
        raise UnsafeTarget(f'server reports database {row["database"]!r}, '
                           f"expected {expected_database!r}")
    if major != RC_MAJOR_VERSION:
        raise UnsafeTarget(f"server is PostgreSQL {major}, expected {RC_MAJOR_VERSION}")
    return dict(row, major=major)


def ensure_database(database: str, recreate: bool) -> None:
    check_name(database)
    admin = dsn_for(MAINTENANCE_DATABASE)
    check_name(urlsplit(admin).path.lstrip("/"), allow_maintenance=True)
    with psycopg.connect(admin, autocommit=True, row_factory=dict_row,
                         connect_timeout=10) as connection:
        server = check_server(connection, MAINTENANCE_DATABASE)
        say("server", server["version"].split(" on ")[0])
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                    (database,)).fetchone()
        if exists and recreate:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (database,))
            connection.execute(f'DROP DATABASE "{database}"')
            exists = None
            say("dropped", database)
        if not exists:
            connection.execute(f'CREATE DATABASE "{database}"')
            say("created", database)
        else:
            say("already present", database)


def migrate(database: str) -> None:
    """Alembic, in a subprocess, with the DSN passed by environment.

    The same command a release runs. Nothing else in this file writes finance DDL.
    """
    environment = dict(os.environ, FINANCE_MIGRATION_DSN=dsn_for(database))
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=BACKEND_ROOT, capture_output=True, text=True,
                            env=environment)
    if result.returncode != 0:
        raise SystemExit("alembic upgrade failed; re-run it directly to see the error")
    # Alembic logs to stderr, so counting stdout alone reports zero for a successful run.
    applied = (result.stdout + result.stderr).count("Running upgrade")
    say("alembic upgrade head", f"{applied} revisions")


async def build(database: str) -> None:
    async with await psycopg.AsyncConnection.connect(
            dsn_for(database), autocommit=True, row_factory=dict_row,
            connect_timeout=10) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""
                SELECT current_database() AS database, host(inet_server_addr()) AS host,
                       inet_server_port() AS port,
                       current_setting('server_version_num') AS version_num
            """)
            row = await cursor.fetchone()
        major = int(row["version_num"]) // 10000
        if (row["database"] != database or row["host"] != RC_HOST
                or int(row["port"]) != RC_PORT or major != RC_MAJOR_VERSION):
            raise UnsafeTarget(f'refusing to write to {row["host"]}:{row["port"]}/'
                               f'{row["database"]} (PostgreSQL {major})')
        say("write target confirmed", f'PG{major} {row["host"]}:{row["port"]}/{row["database"]}')

        await connection.execute(MIRROR_SQL.read_text(encoding="utf-8"))
        counts = await seed_core_mirror.apply(connection)
        say("core mirror", ", ".join(f"{t}={c}" for t, c in counts.items() if c))

        from devhost import database as finance_data
        await finance_data.load_seed(connection)
        say("finance fixtures", "devhost/seed.sql")

        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT version_num FROM finance_alembic_version")
            version = await cursor.fetchone()
            await cursor.execute("SELECT count(*) AS n FROM information_schema.tables "
                                 "WHERE table_schema = 'public'")
            tables = await cursor.fetchone()
        say("finance_alembic_version", version["version_num"] if version else "MISSING")
        say("public tables", str(tables["n"]))


def serve(database: str, port: int) -> None:
    """Start the host against the RC database.

    `FINANCE_MIGRATION_DSN` is cleared: the schema was migrated a moment ago, explicitly,
    and leaving a DDL-capable credential in a running host's environment grants it rights it
    has no use for.
    """
    environment = dict(os.environ, FINANCE_DEV_DSN=dsn_for(database),
                       FINANCE_CORE_DSN=dsn_for(database))
    environment.pop("FINANCE_MIGRATION_DSN", None)
    print(f"\n  release candidate on http://127.0.0.1:{port}  ->  {database} (PG18)\n")
    result = subprocess.run([sys.executable, "-m", "devhost", "--port", str(port)],
                            cwd=BACKEND_ROOT, env=environment)
    # Without this the script reports success when the host never started. It did: the
    # release-candidate environment was missing uvicorn -- which lives in
    # devhost/requirements.txt rather than requirements.txt, because the deployed module is
    # a library and does not carry a server -- and `--serve` exited 0 having served nothing.
    if result.returncode != 0:
        raise SystemExit(f"the development host exited {result.returncode}; "
                         "install backend/devhost/requirements.txt in this environment")


def _loop_factory():
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", default="bambo_finance_rc",
                        help=f"one of {sorted(RC_DATABASES)}")
    parser.add_argument("--recreate", action="store_true", default=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=DEFAULT_RC_PORT)
    arguments = parser.parse_args(argv)
    try:
        database = check_name(arguments.database)
    except UnsafeTarget as refusal:
        print(f"  STOP: {refusal}")
        return 2
    say("target", f"{RC_HOST}:{RC_PORT}/{database}")
    ensure_database(database, arguments.recreate)
    migrate(database)
    asyncio.run(build(database), loop_factory=_loop_factory)
    print("\n  release candidate ready.")
    if arguments.serve:
        serve(database, arguments.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
