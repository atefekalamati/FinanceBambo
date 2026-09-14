"""Load the development dataset, and decide when to.

Schema is **not** touched here. Startup does not migrate -- see `upgrade_to_head_sync`.

Schema truth is Alembic and only Alembic. This module used to hold a second migration
mechanism -- a loop that executed every `migrations/*.up.sql` in filename order -- and two
mechanisms over one schema is one too many: they can disagree about what has been applied,
and only one of them records anything.

The seed is a different thing from a migration and stays separate. It lives in `seed.sql`
as plain, reviewable SQL and is executed as-is; regenerate it with
`python -m devhost.generate_seed_sql` after changing the mock data it mirrors. It is loaded
directly rather than through the services, because the services enforce invariants that
assume a populated project already exists. It is development fixture data and is guarded as
such -- see `seeding_allowed()` -- never a migration.
"""

import asyncio
from pathlib import Path

from . import seed

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


class SchemaNotMigrated(RuntimeError):
    """The development database has no finance schema yet."""


def seed_plan(*, allowed: bool, reseed: bool, already_seeded: bool) -> tuple[bool, bool]:
    """What startup should do about fixture data: `(reset_first, load)`.

    Separated from the host so the decision can be tested exhaustively without a database.
    The rule it encodes:

      * seeding not allowed -> do nothing at all, not even look
      * explicit --reseed   -> reset, then load
      * nothing seeded yet  -> load only
      * already seeded      -> do nothing

    The third case is the correction. Startup used to reset before the first load as well,
    which meant a brand-new database ran the destructive path to delete rows that were never
    there. Harmless in effect, wrong in intent: `reset()` exists to discard a developer's
    working data, and it should only run when a developer asks for that.
    """
    if not allowed:
        return (False, False)
    if reseed:
        return (True, True)
    return (False, not already_seeded)


def upgrade_to_head_sync() -> None:
    """Run `alembic upgrade head` in-process.

    **Not called at startup, and must not be.** Migrations are an explicit operation an
    operator performs -- `alembic upgrade head` from `backend/` -- because starting a
    process is not consent to alter a schema. This helper exists for tooling and tests that
    mean to migrate deliberately; wiring it into a lifespan would put DDL behind the act of
    launching a program.

    Alembic opens its own SQLAlchemy connection from FINANCE_MIGRATION_DSN, so no connection
    is passed in: the DDL role and the runtime role stay separate, and this function cannot
    be handed the application connection by mistake.

    `script_location` in alembic.ini is written relative to that file, so the working
    directory does not matter.
    """
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(ALEMBIC_INI)), "head")


async def upgrade_to_head() -> None:
    """The same, off the event loop. Also not called at startup -- see above."""
    await asyncio.to_thread(upgrade_to_head_sync)


async def is_seeded(connection) -> bool:
    """Whether the development project already exists.

    Raises `SchemaNotMigrated` when the finance tables are absent. Startup no longer creates
    them, so this is the first thing that notices -- and a developer who has not run the
    migration deserves to be told that, rather than an UndefinedTable traceback from three
    layers down or, worse, silent DDL repairing it for them.
    """
    from psycopg import errors
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM finance_project_settings WHERE organization_id=%s AND project_id=%s LIMIT 1",
                (seed.ORGANIZATION_ID, seed.PROJECT_ID))
            return await cursor.fetchone() is not None
    except errors.UndefinedTable as error:
        raise SchemaNotMigrated(
            "The finance schema is not present in this database.\n"
            "Startup does not migrate: apply it explicitly first.\n"
            "    cd backend && alembic upgrade head"
        ) from error


async def reset(connection) -> None:
    """Drop the seeded project. History tables reject UPDATE and DELETE by trigger, so the
    immutability guards are disabled for the length of this statement batch only."""
    tables = ("invoice_lines", "invoices", "progress_overrides", "progress_snapshot_refs",
              "unit_conversions", "price_versions", "estimate_revisions", "estimate_lines",
              "finance_resources", "finance_project_settings", "finance_audit_events",
              "report_snapshots", "finance_attachments", "extraction_drafts",
              # Cleared with the invoices it counts: a counter left behind would resume at
              # a number the reseeded invoices already hold.
              "finance_invoice_counters",
              "finance_import_batches")
    async with connection.cursor() as cursor:
        await cursor.execute("SET session_replication_role = replica")
        for table in tables:
            await cursor.execute(
                f"DELETE FROM {table} WHERE organization_id=%s AND project_id=%s",
                (seed.ORGANIZATION_ID, seed.PROJECT_ID))
        await cursor.execute("SET session_replication_role = DEFAULT")


SEED_SQL = Path(__file__).resolve().parent / "seed.sql"


async def load_seed(connection) -> None:
    """Execute the committed seed. It wraps itself in BEGIN/COMMIT."""
    async with connection.cursor() as cursor:
        await cursor.execute(SEED_SQL.read_text(encoding="utf-8"))
