"""Entry point: python -m devhost [--reseed] [--port 8010]"""

import argparse
import asyncio
import os
import selectors
import sys
from pathlib import Path

import uvicorn

from .app import build
from .environment import (MissingConfiguration, check_port, database_url, demo_port,
                          redacted)


def loop_factory():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="devhost")
    parser.add_argument("--dsn", default=None,
                        help="overrides FINANCE_DEV_DSN for this run")
    parser.add_argument("--port", type=int, default=demo_port())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reseed", action="store_true",
                        help="drop and reload the development project on startup")
    parser.add_argument("--storage", default=str(Path(__file__).resolve().parent / ".files"))
    args = parser.parse_args()
    try:
        dsn = args.dsn or database_url()
    except MissingConfiguration as error:
        parser.exit(2, f"{error}\n")
    print(f"database: {redacted(dsn)}")
    check_port(args.host, args.port)
    print(f"serving on http://{args.host}:{args.port}")

    application = build(dsn, Path(args.storage), reseed=args.reseed)
    server = uvicorn.Server(uvicorn.Config(application, host=args.host, port=args.port,
                                           log_level="info", lifespan="on"))
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
