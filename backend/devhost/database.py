"""Apply the finance migrations and load development data.

The migrations are the only source of schema truth, so they run verbatim and in order.
Seeding writes through plain SQL rather than the services, because the services enforce
invariants that assume a populated project already exists.
"""

from decimal import Decimal
from pathlib import Path

from psycopg import AsyncConnection

from . import seed

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


async def apply_migrations(connection: AsyncConnection) -> list[str]:
    """Run every *.up.sql in name order. They are written to be re-runnable."""
    applied = []
    for path in sorted(MIGRATIONS.glob("*.up.sql")):
        async with connection.cursor() as cursor:
            await cursor.execute(path.read_text(encoding="utf-8"))
        applied.append(path.name)
    return applied


async def is_seeded(connection: AsyncConnection) -> bool:
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT 1 FROM finance_project_settings WHERE organization_id=%s AND project_id=%s LIMIT 1",
            (seed.ORGANIZATION_ID, seed.PROJECT_ID))
        return await cursor.fetchone() is not None


async def reset(connection: AsyncConnection) -> None:
    """Drop the seeded project. History tables reject UPDATE and DELETE by trigger,
    so the immutability guards are disabled for the length of this transaction only."""
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


async def load_seed(connection: AsyncConnection) -> None:
    org, project, actor, now = seed.ORGANIZATION_ID, seed.PROJECT_ID, seed.ACTOR_ID, seed.NOW
    async with connection.cursor() as cursor:
        await cursor.execute(
            "INSERT INTO finance_project_settings"
            "(id,organization_id,project_id,revision,gross_built_area,currency,effective_from,reason,created_by,created_at)"
            " VALUES(%s,%s,%s,1,%s,'IRR',%s,%s,%s,%s)",
            (seed._uuid("10000000", 1), org, project, seed.GROSS_BUILT_AREA,
             seed.date(2026, 3, 1), "ثبت اولیه زیربنای کل پروژه", actor, now))

        for resource_id, kind, code, title, base_unit, dimension in seed.RESOURCES:
            await cursor.execute(
                "INSERT INTO finance_resources"
                "(id,organization_id,project_id,resource_type,code,title,base_unit,dimension,created_by,created_at)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (resource_id, org, project, kind, code, title, base_unit, dimension, actor, now))

        for line_id, resource_id, activity, assignment, quantity, price in seed.ESTIMATE_LINES:
            await cursor.execute(
                "INSERT INTO estimate_lines"
                "(id,organization_id,project_id,resource_id,activity_external_id,assignment_external_id,"
                "original_quantity,original_unit_price_irr,source,created_by,created_at)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'manual_entry',%s,%s)",
                (line_id, org, project, resource_id, activity, assignment, quantity, price, actor, now))

        for resource_id, scope_kind, version, price, effective_from in seed.PRICE_VERSIONS:
            await cursor.execute(
                "INSERT INTO price_versions"
                "(id,organization_id,project_id,resource_id,scope_kind,version,unit_price_irr,effective_from,reason,created_by,created_at)"
                " VALUES(gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (org, project, resource_id, scope_kind, version, price, effective_from,
                 "ثبت نسخه قیمت", actor, now))

        for index, (source_unit, target_unit, dimension, factor) in enumerate(seed.UNIT_CONVERSIONS, 1):
            await cursor.execute(
                "INSERT INTO unit_conversions"
                "(id,organization_id,project_id,scope_kind,version,source_unit,target_unit,dimension,factor,effective_from,reason,created_by,created_at)"
                " VALUES(gen_random_uuid(),%s,%s,'organization',1,%s,%s,%s,%s,%s,%s,%s,%s)",
                (org, project, source_unit, target_unit, dimension, factor,
                 seed.date(2026, 3, 1), "تبدیل واحد پایه", actor, now))

        await cursor.execute(
            "INSERT INTO progress_snapshot_refs"
            "(id,organization_id,project_id,progress_snapshot_id,source_file_version_id,"
            "source_file_name_safe,reporting_date,snapshot_status,imported_by,imported_at,created_at)"
            " VALUES(%s,%s,%s,%s,gen_random_uuid(),%s,%s,'ready',%s,%s,%s)",
            (seed.SNAPSHOT_REF_ID, org, project, seed.SNAPSHOT_ID,
             "progress-1405-05-29.xlsx", seed.REPORTING_DATE, actor, now, now))

        for (invoice_id, number, invoice_date, vendor, source, status,
             discount, tax, shipping, other, sign) in seed.INVOICES:
            lines = [row for row in seed.INVOICE_LINES if row[0] == invoice_id]
            raw_total = sum((row[6] for row in lines), Decimal(0))
            final_total = raw_total - discount + tax + shipping + other
            confirmed = status in ("confirmed", "voided", "corrected")
            await cursor.execute(
                "INSERT INTO invoices"
                "(id,organization_id,project_id,invoice_number,invoice_date,vendor_name,source,status,"
                "discount_irr,tax_irr,shipping_irr,other_costs_irr,final_amount_irr,financial_effect_sign,"
                "idempotency_key,version,submitted_by,confirmed_by,confirmed_at,created_at,updated_at)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)",
                (invoice_id, org, project, number, invoice_date, vendor, source, status,
                 discount, tax, shipping, other, final_total, sign,
                 f"seed-{invoice_id}", actor,
                 actor if confirmed else None, now if confirmed else None, now, now))

            # Adjustments are spread across the invoice's lines in proportion to raw amount,
            # with the remainder landing on the last line so the parts sum to the whole.
            for index, (_iid, estimate_line_id, resource_id, quantity, unit, unit_price, raw) in enumerate(lines):
                last = index == len(lines) - 1
                def share(total):
                    if raw_total == 0:
                        return total if last else Decimal(0)
                    return (total * raw / raw_total).quantize(Decimal("1"))
                allocated = [share(discount), share(tax), share(shipping), share(other)]
                line_final = raw - allocated[0] + allocated[1] + allocated[2] + allocated[3]
                await cursor.execute(
                    "INSERT INTO invoice_lines"
                    "(id,organization_id,project_id,invoice_id,estimate_line_id,resource_id,quantity,unit,"
                    "unit_price_snapshot_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,"
                    "allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,created_at)"
                    " VALUES(gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (org, project, invoice_id, estimate_line_id, resource_id, quantity, unit,
                     unit_price, raw, allocated[0], allocated[1], allocated[2], allocated[3],
                     line_final, now))

        for action, entity_type, entity_id, reason in (
            ("finance_settings.revised", "finance_project_settings", seed._uuid("10000000", 1), "ثبت اولیه زیربنا"),
            ("invoice.confirmed", "invoices", seed.INVOICES[0][0], None),
            ("invoice.confirmed", "invoices", seed.INVOICES[1][0], None),
            ("price_version.created", "price_versions", seed.RESOURCES[0][0], "به‌روزرسانی قیمت تأمین‌کننده"),
        ):
            await cursor.execute(
                "INSERT INTO finance_audit_events"
                "(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,occurred_at)"
                " VALUES(gen_random_uuid(),%s,%s,%s,%s,%s,%s,%s,%s)",
                (org, project, actor, action, entity_type, entity_id, reason, now))
