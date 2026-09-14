# -*- coding: utf-8 -*-
r"""TEST_ONLY -- LOCAL. Create the disposable database the material price tests ask for.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.prepare_material_price_test_db

WHAT IT DOES

  1. Drops and recreates `bambo_material_price_test`, and nothing else, on 127.0.0.1.
  2. Applies the Core mirror schema, because revision 0009 declares a foreign key to
     `msp_tasks` and the chain stops there without it.
  3. `alembic upgrade head`.

WHAT IT REFUSES

Any database name but that one, any host but loopback, and every name in
`FORBIDDEN_DATABASES`. The name is checked twice -- once against the argument and once
against `current_database()` after connecting -- because a tunnel can make anything answer
on 127.0.0.1, and a rule applied to a misread address reads as enforcement while enforcing
something else.

No seed data is loaded. These tests build the rows they need.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

HOST = "127.0.0.1"
PORT = 5432
DATABASE = "bambo_material_price_test"
MAINTENANCE = "postgres"

#: Never, on any host, for any reason.
FORBIDDEN_DATABASES = frozenset({"bambo", "bambo_canonical_local", "bambo_canonical_test"})

MIRROR_SQL = BACKEND_ROOT / "scripts" / "demo" / "core_mirror.sql"


def dsn(database):
    return "postgresql://postgres@%s:%d/%s" % (HOST, PORT, database)


def refuse_unless_disposable(database):
    if database in FORBIDDEN_DATABASES:
        raise SystemExit("STOP: %r is protected and is never created or dropped here."
                         % database)
    if database != DATABASE:
        raise SystemExit("STOP: this script only ever touches %r." % DATABASE)


def recreate():
    refuse_unless_disposable(DATABASE)
    with psycopg.connect(dsn(MAINTENANCE), autocommit=True, row_factory=dict_row) as db:
        where = db.execute("SELECT current_database() AS d").fetchone()["d"]
        if where != MAINTENANCE:
            raise SystemExit("STOP: expected to be connected to %r, reached %r"
                             % (MAINTENANCE, where))
        db.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % DATABASE)
        db.execute('CREATE DATABASE "%s"' % DATABASE)
    print("  recreated %s" % DATABASE)


def apply_core_mirror():
    """Revision 0009 references `msp_tasks`; without the mirror the chain stops there."""
    sql = MIRROR_SQL.read_text(encoding="utf-8")
    with psycopg.connect(dsn(DATABASE), autocommit=True, row_factory=dict_row) as db:
        where = db.execute("SELECT current_database() AS d").fetchone()["d"]
        if where != DATABASE:
            raise SystemExit("STOP: expected %r, reached %r" % (DATABASE, where))
        db.execute(sql)
    print("  core mirror applied")


def migrate():
    environment = dict(os.environ, FINANCE_MIGRATION_DSN=dsn(DATABASE))
    finished = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                              cwd=str(BACKEND_ROOT), env=environment,
                              capture_output=True, text=True)
    if finished.returncode != 0:
        raise SystemExit("alembic upgrade failed:\n" + finished.stderr[-2000:])
    with psycopg.connect(dsn(DATABASE), row_factory=dict_row) as db:
        version = db.execute("SELECT version_num FROM finance_alembic_version").fetchone()
    print("  migrated to %s" % version["version_num"])


def main():
    print("\n  TEST_ONLY -- creating a disposable database. Nothing else is touched.\n")
    recreate()
    apply_core_mirror()
    migrate()
    print("\n  ready: %s\n" % dsn(DATABASE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
