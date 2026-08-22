"""Apply the finance migrations and load the development dataset.

The migrations are the only source of schema truth, so they run verbatim and in order.
The seed lives in `seed.sql` as plain, reviewable SQL and is executed as-is; regenerate it
with `python -m devhost.generate_seed_sql` after changing the mock data it mirrors. It is
loaded directly rather than through the services, because the services enforce invariants
that assume a populated project already exists.
"""

from pathlib import Path

from . import seed

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


async def apply_migrations(connection) -> list[str]:
    """Run every *.up.sql in name order. They are written to be re-runnable."""
    applied = []
    for path in sorted(MIGRATIONS.glob("*.up.sql")):
        async with connection.cursor() as cursor:
            await cursor.execute(path.read_text(encoding="utf-8"))
        applied.append(path.name)
    return applied


async def is_seeded(connection) -> bool:
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT 1 FROM finance_project_settings WHERE organization_id=%s AND project_id=%s LIMIT 1",
            (seed.ORGANIZATION_ID, seed.PROJECT_ID))
        return await cursor.fetchone() is not None


async def reset(connection) -> None:
    """Drop the seeded project. History tables reject UPDATE and DELETE by trigger, so the
    immutability guards are disabled for the length of this statement batch only."""
    tables = ("invoice_lines", "invoices", "progress_overrides", "progress_snapshot_refs",
              "unit_conversions", "price_versions", "estimate_revisions", "estimate_lines",
              "finance_resources", "finance_project_settings", "finance_audit_events",
              "report_snapshots", "finance_attachments", "extraction_drafts",
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
