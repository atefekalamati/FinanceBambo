"""Read development configuration from the environment, never from the repository.

The connection string carries a password, so it has no default here: an absent
FINANCE_DEV_DSN is a setup error the developer has to see, not something to paper over
with a guessable credential committed to git.

`.env` at the repository root is read as a convenience and is git-ignored. It is parsed
here rather than through python-dotenv so the development host adds no dependency the
deployed module would have to carry.
"""

import os
import socket
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class MissingConfiguration(RuntimeError):
    pass


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse KEY=value lines. Existing environment variables always win.

    The path is resolved on each call rather than bound as a default, so the file is
    picked up if it appears after import.
    """
    path = ENV_FILE if path is None else path
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def setting(name: str, default: str | None = None) -> str | None:
    if name in os.environ:
        return os.environ[name]
    return load_env_file().get(name, default)


def database_url() -> str:
    dsn = setting("FINANCE_DEV_DSN")
    if not dsn:
        raise MissingConfiguration(
            "FINANCE_DEV_DSN is not set.\n"
            f"Copy {REPO_ROOT / '.env.example'} to {ENV_FILE} and fill in the password for\n"
            "the bambo_finance_app role, or export FINANCE_DEV_DSN in this shell."
        )
    return dsn


def migration_url() -> str | None:
    """The role allowed to run DDL, if one is configured.

    Migrations create tables and triggers; the application role deliberately cannot. In a
    deployed environment this is a separate step in the release, run by an owner role, and
    the service never holds those rights. The development host mirrors that split rather
    than granting CREATE to the runtime role for convenience.
    """
    return setting("FINANCE_MIGRATION_DSN")


#: The port the finance development host listens on.
#:
#: Deliberately not 8000. That is the default half the tooling on a developer machine
#: reaches for first, so a host that took it would be the one competing for it. Choosing a
#: less contested number costs nothing and removes a whole class of "why am I looking at
#: something else" confusion.
DEFAULT_DEMO_PORT = 8010

DEMO_PORT_SETTING = "FINANCE_DEMO_PORT"


def demo_port() -> int:
    """The port to serve on: FINANCE_DEMO_PORT if set, otherwise 8010.

    Defined here so the entry point and the demo script cannot disagree about it. A value
    that is not a number is ignored rather than fatal -- the default is always usable, and
    refusing to start over a typo in an optional setting helps nobody.
    """
    configured = (setting(DEMO_PORT_SETTING) or "").strip()
    if configured.isdigit() and 0 < int(configured) < 65536:
        return int(configured)
    return DEFAULT_DEMO_PORT


#: Whether a port is ours to take. Lives here rather than in the entry point so the
#: port policy is in one module, and so reading it does not drag in a web server:
#: importing `devhost.__main__` for this one function pulled uvicorn into every
#: caller, which is how the test suite acquired a dependency nobody had declared.
def check_port(host: str, port: int) -> None:
    """Stop before binding if the port is already answering.

    Two things this deliberately does not do:

      * it does not move to another port. A host that silently relocates is one nobody can
        write instructions for, and the browser ends up somewhere the reader was not told
        about;
      * it does not stop whatever is listening. This process did not start it and has no
        idea what it is, so it is reported and left alone.

    Binding without checking would fail anyway, but with an OSError from inside the server
    rather than a sentence saying what to do about it.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(1)
        occupied = probe.connect_ex((host, port)) == 0
    finally:
        probe.close()
    if occupied:
        raise SystemExit(
            f"Port {port} is already in use on {host}.\n"
            "Free it, or choose another port with --port or FINANCE_DEMO_PORT."
        )


def core_url() -> str | None:
    """The database holding the BAMBO Core tables, if the Core adapters are to be used.

    Absent by default, and that default is the previous behaviour exactly: the host wires
    its static fixtures and grants one operator every finance permission.

    When it is set, membership, roles and permissions come from Core's own tables instead,
    and the difference is immediately visible -- `finance_report.issue` does not exist in
    Core's catalogue, so issuing a report is refused.

    A separate setting from FINANCE_DEV_DSN even though the demo points both at one
    database. Core and Finance are separate schemas owned by separate teams and may well be
    separate databases; a single variable would quietly assume otherwise.
    """
    return setting("FINANCE_CORE_DSN")


