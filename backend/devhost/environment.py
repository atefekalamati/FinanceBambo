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
from uuid import UUID

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


#: The central BAMBO server, and the one database on it Finance is allowed to touch.
#:
#: Named here rather than in each caller so there is one place to read the rule from and one
#: place to change it. The host is matched, not just the database name: `bambo` lives on this
#: same server, and a DSN that reached it would be writing Finance rows into the Core database.
CENTRAL_HOSTS = frozenset({"192.168.100.200"})
CENTRAL_DATABASE = "bambo_canonical_local"

#: Refused wherever they appear. `bambo` is Core's own database; `bambo_finance_dev` is the
#: superseded local one that `.env` still points at, which is how a host that looked correctly
#: configured spent a week reading an empty database nobody had migrated.
FORBIDDEN_DATABASES = frozenset({"bambo"})
OBSOLETE_DATABASES = frozenset({"bambo_finance_dev"})


def dsn_target(dsn: str):
    """`(host, database)` for a DSN, or `(None, None)` when it cannot be read.

    Accepts both the URL form and libpq keyword form. Unknown is returned rather than
    guessed: a rule applied to a misread address is worse than no rule, because it reads as
    enforcement while enforcing something else.
    """
    if not dsn:
        return None, None
    text = dsn.strip()
    if "://" in text:
        from urllib.parse import urlsplit
        parsed = urlsplit(text)
        return parsed.hostname, (parsed.path.lstrip("/") or None)
    keywords = dict(
        part.split("=", 1) for part in text.split() if "=" in part
    )
    return keywords.get("host"), keywords.get("dbname")


def check_runtime_dsn(name: str, dsn: str | None) -> str | None:
    """Refuse a runtime DSN that names a database Finance must not run against.

    Three rules, in the order a mistake is likely to be made:

      * anything on the central server must be `bambo_canonical_local`. This is what keeps a
        stray DSN out of `bambo`, and it is checked by address so renaming cannot bypass it;
      * `bambo_finance_dev` is refused everywhere. It is the superseded local database, and
        `.env` still points at it, so an unset environment variable silently lands there;
      * `bambo` is refused everywhere, on any host.

    A local database that is none of those is left alone: the demo builders and the test
    suite need one, and a lock that broke them would be turned off rather than obeyed.
    """
    host, database = dsn_target(dsn)
    if database is None:
        return dsn
    if database in FORBIDDEN_DATABASES:
        raise MissingConfiguration(
            f"{name} names database {database!r}, which belongs to Core.\n"
            f"Finance runs against {CENTRAL_DATABASE!r} and nothing else on that server."
        )
    if database in OBSOLETE_DATABASES:
        raise MissingConfiguration(
            f"{name} names {database!r}, the superseded local database.\n"
            f"Point it at {CENTRAL_DATABASE!r}, or unset {ENV_FILE}'s entry for it."
        )
    if host in CENTRAL_HOSTS and database != CENTRAL_DATABASE:
        raise MissingConfiguration(
            f"{name} names database {database!r} on the central server.\n"
            f"Only {CENTRAL_DATABASE!r} is permitted there."
        )
    return dsn


def check_runtime_pairing() -> None:
    """Refuse a Finance database and a Core database on opposite sides of the network.

    Finance rows in one place and the authorization they are gated by in another is a
    correctness hole that reports no error: every request is answered, and answered against a
    Core that knows nothing about the data being returned.
    """
    finance_host, finance_db = dsn_target(setting("FINANCE_DEV_DSN"))
    core_host, core_db = dsn_target(setting("FINANCE_CORE_DSN"))
    if core_db is None or finance_db is None:
        return
    finance_central = finance_host in CENTRAL_HOSTS
    core_central = core_host in CENTRAL_HOSTS
    if finance_central != core_central:
        raise MissingConfiguration(
            "FINANCE_DEV_DSN and FINANCE_CORE_DSN are on different servers "
            f"({finance_host} and {core_host}).\n"
            "Finance data and the Core that authorizes it must be the same database."
        )
    if finance_central and core_db != finance_db:
        raise MissingConfiguration(
            f"FINANCE_DEV_DSN names {finance_db!r} and FINANCE_CORE_DSN names {core_db!r} "
            "on the central server.\nBoth must be " f"{CENTRAL_DATABASE!r}."
        )


