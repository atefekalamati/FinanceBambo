# -*- coding: utf-8 -*-
"""The finance demo stays on its own port and inside its own repository.

Another BAMBO application -- the Pilot host -- listens on port 8000 on a developer machine.
Two servers cannot share a port, and the failure is nastier than a crash: whichever binds
first wins, so a browser pointed at 8000 can open the wrong application entirely while every
instruction in the demo guide still reads correctly.

These tests fix both halves of that: the port the demo takes, and the absence of any
reference from this repository into another project.
"""

import ast
import os
import re
import socket
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
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

    def test_port_8000_is_refused_by_name(self):
        """Refused explicitly rather than merely not chosen.

        A stale command line or a copied instruction naming 8000 then fails with an
        explanation, instead of colliding with whatever is already there.
        """
        from devhost.__main__ import check_port
        with self.assertRaises(SystemExit) as caught:
            check_port("127.0.0.1", 8000)
        message = str(caught.exception)
        for expected in ("8000", "Pilot", "8010"):
            with self.subTest(expected=expected):
                self.assertIn(expected, message)

    def test_an_occupied_port_stops_the_host_rather_than_moving_it(self):
        """Two refusals to keep separate: reserved, and simply busy.

        Neither is handled by silently picking another port -- a demo that moves is a demo
        nobody can write instructions for -- and the process already listening belongs to
        somebody, so it is reported and never stopped.
        """
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            from devhost.__main__ import check_port
            with self.assertRaises(SystemExit) as caught:
                check_port("127.0.0.1", port)
            self.assertIn("already in use", str(caught.exception))
        finally:
            listener.close()

    def test_a_free_port_is_accepted(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        from devhost.__main__ import check_port
        check_port("127.0.0.1", port)

    def test_neither_entry_point_still_defaults_to_8000(self):
        """A grep for "8000" would be useless: the fixture UUIDs are full of `-4000-8000-`.

        So this asserts on the argparse default expression instead, and on both entry
        points reading the same shared function rather than repeating a number.
        """
        for relative in ("devhost/__main__.py", "scripts/demo/prepare.py"):
            with self.subTest(relative=relative):
                text = (BACKEND_ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn('"--port", type=int, default=8000', text)
                self.assertIn("default=demo_port()", text)

    def test_the_port_number_appears_in_no_executable_line(self):
        """Both entry points call `demo_port()`; neither hardcodes the number.

        Docstrings and comments are stripped first. A usage line reading `[--port 8010]` is
        documentation, and documentation that names the default is a good thing -- it is
        duplicated *configuration* that drifts, not duplicated prose.
        """
        from devhost import environment
        number = str(environment.DEFAULT_DEMO_PORT)
        for relative in ("devhost/__main__.py", "scripts/demo/prepare.py"):
            with self.subTest(relative=relative):
                tree = ast.parse((BACKEND_ROOT / relative).read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                        continue                       # a bare string expression: a docstring
                    if isinstance(node, ast.Constant) and str(node.value) == number:
                        self.fail(f"{relative} line {node.lineno} hardcodes {number}")


class PilotIsolationTests(unittest.TestCase):
    """Nothing here may reach into another BAMBO project.

    Scanned rather than asserted once, so a future import is caught by a failing test
    instead of by somebody noticing during a demo.
    """

    SOURCE_ROOTS = ("app", "coreint", "devhost", "scripts", "tests", "alembic")
    FRONTEND = BACKEND_ROOT.parent / "frontend" / "src"

    def python_sources(self):
        for root in self.SOURCE_ROOTS:
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" not in path.parts:
                    yield path

    def all_sources(self):
        yield from self.python_sources()
        yield from self.FRONTEND.rglob("*.js")

    def test_nothing_references_another_project_repository(self):
        """This file is excluded from its own scan.

        It has to spell the forbidden strings out in order to search for them, so scanning
        itself would fail every time and say nothing about the code under test. Every other
        file, including every other test, is scanned.
        """
        needles = ("bamboo/platform", "bamboo" + BACKSLASH + "platform",
                   "e:" + BACKSLASH + "bamboo", "e:/bamboo")
        scanned = 0
        for path in self.all_sources():
            if path.resolve() == Path(__file__).resolve():
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8").lower()
            for needle in needles:
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, text)
        # Guards against the exclusion above silently becoming "scan nothing".
        self.assertGreater(scanned, 100, "the sweep covered almost no files")

    def test_nothing_imports_a_pilot_module(self):
        for path in self.python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    root = name.split(".")[0].lower()
                    with self.subTest(path=path.name, name=name):
                        self.assertNotIn(root, {"pilot", "pilot_app", "bamboo_pilot"})

    def test_the_deployable_library_reads_nothing_from_an_absolute_path(self):
        """`app/` and `coreint/` are the parts a host installs.

        A hardcoded drive letter in either would tie a deployed module to one developer's
        machine -- which is how a demo quietly starts depending on a directory nobody else
        has.
        """
        pattern = re.compile(r"[A-Za-z]:[/" + BACKSLASH + BACKSLASH + "]")
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                with self.subTest(path=str(path.relative_to(BACKEND_ROOT))):
                    self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))

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

    def test_the_development_seed_is_finance_data_and_depends_on_nothing_else(self):
        """`devhost.seed` is the finance demo fixture, mirrored from the frontend's own
        mock adapters. It imports three standard-library modules and nothing more, so it
        cannot be carrying data in from another project.
        """
        source = (BACKEND_ROOT / "devhost" / "seed.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual({"datetime", "decimal", "uuid"}, imported)

        from devhost import seed
        self.assertEqual("sample_site_01", seed.PROJECT_ID)
        # Every fixture id comes from one of the declared families, which is what separates
        # a fixture row from a row created through the API.
        self.assertIn("30000000", seed.FIXTURE_ID_PREFIXES)

    def test_the_core_mirror_seed_takes_its_values_from_the_finance_fixture(self):
        """Alignment is built, not maintained: the mirror imports the same constants.

        If it typed them instead, the two could drift and nothing would notice.
        """
        from devhost import seed
        from scripts.demo import seed_core_mirror
        self.assertIs(seed.ORGANIZATION_ID, seed_core_mirror.statements.__globals__["seed"].ORGANIZATION_ID)
        self.assertEqual(seed.ACTOR_ID, seed_core_mirror.FINANCE_EXPERT)
        self.assertEqual(seed.IMPORTER_ID, seed_core_mirror.PLANNER)

    def test_no_demo_user_carries_contactable_personal_data(self):
        """Synthetic people only, and deliberately not contactable.

        A table of plausible-looking names with real-looking emails and phone numbers is
        the kind of thing that gets copied somewhere it should not be.
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
        # Five synthetic people, every id from the reserved fixture family.
        self.assertEqual(5, len(seed_core_mirror.USERS))
        for user_id, _name in seed_core_mirror.USERS:
            with self.subTest(user_id=str(user_id)):
                self.assertTrue(str(user_id).startswith("aaaaaaaa-aaaa-"))


if __name__ == "__main__":
    unittest.main()
