"""Entry point: python -m devhost [--reseed] [--port 8010]"""

import argparse
import asyncio
import os
import selectors
import socket
import sys
from pathlib import Path

import uvicorn

from .app import build
from .environment import MissingConfiguration, database_url, demo_port, redacted


def loop_factory():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


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
