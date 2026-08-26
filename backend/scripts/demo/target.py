"""The gate every destructive demo action has to pass first.

Two checks, deliberately independent, because they can fail in different ways:

  1. `assert_dsn_targets_demo` parses the connection string and compares it against the one
     approved target. Cheap, and it runs before a socket is opened -- but a DSN is only a
     claim about where it points.
  2. `assert_server_is_demo` asks the server that actually answered who it is. This is the
     check that matters. A tunnel, a `pg_hba` redirect, a stale port-forward or a typo can
     all make a loopback DSN reach somewhere else, and only the server can settle it.

Both name the Main/Core database explicitly in `FORBIDDEN_*` rather than merely failing to
match the approved value. Refusing something by name gives a specific error when it
happens, and leaves a searchable record of what this module was written to prevent.
"""

from urllib.parse import urlsplit

#: The only server the demo may write to.
DEMO_HOST = "127.0.0.1"
DEMO_PORT = 5432

#: The only database the demo may write to, plus the maintenance database that has to be
#: reachable to create and drop it.
DEMO_DATABASE = "bambo_finance_integration_demo"
MAINTENANCE_DATABASE = "postgres"

#: Named so a mistake is refused with a message that says what it was, not just that some
#: comparison failed.
FORBIDDEN_HOSTS = frozenset({"192.168.100.200"})
FORBIDDEN_DATABASES = frozenset({"bambo"})


class UnsafeTarget(RuntimeError):
    """The target is not the approved local demo database. Nothing should proceed."""


def parse_target(dsn: str) -> tuple[str, int, str]:
    """`(host, port, database)` as the connection string states them."""
    parts = urlsplit(dsn)
    return (parts.hostname or "", parts.port or 5432,
            parts.path.lstrip("/").split("?")[0])


def assert_dsn_targets_demo(dsn: str, *, allow_maintenance: bool = False) -> tuple[str, int, str]:
    """Gate 1: the DSN claims the approved local target.

    `allow_maintenance` widens the permitted database to `postgres`, and only that -- it is
    needed to CREATE or DROP the demo database, which cannot be done from inside it. The
    host and port are never widened.
    """
    host, port, database = parse_target(dsn)
    permitted = {DEMO_DATABASE} | ({MAINTENANCE_DATABASE} if allow_maintenance else set())

    if host in FORBIDDEN_HOSTS:
        raise UnsafeTarget(f"refusing {host}: that is the Main/Core server, which is read-only")
    if database in FORBIDDEN_DATABASES:
        raise UnsafeTarget(f"refusing database {database!r}: that is the Main/Core database")
    if host != DEMO_HOST:
        raise UnsafeTarget(f"host must be {DEMO_HOST}, the DSN says {host!r}")
    if port != DEMO_PORT:
        raise UnsafeTarget(f"port must be {DEMO_PORT}, the DSN says {port}")
    if database not in permitted:
        raise UnsafeTarget(
            f"database must be one of {sorted(permitted)}, the DSN says {database!r}")
    return host, port, database


def assert_server_is_demo(connection, *, allow_maintenance: bool = False) -> dict:
    """Gate 2: the server that answered is the approved local one.

    Takes an open psycopg connection rather than a DSN, so what is verified is the same
    session the caller is about to write through -- not a second connection that might
    resolve somewhere else.
    """
    row = connection.execute("""
        SELECT current_database()          AS database,
               host(inet_server_addr())    AS host,
               inet_server_port()          AS port,
               current_user                AS usr,
               version()                   AS version
    """).fetchone()
    database, host, port = row["database"], row["host"], int(row["port"])
    permitted = {DEMO_DATABASE} | ({MAINTENANCE_DATABASE} if allow_maintenance else set())

    if host in FORBIDDEN_HOSTS or database in FORBIDDEN_DATABASES:
        raise UnsafeTarget(
            f"the server answering is {host}/{database}, which is the Main/Core database")
    if host != DEMO_HOST:
        raise UnsafeTarget(f"server reports host {host!r}, expected {DEMO_HOST}")
    if port != DEMO_PORT:
        raise UnsafeTarget(f"server reports port {port}, expected {DEMO_PORT}")
    if database not in permitted:
        raise UnsafeTarget(
            f"server reports database {database!r}, expected one of {sorted(permitted)}")
    return dict(row)
