# -*- coding: utf-8 -*-
"""TEST_ONLY -- DISPOSABLE. The gate every destructive step in this probe passes first.

Modelled on `scripts/demo/target.py`, deliberately as a separate module rather than by
widening that one. The demo gate permits exactly one database; teaching it a second name
would loosen a safety check that protects unrelated work in order to serve a throwaway
probe. A new target gets a new gate.

Two independent checks, because they fail in different ways:

  1. `assert_dsn_targets_scratch` reads the connection string, before a socket is opened. A
     DSN is only a claim about where it points, but it is a cheap one to check.
  2. `assert_server_is_scratch` asks the server that actually answered. This is the check
     that matters: a tunnel, a `pg_hba` redirect or a stale port-forward can all make a
     loopback DSN arrive somewhere else, and only the server can settle it.

Every database this must never touch is named in `FORBIDDEN_DATABASES` rather than merely
failing to equal the approved one. Refusing by name produces an error that says what was
refused, and leaves a searchable record of what this module was written to prevent.
"""

from urllib.parse import urlsplit

#: The only server this probe may write to.
SCRATCH_HOST = "127.0.0.1"
SCRATCH_PORT = 5432

#: The only database this probe may write to, plus the maintenance database that has to be
#: reachable in order to create and drop it.
SCRATCH_DATABASE = "bambo_mpp_probe"
MAINTENANCE_DATABASE = "postgres"

#: The central database. Under a standing read-only instruction, and named here so an
#: attempt to reach it is refused with that reason rather than with a failed comparison.
CENTRAL_DATABASE = "bambo_canonical_local"

FORBIDDEN_HOSTS = frozenset({"192.168.100.200"})
FORBIDDEN_DATABASES = frozenset({
    "bambo",                             # Core's own database
    "bambo_finance_dev",                 # the shared development database
    CENTRAL_DATABASE,                    # central; read-only
    "bambo_finance_integration_demo",    # the demo database, owned by scripts/demo
})

#: Why each name is refused, so the error explains itself.
REASONS = {
    "bambo": "that is Core's own database",
    "bambo_finance_dev": "that is the shared development database",
    CENTRAL_DATABASE: "that is the central database, which is read-only",
    "bambo_finance_integration_demo": "that is the demo database, owned by scripts/demo",
}


class UnsafeTarget(RuntimeError):
    """The target is not the approved local scratch database. Nothing should proceed."""


def parse_target(dsn: str) -> tuple[str, int, str]:
    """`(host, port, database)` as the connection string states them."""
    parts = urlsplit(dsn)
    return (parts.hostname or "", parts.port or 5432,
            parts.path.lstrip("/").split("?")[0])


def _check(host, port, database, allow_maintenance, source):
    permitted = {SCRATCH_DATABASE} | ({MAINTENANCE_DATABASE} if allow_maintenance else set())
    if host in FORBIDDEN_HOSTS:
        raise UnsafeTarget(
            "refusing %s (%s): that is the Main/Core server, which is read-only"
            % (host, source))
    if database in FORBIDDEN_DATABASES:
        raise UnsafeTarget("refusing database %r (%s): %s"
                           % (database, source, REASONS.get(database, "not permitted here")))
    if host != SCRATCH_HOST:
        raise UnsafeTarget("host must be %s, %s says %r" % (SCRATCH_HOST, source, host))
    if int(port) != SCRATCH_PORT:
        raise UnsafeTarget("port must be %s, %s says %s" % (SCRATCH_PORT, source, port))
    if database not in permitted:
        raise UnsafeTarget("database must be one of %s, %s says %r"
                           % (sorted(permitted), source, database))


def assert_dsn_targets_scratch(dsn: str, *, allow_maintenance: bool = False):
    """Gate 1: the DSN claims the approved local scratch target.

    `allow_maintenance` widens the permitted database to `postgres`, and only that -- it is
    needed to CREATE or DROP the scratch database, which cannot be done from inside it. Host
    and port are never widened.
    """
    host, port, database = parse_target(dsn)
    _check(host, port, database, allow_maintenance, "the DSN")
    return host, port, database


def assert_server_is_scratch(connection, *, allow_maintenance: bool = False) -> dict:
    """Gate 2: the server that answered is the approved local one.

    Takes an open connection rather than a DSN, so what is verified is the same session the
    caller is about to write through -- not a second one that might resolve elsewhere.
    """
    row = connection.execute("""
        SELECT current_database()       AS database,
               host(inet_server_addr()) AS host,
               inet_server_port()       AS port,
               current_user             AS usr,
               version()                AS version
    """).fetchone()
    _check(row["host"], row["port"], row["database"], allow_maintenance,
           "the server that answered")
    return dict(row)
