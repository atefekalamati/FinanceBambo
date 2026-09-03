"""Writes the API's own description to contracts/openapi.json.

The schema was always there — FastAPI builds it from the routes — but it was
never written down, so the frontend's mappers were the only statement of what
the API returns, kept in step by hand. Committing it puts a contract change in a
diff, where a reviewer can see it and the frontend can be told before it breaks.

    python scripts/export_openapi.py           # write
    python scripts/export_openapi.py --check    # fail if the file is stale

--check is what CI runs: it regenerates in memory and compares, so a route or a
field that moved without the contract being refreshed stops the build.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402

TARGET = pathlib.Path(__file__).resolve().parent.parent / "contracts" / "openapi.json"


def render() -> str:
    # sort_keys so the file is stable: a dict ordering change must never look
    # like a contract change in a diff.
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    rendered = render()
    check = "--check" in sys.argv

    if check:
        if not TARGET.exists():
            print(f"{TARGET.relative_to(TARGET.parents[1])} is missing. Run: python scripts/export_openapi.py")
            return 1
        if TARGET.read_text(encoding="utf-8") != rendered:
            print(
                f"{TARGET.relative_to(TARGET.parents[1])} is out of date — the API has changed since it was written.\n"
                "Run: python scripts/export_openapi.py"
            )
            return 1
        print(f"contract is current ({len(create_app().openapi()['paths'])} paths)")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(TARGET.parents[1])} ({len(create_app().openapi()['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
