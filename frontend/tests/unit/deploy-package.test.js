import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const script = read("../../scripts/build-package.mjs");

test("the package is derived from the graph, never from a list", () => {
  // A hand-written manifest goes stale the first time someone adds a module and
  // does not think of it, and the failure is a blank page on the host's server
  // rather than a red test here. The script walks the same graph the browser
  // walks, so a new module is found by the same thing that loads it.
  assert.match(script, /const ENTRY_JS = "src\/app\/bootstrap\.js"/);
  assert.match(script, /const ENTRY_CSS = "src\/shared\/styles\/index\.css"/);
  assert.match(script, /async function closure/);
  // No array of file paths anywhere: that would be the list this replaces.
  assert.doesNotMatch(script, /"src\/features\//, "the script names a feature file directly");
});

test("the entry points it walks from are the ones the page actually loads", () => {
  // The guard that matters: if the entry moves and the script does not, it
  // copies a package around the wrong root and nothing here notices until the
  // host serves it.
  const host = read("../../host.html");
  assert.match(host, /src="\.\/src\/app\/bootstrap\.js"/);
  assert.match(host, /href="\.\/src\/shared\/styles\/index\.css"/);
  assert.ok(existsSync(fileURLToPath(new URL("../../src/app/bootstrap.js", import.meta.url))));
  assert.ok(existsSync(fileURLToPath(new URL("../../src/shared/styles/index.css", import.meta.url))));
});

test("a package short of a file is not written at all", () => {
  // Better no package than one quietly missing a module: the second kind fails
  // on the host's server, at load, with nothing in the console.
  assert.match(script, /if \(absent\.length\)/);
  assert.match(script, /process\.exit\(1\)/);
});

test("both mount pages ship, and only one of them is for the host", () => {
  // index.html carries data-finance-runtime="standalone", which is the one way
  // demo data can appear on the real site. host.html is what the host copies.
  assert.match(script, /const HTML = \["host\.html", "index\.html"\]/);
  const bodyTag = (html) => html.match(/<body[^>]*>/)[0];
  assert.match(bodyTag(read("../../index.html")), /data-finance-runtime="standalone"/);
  // The tag, not the file: host.html explains the absence in a comment, and a
  // match on the whole file would be satisfied by that explanation.
  assert.doesNotMatch(bodyTag(read("../../host.html")), /data-finance-runtime/,
    "host.html must not carry the marker that switches on demo data");
});

test("the mock adapters ship, because the imports that reach them are static", () => {
  // Removing the folder does not trim the package, it stops the module loading:
  // a 404 on a static import is a white page with nothing in the console. The
  // script says so where someone would go to delete them.
  const bootstrap = read("../../src/app/bootstrap.js");
  const staticMockImports = (bootstrap.match(/^import .*adapters\/mock/gm) ?? []).length;
  assert.ok(staticMockImports > 0, "the mock imports became dynamic; the package note is now wrong");
  assert.match(script, /WHAT IS DELIBERATELY LEFT IN/);
  assert.match(script, /src\/adapters\/mock/);
});
