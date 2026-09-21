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


#: Where the OCR and speech packages live. Named here rather than discovered, because the
#: point of the message is to tell somebody which interpreter to use.
CANONICAL_ENVIRONMENT = "backend/ai-extraction-env"


def warn_if_extraction_cannot_run():
    """Say so at STARTUP when this interpreter has no PaddleOCR. Never blocks.

    WHY AT STARTUP AND NOT AT THE FIRST REQUEST

    `ImageExtractionAdapter` imports its provider lazily -- deliberately, so a host that
    never processes an image does not pay for several gigabytes of deep-learning runtime.
    The cost of that is that the wrong interpreter looks completely healthy: every endpoint
    serves, the logs are clean, and the fault appears much later as a 500 on one upload,
    by which time the person is debugging the invoice rather than the environment.

    `find_spec` is the whole check. It reads the import metadata and does NOT import the
    package, so it costs nothing measurable and cannot trigger the model load this warning
    exists to protect. That is what makes it safe to run on every start.

    It warns and returns. A host with no OCR is a perfectly ordinary thing to run -- most
    development does not touch extraction -- so this is a note about what will not work,
    not a refusal to start.
    """
    import importlib.util

    if importlib.util.find_spec("paddleocr") is not None:
        return False
    print("")
    print("  WARNING  this interpreter cannot run invoice extraction.")
    print("           `paddleocr` is not installed in it, so every call to")
    print("           POST /files/{fileId}/extractions will fail at request time.")
    print("")
    print("           current interpreter   %s" % sys.executable)
    print("           expected              %s/Scripts/python.exe" % CANONICAL_ENVIRONMENT)
    print("")
    print("           Start the host with backend/scripts/dev/run_devhost.cmd, which")
    print("           names that interpreter outright. Everything else serves normally.")
    print("")
    return True


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
    warn_if_extraction_cannot_run()
    print(f"database: {redacted(dsn)}")
    check_port(args.host, args.port)
    print(f"serving on http://{args.host}:{args.port}")

    application = build(dsn, Path(args.storage), reseed=args.reseed)
    server = uvicorn.Server(uvicorn.Config(application, host=args.host, port=args.port,
                                           log_level="info", lifespan="on"))
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
