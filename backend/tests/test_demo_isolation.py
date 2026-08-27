# -*- coding: utf-8 -*-
"""The demo host stays on its own port and inside its own repository.

Two independent properties, both easy to lose by accident and both invisible until a demo:

  * **Which socket it binds.** One place decides the port, both entry points read it, and a
    port that is already answering stops the host rather than moving it or clearing it.
  * **What it reaches for.** Nothing here may depend on a path outside this repository, and
    the browser may only talk to the origin that served it.
"""

import ast
import os
import re
import socket
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

BACKSLASH = chr(92)


class DemoPortTests(unittest.TestCase):
    def test_the_default_port_is_8010(self):
        from devhost.environment import DEFAULT_DEMO_PORT, demo_port
        self.assertEqual(8010, DEFAULT_DEMO_PORT)
        self.assertEqual(8010, demo_port())

    def test_the_port_is_overridable_through_the_existing_settings_mechanism(self):
        """No new configuration system: `setting()` is what every other option uses."""
        from devhost import environment
        previous = os.environ.get(environment.DEMO_PORT_SETTING)
        try:
            os.environ[environment.DEMO_PORT_SETTING] = "8011"
            self.assertEqual(8011, environment.demo_port())
            # A typo must not stop the host starting. The default is always usable, and
            # refusing to boot over a malformed optional setting helps nobody.
            for nonsense in ("", "   ", "abc", "0", "70000", "-1", "80.10"):
                with self.subTest(nonsense=nonsense):
                    os.environ[environment.DEMO_PORT_SETTING] = nonsense
                    self.assertEqual(8010, environment.demo_port())
        finally:
            os.environ.pop(environment.DEMO_PORT_SETTING, None)
            if previous is not None:
                os.environ[environment.DEMO_PORT_SETTING] = previous

    def test_an_occupied_port_stops_the_host_rather_than_moving_it(self):
        """A host that silently relocates is one nobody can write instructions for.

        The message has to name the port and say what to do, because the alternative is an
        OSError raised from inside the server after startup has already begun.
        """
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            from devhost.__main__ import check_port
            with self.assertRaises(SystemExit) as caught:
                check_port("127.0.0.1", port)
            message = str(caught.exception)
            self.assertIn(f"Port {port} is already in use", message)
            self.assertIn("--port", message)
        finally:
            listener.close()

    def test_a_free_port_is_accepted(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        from devhost.__main__ import check_port
        check_port("127.0.0.1", port)

    def test_the_host_never_stops_whatever_is_listening(self):
        """It did not start that process and has no idea what it is.

        Asserted against the source, because the only way to test the behaviour directly is
        to leave something running and see whether it survives -- and a test that kills the
        wrong process on a developer machine is a worse outcome than the bug.
        """
        source = (BACKEND_ROOT / "devhost" / "__main__.py").read_text(encoding="utf-8")
        for weapon in ("kill", "terminate", "taskkill", "Stop-Process", "SIGKILL",
                       "SIGTERM", "pg_terminate_backend"):
            with self.subTest(weapon=weapon):
                self.assertNotIn(weapon, source)

    def test_neither_entry_point_hardcodes_the_port_number(self):
        """A grep for the number would be useless: the fixture UUIDs are full of digits.

        So this walks the syntax tree instead, and skips docstrings -- a usage line reading
        `[--port 8010]` is documentation, and documentation that names the default is a good
        thing. It is duplicated *configuration* that drifts.
        """
        from devhost import environment
        number = str(environment.DEFAULT_DEMO_PORT)
        for relative in ("devhost/__main__.py", "scripts/demo/prepare.py"):
            with self.subTest(relative=relative):
                text = (BACKEND_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("default=demo_port()", text)
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                        continue                       # a bare string expression: a docstring
                    if isinstance(node, ast.Constant) and str(node.value) == number:
                        self.fail(f"{relative} line {node.lineno} hardcodes {number}")


class RepositoryBoundaryTests(unittest.TestCase):
    """Nothing here may depend on anything outside this repository.

    Scanned rather than asserted once, so the next stray absolute path is caught by a
    failing test instead of by somebody noticing during a demo.
    """

    SOURCE_ROOTS = ("app", "coreint", "devhost", "scripts", "tests", "alembic")
    FRONTEND = REPO_ROOT / "frontend" / "src"

    def python_sources(self):
        for root in self.SOURCE_ROOTS:
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" not in path.parts:
                    yield path

    def test_the_deployable_library_reads_nothing_from_an_absolute_path(self):
        """`app/` and `coreint/` are the parts a host installs.

        A hardcoded drive letter or root path in either would tie a deployed module to one
        developer's machine -- which is how something quietly starts depending on a
        directory nobody else has.
        """
        drive_letter = re.compile(r"[A-Za-z]:[/" + BACKSLASH + BACKSLASH + "]")
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=str(path.relative_to(BACKEND_ROOT))):
                    self.assertIsNone(drive_letter.search(text))
                    self.assertNotIn('Path("/', text)

    def test_no_module_walks_out_of_the_repository(self):
        """`parents[n]` climbing past the repository root reaches a sibling checkout.

        `backend/x.py` is two levels below the root, so `parents[2]` is already outside it.
        Nested modules are deeper and get proportionally more room.
        """
        climb = re.compile(r"parents\[(\d+)\]")
        for path in self.python_sources():
            depth = len(path.relative_to(REPO_ROOT).parts) - 1     # directories above it
            for level in (int(n) for n in climb.findall(path.read_text(encoding="utf-8"))):
                with self.subTest(path=str(path.relative_to(REPO_ROOT)), level=level):
                    self.assertLessEqual(level, depth,
                                         "resolves to a directory outside the repository")

    def test_the_frontend_names_no_absolute_origin(self):
        """The client resolves every path against `window.location.origin` and refuses to
        leave it, so the page can only ever call the host that served it.

        That is what makes moving the host to another port safe: there is no second place
        recording which port the API is on, and so no second place to forget.
        """
        client = (self.FRONTEND / "core" / "api" / "api-client.js").read_text(encoding="utf-8")
        self.assertIn("window.location.origin", client)
        self.assertIn("assertSameOrigin", client)
        for path in self.FRONTEND.rglob("*.js"):
            urls = re.findall(r"https?://[A-Za-z0-9_.:/-]+", path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                self.assertEqual([], [url for url in urls if "w3.org" not in url])

    def test_preparing_the_demo_reads_only_files_inside_this_repository(self):
        """The generator that reads a schema export from elsewhere is not part of a run.

        `core_mirror.sql` is committed, so building the demo database touches nothing
        outside the repository.
        """
        prepare = (BACKEND_ROOT / "scripts" / "demo" / "prepare.py").read_text(encoding="utf-8")
        self.assertNotIn("generate_core_mirror", prepare)
        self.assertIn("MIRROR_SQL", prepare)
        self.assertTrue((BACKEND_ROOT / "scripts" / "demo" / "core_mirror.sql").is_file())


class DemoDataProvenanceTests(unittest.TestCase):
    """Where the demo rows come from, and what they must never contain."""

    def test_the_development_seed_depends_on_nothing_but_the_standard_library(self):
        """`devhost.seed` is the finance demo fixture, mirrored from the frontend's own
        mock adapters. Three standard-library imports and nothing else, so it cannot be
        carrying data in from anywhere.
        """
        tree = ast.parse((BACKEND_ROOT / "devhost" / "seed.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual({"datetime", "decimal", "uuid"}, imported)

        from devhost import seed
        self.assertEqual("sample_site_01", seed.PROJECT_ID)
        # Every fixture id comes from a declared family, which is what separates a fixture
        # row from a row created through the API.
        self.assertIn("30000000", seed.FIXTURE_ID_PREFIXES)

    def test_the_core_mirror_seed_takes_its_values_from_the_finance_fixture(self):
        """Alignment is built, not maintained: the mirror imports the same constants.

        If it typed them instead, the two could drift and nothing would notice.
        """
        from devhost import seed
        from scripts.demo import seed_core_mirror
        self.assertEqual(seed.ACTOR_ID, seed_core_mirror.FINANCE_EXPERT)
        self.assertEqual(seed.IMPORTER_ID, seed_core_mirror.PLANNER)
        self.assertIs(seed, seed_core_mirror.statements.__globals__["seed"])

    def test_no_demo_person_is_contactable(self):
        """Synthetic people only, and deliberately without contact details.

        A table of plausible names carrying real-looking emails and phone numbers is the
        kind of thing that gets copied somewhere it should not be.
        """
        from scripts.demo import seed_core_mirror
        source = (BACKEND_ROOT / "scripts" / "demo" / "seed_core_mirror.py").read_text(
            encoding="utf-8")
        self.assertIn("INSERT INTO users (id, display_name, is_active)", source)
        for column in ("email", "phone", "password_hash", "avatar_path"):
            with self.subTest(column=column):
                self.assertNotIn(f"INTO users (id, display_name, {column}", source)
        self.assertIsNone(re.search(r"(\+?98|0)9" + r"\d{9}", source), "a phone-shaped value")
        self.assertIsNone(re.search(r"[a-z0-9_.]+@[a-z0-9-]+\.[a-z]{2,}", source),
                          "an email-shaped value")
        self.assertEqual(5, len(seed_core_mirror.USERS))
        for user_id, _name in seed_core_mirror.USERS:
            with self.subTest(user_id=str(user_id)):
                self.assertTrue(str(user_id).startswith("aaaaaaaa-aaaa-"))


if __name__ == "__main__":
    unittest.main()