def database_url() -> str:
    dsn = setting("FINANCE_DEV_DSN")
    if not dsn:
        raise MissingConfiguration(
            "FINANCE_DEV_DSN is not set.\n"
            f"Copy {REPO_ROOT / '.env.example'} to {ENV_FILE} and fill in the password for\n"
            "the bambo_finance_app role, or export FINANCE_DEV_DSN in this shell."
        )
    check_runtime_pairing()
    return check_runtime_dsn("FINANCE_DEV_DSN", dsn)


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
    return check_runtime_dsn("FINANCE_CORE_DSN", setting("FINANCE_CORE_DSN"))


def core_identity_settings():
    """Which real person, organization and project the development host stands in for.

    Only meaningful with `FINANCE_CORE_DSN` set. The fixture identifiers in `devhost/seed.py`
    name a person who exists in the seeded demo and in no real Core database, so pointing the
    Core adapters at a real one and leaving them in place asks Core about somebody who is not
    there. Core answers correctly -- no membership, no permissions, 403 -- and the page reads
    as a permission problem when it is a configuration one.

    This changes *who is calling* and nothing else. Membership, roles, permissions and every
    gate still come from Core's own tables for whoever is named here: naming a user grants
    them nothing, exactly as a real host session grants nothing by itself.

    Returns `(user_id, organization_id, project_id)`, each None when unset.
    """
    user = setting("FINANCE_DEMO_USER_ID")
    organization = setting("FINANCE_DEMO_ORGANIZATION_ID")
    project = setting("FINANCE_DEMO_PROJECT_ID")
    parsed_user = _uuid_setting("FINANCE_DEMO_USER_ID", user)
    parsed_organization = _uuid_setting("FINANCE_DEMO_ORGANIZATION_ID", organization)
    return parsed_user, parsed_organization, (project.strip() if project else None)


def _uuid_setting(name: str, value: str | None):
    """A UUID setting, or a refusal naming the setting.

    Falling back to the fixture on a typo would start the host against a real Core database
    under an identity nobody chose, and the only symptom would be a 403 that looks like the
    one this setting exists to fix.
    """
    if not value or not value.strip():
        return None
    try:
        return UUID(value.strip())
    except ValueError as error:
        raise MissingConfiguration(f"{name} is not a UUID: {value.strip()!r}") from error


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


#: The value that turns the local models on. Anything else -- unset, blank, a typo --
#: leaves the refusing stand-in in place, which is the safe direction: a misspelt setting
#: must not silently start a host that cannot extract but says it can.
SELF_HOSTED_EXTRACTION = "self_hosted"


def extraction_provider() -> str:
    """Which extraction providers the host installs. `UnavailableExtractor` unless told.

    Deliberately a NAME rather than a boolean. There will be more than one answer -- a
    hosted API, a different local model -- and `EXTRACTION_AI=1` would have to be replaced
    the first time a second option existed, while a name only gains a value.
    """
    return (setting("EXTRACTION_PROVIDER", "") or "").strip().lower()


# --------------------------------------------------------------------------- MPP import
#
# Core owns MPP file handling; these settings say where the development host may read
# schedule files from and how often the periodic import looks at them. Every default is
# the OFF position: an unconfigured host imports nothing.

def mpp_import_enabled() -> bool:
    """Whether the periodic MPP import runs at all. Off unless explicitly on."""
    return (setting("MPP_IMPORT_ENABLED", "") or "").strip().lower() in ("1", "true", "yes", "on")


def mpp_import_root():
    """The ONLY directory MPP files may be read from. None means no imports.

    Callers hand the importer a name RELATIVE to this root; the resolver collapses
    `..`, follows symlinks and re-checks containment, so configuration is the whole
    attack surface and it is one line.
    """
    value = setting("MPP_IMPORT_ROOT")
    return value.strip() if value and value.strip() else None


def mpp_max_file_size_mb() -> int:
    """Upper bound on an importable file. A schedule is megabytes, not gigabytes."""
    raw_value = (setting("MPP_MAX_FILE_SIZE_MB", "") or "").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 0
    return parsed if parsed > 0 else 100


def mpp_import_interval_minutes() -> int:
    """How often the periodic import re-examines the configured files."""
    raw_value = (setting("MPP_IMPORT_INTERVAL_MINUTES", "") or "").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 0
    return parsed if parsed > 0 else 60


def mpp_java_home():
    """The FULL JRE MPXJ runs on. None falls back to the process JAVA_HOME.

    Full, not minimal: a jlink'd runtime without jdk.charsets dies inside MPXJ's own
    charset initialiser asking for MacRoman, before any file is opened.
    """
    value = setting("MPP_JAVA_HOME")
    return value.strip() if value and value.strip() else None


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
