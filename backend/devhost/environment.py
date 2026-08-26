"""Read development configuration from the environment, never from the repository.

The connection string carries a password, so it has no default here: an absent
FINANCE_DEV_DSN is a setup error the developer has to see, not something to paper over
with a guessable credential committed to git.

`.env` at the repository root is read as a convenience and is git-ignored. It is parsed
here rather than through python-dotenv so the development host adds no dependency the
deployed module would have to carry.
"""

import os
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
