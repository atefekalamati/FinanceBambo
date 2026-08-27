# -*- coding: utf-8 -*-
"""The development host must not let a browser cache what it serves.

`StaticFiles` sends an ETag and a Last-Modified header, so a browser revalidates and, on a
304, re-runs the copy it already had. That is correct for a CDN and wrong for source files
that change every time somebody edits them.

The failure it produces is a bad one to debug. The server sends the correct bytes, the
browser never asks for them, and the page renders from a stale module whose imports no
longer resolve. Nothing in the log says anything is wrong except a 304 and a scatter of 404s
for files this repository does not contain -- so the evidence points at the server, which is
the one place that is behaving correctly.

Two defences, tested here: refuse to be cached at all, and give the entry point a URL unique
to each process so an already-stored copy cannot be reused either.
"""

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urljoin

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = BACKEND_ROOT.parent / "frontend"
sys.path.insert(0, str(BACKEND_ROOT))


class NoStoreHeaderTests(unittest.TestCase):
    def source(self):
        return (BACKEND_ROOT / "devhost" / "app.py").read_text(encoding="utf-8")

    def test_the_middleware_sets_no_store(self):
        self.assertIn('response.headers["Cache-Control"] = "no-store"', self.source())

    def test_no_store_is_set_for_every_response_not_only_the_api(self):
        """The static modules are the ones that matter, and they are not under /api/.

        Asserted by position: the header must be set before the branch that only runs for
        API paths, or the files this test exists to protect are left out.
        """
        source = self.source()
        header = source.index('response.headers["Cache-Control"] = "no-store"')
        api_branch = source.index('if request.url.path.startswith("/api/"):',
                                  source.index("async def one_request_at_a_time"))
        self.assertLess(header, api_branch,
                        "Cache-Control is set inside the API-only branch")

    def test_no_cache_is_not_used_instead(self):
        """`no-cache` still stores the response and revalidates.

        Revalidation returning 304 is exactly what re-runs the stale module, so the weaker
        directive would leave the bug in place while looking like a fix.
        """
        self.assertNotIn('"no-cache"', self.source())


class EntryPointFreshnessTests(unittest.IsolatedAsyncioTestCase):
    def build(self):
        from devhost.app import build
        # The DSN is never opened: only the index route and the static mounts are exercised,
        # and the lifespan that would connect is not entered.
        return build("postgresql://stub@127.0.0.1:5432/stub", BACKEND_ROOT / "build" / "storage")

    async def client(self, application):
        import httpx
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
                                 base_url="http://demo")

    async def test_a_static_module_is_served_with_no_store(self):
        async with await self.client(self.build()) as client:
            response = await client.get("/src/app/bootstrap.js")
            self.assertEqual(200, response.status_code)
            self.assertEqual("no-store", response.headers.get("cache-control"))

    async def test_the_entry_point_url_is_unique_to_the_process(self):
        """`no-store` cannot undo what a browser already stored.

        StaticFiles sends Last-Modified and no max-age, so an existing copy may be reused
        for a heuristic fraction of its age without asking the server at all. A URL that has
        never been seen has nothing stored under it.
        """
        from devhost.app import BUILD_TOKEN
        async with await self.client(self.build()) as client:
            html = (await client.get("/")).text
        source = re.search(r'<script type="module" src="([^"]+)"', html).group(1)
        self.assertIn(f"?build={BUILD_TOKEN}", source)
        self.assertTrue(source.startswith("./src/app/bootstrap.js"))

    async def test_two_processes_do_not_share_an_entry_point_url(self):
        import importlib
        from devhost import app as first
        token = first.BUILD_TOKEN
        reloaded = importlib.reload(first)
        self.assertNotEqual(token, reloaded.BUILD_TOKEN)


class FrontendModuleGraphTests(unittest.TestCase):
    """Every relative import in the frontend resolves to a file that exists.

    This is the property whose absence produced a blank page: the browser requested modules
    that were not there, each 404 was silent to anyone not reading the network panel, and
    the application simply never started.

    Checked on disk rather than over HTTP so it holds without a running server, and walked
    from the entry point so an unreachable file cannot mask a broken one.
    """

    IMPORT = re.compile(
        r"""(?:import|export)\s+(?:[^'"]*?\sfrom\s+)?['"](\.[^'"]+)['"]""")

    def test_the_graph_from_the_entry_point_is_complete(self):
        entry = "src/app/bootstrap.js"
        seen, missing, queue = set(), [], [entry]
        while queue:
            relative = queue.pop()
            if relative in seen:
                continue
            seen.add(relative)
            path = FRONTEND_ROOT / relative
            if not path.is_file():
                missing.append(relative)
                continue
            for imported in self.IMPORT.findall(path.read_text(encoding="utf-8")):
                queue.append(urljoin(relative, imported.split("?")[0]))
        self.assertEqual([], sorted(missing), "imported modules that do not exist")
        # A guard against the walk silently collapsing to the entry point alone.
        self.assertGreater(len(seen), 50, "the graph walk covered almost nothing")

    def test_the_entry_point_is_the_one_the_html_loads(self):
        html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="./src/app/bootstrap.js"', html)


if __name__ == "__main__":
    unittest.main()
