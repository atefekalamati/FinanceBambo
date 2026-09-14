# Operational scripts for the material price database work

These four scripts are how the material-price data got into `bambo_canonical_test`. They
are here so that operation is **repeatable and reviewable** before anything like it is
proposed for a production database — a migration applied by a script nobody kept is a
migration nobody can check.

They are **tools, not application code**. `backend/app` never imports them, and
`tests/test_demo_isolation.py` fails if it ever does: these open database connections and
run `pg_dump`, and a runtime that could reach them is one bad import away from doing that
during a request.

---

## Rules every script here follows

| | |
|---|---|
| Explicit execution | Nothing runs on import, at startup, in tests, or during a migration. Each is a `python -m` entry point. |
| Dry run by default | Read, report, write nothing. `--apply` is the only way to write. `backup_canonical_test` is the exception: it only reads the database and writes a file, so there is nothing to withhold. |
| No credentials | Every DSN comes from `--dsn` or an environment variable. There is no default DSN and no password anywhere in this directory. |
| No production target | `bambo` and `bambo_canonical_local` are refused before a connection is opened **and** again after, against what the server itself reports. No flag turns that off. |
| Identity is asked, not assumed | `current_database()`, `inet_server_addr()`, `inet_server_port()`, `current_user` — because a tunnel can make anything answer on loopback. |
| Nothing destructive | No `DROP`, `TRUNCATE`, `DELETE`, full restore, trigger disable, or `session_replication_role`. |
| No invented data | Nothing here creates a price, a provider or a seed row. |

---

## `backup_canonical_test.py`

```
python -m scripts.ops.backup_canonical_test --dsn postgresql://user@127.0.0.1:5432/bambo_canonical_test
FINANCE_OPS_DSN=... FINANCE_OPS_BACKUP_DIR=E:/bamboo/backups python -m scripts.ops.backup_canonical_test
```

Custom-format `pg_dump`, validated with `pg_restore --list`, hashed with SHA256. Prints the
path, size, hash, tool version and server version.

Three checks, each from something that went wrong when this was done by hand:

- the tool is chosen by **matching the server's major version**, never by which directory
  sorts last — an 18.x `pg_dump` against a 16.x server emits parameters the server does not
  know;
- every command is judged by its own **return code**, and nothing is piped — a pipeline
  reports the exit status of its *last* command, so a failed dump through `tail` looks like
  a success;
- a file is not a backup until `pg_restore --list` can read it, and an archive with fewer
  than 50 entries stops the script.

## `migrate_canonical_test.py`

```
python -m scripts.ops.migrate_canonical_test --dsn ...          # dry run: prints the range
python -m scripts.ops.migrate_canonical_test --dsn ... --apply
```

Counts every business table and every immutability trigger before and after, and **stops if
any count falls**. Prints the exact list of revisions that would run before running them,
because an Alembic chain is linear and reaching the revision you want means running every
one in between — including ones that touch data. It never disables a trigger and never
downgrades.

## `copy_material_work.py`

```
python -m scripts.ops.copy_material_work --source ... --target ...
python -m scripts.ops.copy_material_work --source ... --target ... --apply
```

`INSERT ... ON CONFLICT DO NOTHING`, parents before children. A row already in the target
is counted as already present and left alone — **including when its values differ**, which
is reported as a conflict rather than resolved. Resolving it would mean choosing which of
two databases is right, and this script is not in a position to know.

With `--apply`, a table with conflicts writes **nothing** for that table and the script
stops.

UUIDs are preserved because that keeps provenance intact, and it is checked rather than
assumed: every id present on both sides is compared first. `price_versions` is never
copied — an observation is evidence, an official Finance price is a decision.

## `import_into_terrace.py`

```
python -m scripts.ops.import_into_terrace --sheet <url>                       # dry run
python -m scripts.ops.import_into_terrace --dsn ... --organization <uuid> \
    --project terrace --apply
```

Goes through `MaterialPriceImportService`, the same service the application uses, so every
rule comes with it: an incomplete workbook writes nothing, a missing required header
refuses the worksheet by name, a blank price is stored as a rejected observation and never
as a zero, Toman becomes IRR by one multiplication, and re-running inserts nothing it has
already inserted.

The dry run opens **no database connection at all** — it fetches the sheet, reads it
through the real contract, and reports.

`scripts/import_material_prices.py` refuses `bambo_canonical_test` by name and that
refusal is **left exactly as it is**. This script reaches that database by satisfying the
same checks explicitly, not by turning the guard off.

---

## Order

1. `backup_canonical_test.py` — and do not continue if it fails.
2. `migrate_canonical_test.py` — dry run, read the range, then `--apply`.
3. `copy_material_work.py` or `import_into_terrace.py` — dry run, then `--apply`.

## Not for production

None of these may be pointed at `bambo` or `bambo_canonical_local`. A production operation
is a separate script with its own review, and it does not exist yet.
