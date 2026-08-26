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
from .environment import (MissingConfiguration, RESERVED_PORTS, database_url,
                          demo_port, redacted)


def loop_factory():
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def check_port(host: str, port: int) -> None:
    """Refuse to start unless this exact port is ours to take.

    Two separate refusals, because they are different mistakes:

      * a reserved port is one another BAMBO application owns, and taking it would either
        fail or -- worse -- serve the wrong application to a browser pointed at it;
      * an occupied port is already answering, and whatever is answering is not ours.

    Neither is handled by picking a different port. A demo that silently moves is a demo
    nobody can write instructions for, and the process already listening belongs to
    somebody: it is reported, never stopped.
    """
    if port in RESERVED_PORTS:
        raise SystemExit(
            f"refusing to serve on port {port}: it is reserved for "
            f"{RESERVED_PORTS[port]}.\n"
            f"The finance demo uses {demo_port()}. Run without --port, or pass a free one."
        )
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(1)
        occupied = probe.connect_ex((host, port)) == 0
    finally:
        probe.close()
    if occupied:
        raise SystemExit(
            f"port {port} is already in use on {host}, and this host will not take it.\n"
            "Whatever is listening there was not started by the finance demo, so it is\n"
            "left alone. Stop it yourself, or choose another port with --port."
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
