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


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse KEY=value lines. Existing environment variables always win."""
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


def redacted(dsn: str) -> str:
    """A form safe to print: the password is replaced, never echoed."""
    if "://" not in dsn or "@" not in dsn:
        return dsn
    scheme, _, rest = dsn.partition("://")
    credentials, _, host = rest.rpartition("@")
    user = credentials.partition(":")[0] if ":" in credentials else credentials
    return f"{scheme}://{user}:***@{host}"