def core_progress_enabled() -> bool:
    """Whether progress should be read from Core's MSP tables rather than the host feed.

    Off by default, and the default is the honest production shape rather than a
    convenience. Core stores parsed schedules -- `msp_tasks` has percentages and no resource
    or quantity columns at all -- so the Core adapter can report that a task is 30% done and
    nothing about how much rebar that represents. Finance then marks every line
    `unavailable` with a warning, which is correct and shows almost nothing on a dashboard.

    Assignment-level quantities come from whatever publishes them: the host's progress
    module. `devhost` stands in for that with a seeded feed, so the demo shows the numbers a
    wired host would supply.

    Turn this on to see the other half of the truth -- what Core alone can and cannot
    answer. It is the same code path a production host would use if it had no progress
    module, and the warnings it produces are the point.
    """
    return (setting("FINANCE_CORE_PROGRESS", "") or "").strip().lower() in ("1", "true", "yes", "on")


def app_env() -> str:
    """The environment name, defaulting to development when unset.

    The default is for description -- log lines, the "seed DISABLED" notice -- not for
    authorization. `seeding_allowed()` deliberately reads the raw setting instead, because a
    default that means "development" would let an unconfigured environment authorize writes.
    """
    return (setting(APP_ENV_SETTING, "development") or "development").strip().lower()


#: Environments where seeding is even conceivable. Staging is deliberately absent: it is a
#: deployed environment, and demo rows in a deployed environment are indistinguishable from
#: real ones to everyone looking at it.
SEEDABLE_ENVIRONMENTS = ("development", "dev", "test")

#: The positive authorization seeding now requires, on top of a seedable environment.
SEED_OPT_IN = "FINANCE_ALLOW_SEED"

#: Named once so `app_env()` and `seeding_allowed()` cannot end up reading different keys.
#: They read the same setting for different purposes: one describes, the other authorizes.
APP_ENV_SETTING = "APP_ENV"


def seed_opt_in() -> bool:
    """Whether someone has explicitly authorized fixture data in this environment."""
    return (setting(SEED_OPT_IN, "") or "").strip().lower() in ("1", "true", "yes", "on")


def seeding_allowed() -> bool:
    """Whether development fixtures may be loaded. Fails closed.

    Two explicit positive conditions, both required, neither with a default:

      1. APP_ENV is **configured** and names a seedable environment, and
      2. FINANCE_ALLOW_SEED explicitly says yes.

    `app_env()` is deliberately not used here. It substitutes "development" when APP_ENV is
    unset, which is a sensible default for describing an environment but a dangerous one for
    authorizing writes: an environment that had simply never been configured would satisfy
    condition 1 by accident, and with the opt-in set would seed. So this reads the raw
    setting and treats absent or blank as a refusal.

    That is the whole rule: **no default may authorize fixture insertion.** Production must
    never receive demo data, and "never" cannot rest on a variable being remembered.

    Staging is not a seedable environment. It is deployed, and demo invoices there look
    exactly like real ones to anyone reviewing it.

    The check is on the environment rather than the connection string on purpose: a
    production DSN in a misconfigured shell would otherwise be seeded silently.
    """
    configured = (setting(APP_ENV_SETTING) or "").strip().lower()
    if not configured:
        return False
    return configured in SEEDABLE_ENVIRONMENTS and seed_opt_in()


def redacted(dsn: str) -> str:
    """A form safe to print: the password is replaced, never echoed."""
    if "://" not in dsn or "@" not in dsn:
        return dsn
    scheme, _, rest = dsn.partition("://")
    credentials, _, host = rest.rpartition("@")
    user = credentials.partition(":")[0] if ":" in credentials else credentials
    return f"{scheme}://{user}:***@{host}"
