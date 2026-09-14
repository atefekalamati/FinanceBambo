# -*- coding: utf-8 -*-
r"""Back up a local Finance test database, and prove the backup is usable.

    python -m scripts.ops.backup_canonical_test --dsn postgresql://user@127.0.0.1:5432/bambo_canonical_test
    FINANCE_OPS_DSN=... python -m scripts.ops.backup_canonical_test --out E:/bamboo/backups

This one has no dry run: it only reads the database and writes a file, so there is nothing
to withhold. Everything else in this directory refuses to write without `--apply`.

WHY IT IS THIS FUSSY

Three things went wrong the last time a backup was taken by hand, and each check here is
one of them:

  * the newest pg_dump in the directory was picked, which was 18.6 against a 16.15 server.
    It emitted `transaction_timeout`, the server did not know it, and the warning was
    tolerated. The tool is now chosen by matching the server's MAJOR version.
  * the result was piped through `tail`, so the exit status reported was `tail`'s. Every
    command here is judged by its own return code and nothing is piped.
  * "it produced a file" was taken as success. A file is not a backup until `pg_restore
    --list` can read it, so that runs, and a suspiciously small archive stops the script.
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from scripts.ops._common import (CANONICAL_TEST, Refused, confirm_identity, postgres_tool,
                                 refuse_protected, require_dsn, run)

#: Below this, the archive is not this database and something went wrong quietly.
MINIMUM_ENTRIES = 50


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="target DSN; or set FINANCE_OPS_DSN")
    parser.add_argument("--database", default=CANONICAL_TEST,
                        help="the database this run expects to reach (default: %s)"
                             % CANONICAL_TEST)
    parser.add_argument("--out", default=os.environ.get("FINANCE_OPS_BACKUP_DIR", "backups"),
                        help="directory for the dump; or set FINANCE_OPS_BACKUP_DIR")
    arguments = parser.parse_args(argv)

    dsn = require_dsn(arguments.dsn, "FINANCE_OPS_DSN", "target DSN")
    refuse_protected(dsn, action="back up")

    print("### target ###")
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as db:
        # Read-only for the whole session: this script has no reason to write, and the
        # server refusing is better than the author remembering.
        db.execute("SET default_transaction_read_only = on")
        row = confirm_identity(db, arguments.database)
        server_version = row["v"]

    pg_dump, dump_version = postgres_tool("pg_dump", server_version)
    pg_restore, _ = postgres_tool("pg_restore", server_version)
    print("   pg_dump  : %s  (%s)" % (dump_version, pg_dump))
    print("   major versions agree with the server")

    out_dir = Path(arguments.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / ("%s_%s.dump" % (arguments.database, stamp))

    print()
    print("### dumping (custom format) ###")
    code, _out, err = run([pg_dump, "--dbname", dsn, "--format=custom",
                           "--no-owner", "--no-privileges", "--file", str(path)])
    print("   pg_dump exit code : %d" % code)
    if err.strip():
        print("   stderr            : %s" % err.strip()[:400])
    if code != 0:
        raise Refused("the dump failed. Nothing downstream of this should run.")

    size = path.stat().st_size
    print("   file              : %s" % path)
    print("   size              : %d bytes (%.1f MB)" % (size, size / 1024 / 1024))
    if size == 0:
        raise Refused("the dump is empty.")

    print()
    print("### validating with pg_restore --list ###")
    code, listing, err = run([pg_restore, "--list", str(path)])
    print("   pg_restore exit code : %d" % code)
    if code != 0:
        print("   stderr               : %s" % err.strip()[:400])
        raise Refused("the dump does not list. It is a file, not a backup.")
    entries = [line for line in listing.splitlines() if line and not line.startswith(";")]
    tables = [line for line in entries if " TABLE DATA " in line]
    print("   archive entries      : %d" % len(entries))
    print("   TABLE DATA entries   : %d" % len(tables))
    if len(entries) < MINIMUM_ENTRIES:
        raise Refused("only %d archive entries -- that is not %s."
                      % (len(entries), arguments.database))

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    (path.parent / (path.name + ".sha256")).write_text(
        "%s  %s\n" % (digest.hexdigest(), path.name), encoding="utf-8")

    print()
    print("   BACKUP VALIDATED")
    print("   path    : %s" % path)
    print("   sha256  : %s" % digest.hexdigest())
    print("   server  : PostgreSQL %s" % server_version)
    print("   pg_dump : %s" % dump_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
