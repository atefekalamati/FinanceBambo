"""Alembic's entry point, wired to this project's existing configuration.

WHERE THE URL COMES FROM
`FINANCE_MIGRATION_DSN`, read through `devhost.environment` — the same loader the rest of
the project uses, rather than a second .env parser that could drift from it. The DSN is
never written into alembic.ini: that file is committed, and a committed file is the wrong
place for a password.

WHY NOT THE RUNTIME DSN
`FINANCE_DEV_DSN` belongs to the application role, which deliberately cannot issue DDL.
Schema changes run as an owner role and finish before the service starts, the same split a
release uses. Reading the runtime DSN here would quietly undo that separation, so it is
not read at all.

WHY AN ABSENT DSN IS FATAL
There is no fallback and no default. A guessed connection string is how a migration ends
up running against the wrong database, and the one thing worse than a failed migration is
a successful one somewhere unintended.

NO AUTOGENERATE
This project has no SQLAlchemy models — repositories are raw parameterised SQL against
psycopg — so `target_metadata` stays None. Every revision is written from reviewed SQL.
SQLAlchemy is present only because Alembic connects through it.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# `prepend_sys_path = .` in alembic.ini covers the usual case of running from backend/.
# This makes the import work from any working directory, so a script or a test harness
# that invokes Alembic programmatically does not have to chdir first.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from devhost.environment import MissingConfiguration, migration_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: No models, so nothing to compare against. See the module docstring.
target_metadata = None

#: Finance owns its migration chain, not the database it lives in.
#:
#: The generic name `alembic_version` claims the migration-version namespace of the whole
#: database. In production Finance is installed into the shared BAMBO database, which has no
#: Alembic table of its own today -- so the generic name would silently make Finance the
#: owner of migration state for every module, and would collide the day Core adopts Alembic.
#: One table, one version_num row, two owners: neither could then proceed without a manual
#: repair on a production database.
VERSION_TABLE = "finance_alembic_version"


def _migration_engine_url() -> str:
    """The migration DSN, named for the driver this project actually installs.

    SQLAlchemy resolves a bare `postgresql://` URL to psycopg2, which is not a dependency
    here; psycopg 3 is. Naming the driver in the URL keeps one DSN in `.env` usable by both
    tools, instead of asking anyone to maintain a second copy that differs by one word.
    """
    dsn = migration_url()
    if not dsn:
        raise MissingConfiguration(
            "FINANCE_MIGRATION_DSN is not set, and Alembic will not guess a database.\n"
            "Set it to the owner role that is allowed to run DDL. FINANCE_DEV_DSN is the\n"
            "application role and is deliberately not used for migrations."
        )
    for prefix in ("postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+psycopg://" + dsn[len(prefix):]
    return dsn


def run_migrations_offline() -> None:
    """Emit SQL instead of running it, for review or for a DBA to apply."""
    context.configure(
        url=_migration_engine_url(),
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run. The engine is built from the DSN rather than from alembic.ini, so
    the placeholder URL in that file can never become a real connection by accident."""
    connectable = create_engine(_migration_engine_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          version_table=VERSION_TABLE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
