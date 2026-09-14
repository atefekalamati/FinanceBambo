# -*- coding: utf-8 -*-
"""Shared safety checks for the operational scripts in this directory.

These four checks are in one file because four copies of them would drift, and the copy
that drifted would be the one somebody ran against the wrong database at two in the
morning. Nothing here is clever; it is here so that "did you check?" has one answer.

NOTHING IN THIS PACKAGE IS APPLICATION CODE

`backend/app` must never import it, and `tests/test_demo_isolation.py` fails if it does.
These scripts connect to databases and run `pg_dump`; a runtime that could reach them is a
runtime one bad import away from doing that during a request.
"""

import os
import subprocess
import sys
from urllib.parse import urlsplit

#: Never written by anything in this directory, on any host, for any reason.
#:
#: `bambo` is Core's own database and `bambo_canonical_local` is the production-like one.
#: A production operation is a separate, reviewed script that does not exist yet; until it
#: does, the honest behaviour is to refuse rather than to grow a flag that turns this off.
PROTECTED_DATABASES = frozenset({"bambo", "bambo_canonical_local"})

#: The one database these scripts are written for.
CANONICAL_TEST = "bambo_canonical_test"


class Refused(SystemExit):
    """Stop, with a message saying which rule stopped it."""

    def __init__(self, message):
        super().__init__("STOP: " + message)


def database_of(dsn: str):
    """The database a DSN names, in either spelling, or None when it names none.

    Returned as None rather than guessed: a rule applied to a misread address reads as
    enforcement while enforcing something else.
    """
    if not dsn:
        return None
    text = dsn.strip()
    if "://" in text:
        return (urlsplit(text).path or "").lstrip("/").split("?")[0] or None
    keywords = dict(part.split("=", 1) for part in text.split() if "=" in part)
    return keywords.get("dbname")


def require_dsn(value, variable, what):
    """A DSN from the command line or the environment. Never a default, never a literal.

    A default would be a hardcoded write target, which is the thing that turns a script
    somebody ran in the wrong window into an incident.
    """
    dsn = (value or os.environ.get(variable) or "").strip()
    if not dsn:
        raise Refused("no %s given. Pass it on the command line or set %s."
                      % (what, variable))
    return dsn


def refuse_protected(dsn: str, *, action="write to"):
    """Refuse a DSN naming a protected database, before a connection is opened."""
    name = database_of(dsn)
    if name is None:
        raise Refused("the DSN names no database, so it cannot be checked.")
    if name in PROTECTED_DATABASES:
        raise Refused("%r is protected. This script will never %s it; a production "
                      "operation is a separate, reviewed script." % (name, action))
    return name


def identity(connection):
    """`(database, host, port, user)` as the SERVER reports them, and printed.

    Asked after connecting, not read off the DSN: a tunnel can make anything answer on
    loopback, and the address somebody typed is not evidence of where they arrived.
    """
    row = connection.execute(
        "SELECT current_database() AS d, host(inet_server_addr()) AS h,"
        " inet_server_port() AS p, current_user AS u,"
        " current_setting('server_version') AS v").fetchone()
    print("   %s | %s:%s | user %s | PostgreSQL %s"
          % (row["d"], row["h"], row["p"], row["u"], row["v"]))
    return row


def confirm_identity(connection, expected, *, require_loopback=True):
    """The server must be the database that was asked for, and it must be local.

    Both halves matter. The name alone would accept a production database that happened to
    be called the same thing; loopback alone would accept any database on this machine.
    """
    row = identity(connection)
    if row["d"] != expected:
        raise Refused("expected %r, the server answered %r." % (expected, row["d"]))
    if row["d"] in PROTECTED_DATABASES:
        raise Refused("the server answered %r, which is protected." % row["d"])
    if require_loopback and row["h"] not in ("127.0.0.1", "::1"):
        raise Refused("%r is not loopback. These scripts are for a local database."
                      % row["h"])
    return row


def postgres_tool(name, server_version):
    """The path to `name` whose MAJOR version matches the server's.

    Chosen by version, never by whichever directory sorts last. An 18.x pg_dump against a
    16.x server emits parameters the server does not know, and the result is a dump that
    restores with warnings nobody reads.
    """
    major = str(server_version).split(".")[0]
    roots = [r"C:/Program Files/PostgreSQL", "/usr/lib/postgresql"]
    candidates = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            for path in ("%s/%s/bin/%s.exe" % (root, entry, name),
                         "%s/%s/bin/%s" % (root, entry, name)):
                if os.path.isfile(path):
                    candidates.append(path)
    for path in candidates:
        found = subprocess.run([path, "--version"], capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.split()[-1].split(".")[0] == major:
            return path, found.stdout.split()[-1]
    raise Refused("no %s with major version %s was found for a server running %s. "
                  "Install the matching client tools rather than using another version."
                  % (name, major, server_version))


def run(command):
    """A subprocess, judged by its RETURN CODE.

    Never piped through anything: a pipeline reports the exit status of its last command,
    so `pg_dump ... | tail` that failed looks exactly like one that succeeded.
    """
    finished = subprocess.run(command, capture_output=True, text=True)
    return finished.returncode, finished.stdout, finished.stderr


def dry_run_banner(applying: bool):
    """Say which mode this is, loudly, before anything happens."""
    if applying:
        print("   MODE: --apply given. This run WILL write.")
    else:
        print("   MODE: dry run. Nothing will be written. Pass --apply to write.")
    return applying


def selector_loop():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    import asyncio

    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
