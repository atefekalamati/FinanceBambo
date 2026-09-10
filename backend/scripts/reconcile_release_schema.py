"""Local recovery of an externally applied 0014-0016 schema, never a blind stamp.

The reference must be a fresh Alembic installation. Compare complete affected tables,
including types/defaults/constraints/indexes/triggers and their function bodies. Any
difference refuses ledger repair. No DDL or financial data is changed by this tool.
"""
import argparse
import hashlib
import json

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

TABLES = ("finance_mpp_source_versions", "finance_mpp_rows", "estimate_line_source_completions")
QUERIES = {
    "columns": """SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
        pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated
        FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attname""",
    "constraints": """SELECT conname,pg_get_constraintdef(oid),convalidated
        FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY conname""",
    "indexes": """SELECT ic.relname,pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready
        FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
        WHERE i.indrelid=%s::regclass ORDER BY ic.relname""",
    "triggers": """SELECT tgname,pg_get_triggerdef(oid),tgenabled,pg_get_functiondef(tgfoid)
        FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal ORDER BY tgname""",
}


def manifest(connection):
    return {table: {kind: connection.execute(query, ("public." + table,)).fetchall()
                    for kind, query in QUERIES.items()} for table in TABLES}


def fingerprints(connection):
    tables = connection.execute("""SELECT tablename FROM pg_tables WHERE schemaname='public'
        AND tablename <> 'finance_alembic_version' ORDER BY tablename""").fetchall()
    result = {}
    for (table,) in tables:
        rows = connection.execute(sql.SQL("SELECT to_jsonb(t)::text FROM {} t ORDER BY 1").format(
            sql.Identifier("public", table))).fetchall()
        result[table] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return result


def local_dsn(value):
    parts = conninfo_to_dict(value)
    if parts.get("host") not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("this recovery tool is local-only")
    if not parts.get("dbname", "").startswith("bambo_release_"):
        raise ValueError("only isolated bambo_release_* databases are allowed")
    return value


def reconcile(reference_dsn, target_dsn, apply=False):
    local_dsn(reference_dsn)
    local_dsn(target_dsn)
    if conninfo_to_dict(reference_dsn) == conninfo_to_dict(target_dsn):
        raise ValueError("reference and target must be different databases")
    with psycopg.connect(reference_dsn) as reference, psycopg.connect(target_dsn) as target:
        reference.execute("SET TRANSACTION READ ONLY")
        if reference.execute("SELECT version_num FROM finance_alembic_version").fetchall() != [("0016",)]:
            raise ValueError("reference must be a verified 0016 installation")
        target.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
            sql.SQL(",").join(sql.Identifier("public", name) for name in TABLES)))
        expected, actual = manifest(reference), manifest(target)
        differences = {table: {kind: {"expected": expected[table][kind], "actual": actual[table][kind]}
                               for kind in QUERIES if expected[table][kind] != actual[table][kind]}
                       for table in TABLES if expected[table] != actual[table]}
        if differences:
            print(json.dumps(differences, default=str, ensure_ascii=True))
            raise ValueError("schema mismatch: refusing to change migration metadata")
        version = target.execute("SELECT version_num FROM finance_alembic_version FOR UPDATE").fetchall()
        if version not in ([("0013",)], [("0016",)]):
            raise ValueError("only the documented 0013 to 0016 recovery is supported")
        before = fingerprints(target)
        if apply and version == [("0013",)]:
            # Equivalent to a stamp, but only after exact catalog verification under lock.
            target.execute("UPDATE finance_alembic_version SET version_num='0016' WHERE version_num='0013'")
        if fingerprints(target) != before:
            raise ValueError("financial contents changed; transaction will roll back")
        print(json.dumps({"schemaMatches": True, "applied": apply,
                          "unchangedTables": len(before), "targetRevision": "0016" if apply else version[0][0]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dsn", required=True)
    parser.add_argument("--target-dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    reconcile(args.reference_dsn, args.target_dsn, args.apply)
