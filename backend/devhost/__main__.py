"""Entry point: python -m devhost [--reseed] [--port 8000]"""

import argparse
import asyncio
import os
import selectors
import sys
from pathlib import Path

import uvicorn

from .app import build

# A locally installed PostgreSQL. Docker is only a fallback and publishes on 55433,
# so the two can run side by side without either shadowing the other.
DEFAULT_DSN = "postgresql://bambo:bambo@127.0.0.1:55432/bambo_finance"


def loop_factory():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="devhost")
    parser.add_argument("--dsn", default=os.environ.get("FINANCE_DEV_DSN", DEFAULT_DSN))
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reseed", action="store_true",
                        help="drop and reload the development project on startup")
    parser.add_argument("--storage", default=str(Path(__file__).resolve().parent / ".files"))
    args = parser.parse_args()

    application = build(args.dsn, Path(args.storage), reseed=args.reseed)
    server = uvicorn.Server(uvicorn.Config(application, host=args.host, port=args.port,
                                           log_level="info", lifespan="on"))
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
