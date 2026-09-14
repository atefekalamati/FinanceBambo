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

test("the host gets the page it mounts, and not the one that enables demo data", () => {
  // index.html carries data-finance-runtime="standalone", which is the one way demo data
  // can appear at all. It is a development preview and no longer ships by default.
  assert.match(script, /WITH_PREVIEW \? \["host\.html", "index\.html"\] : \["host\.html"\]/);
  const bodyTag = (html) => html.match(/<body[^>]*>/)[0];
  assert.match(bodyTag(read("../../index.html")), /data-finance-runtime="standalone"/);
  // The tag, not the file: host.html explains the absence in a comment, and a
  // match on the whole file would be satisfied by that explanation.
  assert.doesNotMatch(bodyTag(read("../../host.html")), /data-finance-runtime/,
    "host.html must not carry the marker that switches on demo data");
});

test("the demo adapters are not in the package the host is served", () => {
  // They used to be, and the note in the packager said so: 117 KB the host never executed,
  // kept because a static import cannot be dropped without breaking the module. The
  // imports are dynamic now, reached only inside the standalone branch, so the folder is
  // outside the static graph the host build walks -- and the note says that instead.
  const bootstrap = read("../../src/app/bootstrap.js");
  const staticMockImports = (bootstrap.match(/^import .*adapters\/mock/gm) ?? []).length;
  assert.equal(staticMockImports, 0,
    "a static import puts the demo adapters back in the host's bundle");
  assert.ok((bootstrap.match(/import\(\s*"\.\.\/adapters\/mock/g) ?? []).length >= 8,
    "the preview still needs its adapters, reached dynamically");
  assert.match(script, /WHAT IS NO LONGER IN IT/);
  assert.doesNotMatch(script, /WHAT IS DELIBERATELY LEFT IN/,
    "the note must describe what the packager does now");
});
