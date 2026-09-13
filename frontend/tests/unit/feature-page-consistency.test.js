import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = fileURLToPath(new URL("../../src", import.meta.url));
const FEATURES_DIR = join(SRC_DIR, "features");

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) return walk(full);
    return entry.name.endsWith(".js") ? [[full.slice(SRC_DIR.length + 1).replaceAll("\\", "/"), readFileSync(full, "utf8")]] : [];
  });
}

const SOURCES = walk(SRC_DIR);
const PAGES = SOURCES.filter(([name]) => name.startsWith("features/") && name.endsWith("-page.js"));

test("every feature page renders its states through the shared page-state helper", () => {
  assert.ok(PAGES.length >= 10, "expected one module per finance route");
  // The destinations page fetches nothing — it is the static list of links that
  // used to close the overview — so it has no loading, empty or error state to
  // render. Every page that does ask the service for something is still held to
  // the shared helper.
  const STATELESS = new Set();
  const offenders = PAGES
    .filter(([name]) => !STATELESS.has(name))
    .filter(([, source]) => !source.includes("renderPageState("))
    .map(([name]) => name);
  assert.deepEqual(
    offenders,
    [],
    "hand-rolled loading/empty/error/denied cards lose role=alert, aria-live, focus handling, the error code and the request id",
  );
});

/**
 * WHY THIS EXISTS
 * `settings-page.js` called `actorLabel(...)` and never imported it. The page threw
 * `ReferenceError: actorLabel is not defined` inside the render of the revision-history
 * table -- which runs inside an async load, so it surfaced as an unhandled promise
 * rejection and the page simply stopped drawing. It survived because the code path needs a
 * project that HAS settings revisions, and the seeded demo project has none.
 *
 * Nothing in the suite asks whether a module imports what it calls, so nothing could have
 * caught it. This asks, for every shared and core helper, in every module.
 */
const SHARED_EXPORTS = SOURCES
  .filter(([name]) => name.startsWith("shared/") || name.startsWith("core/"))
  .flatMap(([name, source]) => [
    ...source.matchAll(/export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g),
    ...source.matchAll(/export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\(|async|function)/g),
  ].map((match) => [match[1], name]));

const EXPORTED_BY = new Map(SHARED_EXPORTS);

function importedNames(source) {
  const names = new Set();
  for (const match of source.matchAll(/import\s*\{([^}]*)\}\s*from/g)) {
    for (const part of match[1].split(",")) {
      const name = part.trim().split(/\s+as\s+/).pop().trim();
      if (name) names.add(name);
    }
  }
  // A namespace or default import brings the name in too.
  for (const match of source.matchAll(/import\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)\s*(?:,|from)/g)) {
    names.add(match[1]);
  }
  return names;
}

function definedLocally(source, name) {
  return new RegExp(`(?:function|const|let|class)\\s+${name}\\b`).test(source);
}

test("every module imports the shared helper it calls", () => {
  assert.ok(EXPORTED_BY.size > 20, "no shared helpers were discovered; the scan is broken");
  const offenders = [];
  for (const [name, source] of SOURCES) {
    if (name.startsWith("shared/") || name.startsWith("core/")) continue;
    const imported = importedNames(source);
    for (const [helper, home] of EXPORTED_BY) {
      if (imported.has(helper) || definedLocally(source, helper)) continue;
      // Called as a bare function, not as a property of something else and not as part
      // of a longer identifier: `x.element(` and `myElement(` are not calls to `element`.
      if (!new RegExp(`(?<![.\\w$])${helper}\\s*\\(`).test(source)) continue;
      offenders.push(`${name} calls ${helper}() from ${home} without importing it`);
    }
  }
  assert.deepEqual(offenders, [],
    "a module that calls an unimported helper throws ReferenceError the moment that branch renders");
});

test("no module builds markup through innerHTML", () => {
  const offenders = SOURCES.filter(([name, source]) => name !== "shared/dom/elements.js" && source.includes(".innerHTML")).map(([name]) => name);
  assert.deepEqual(offenders, [], "build nodes with element()/tableHead() so Backend values can never be parsed as markup");
});

test("every data table carries a caption", () => {
  const offenders = SOURCES.flatMap(([name, source]) => {
    const tables = (source.match(/element\("table"|createElement\("table"\)/g) ?? []).length;
    const captions = (source.match(/tableCaption\(|element\("caption"|createElement\("caption"\)/g) ?? []).length;
    return tables > captions ? [`${name}: ${tables} tables, ${captions} captions`] : [];
  });
  assert.deepEqual(offenders, [], "a table without <caption> is unnavigable by screen reader and unlabelled in print");
});

test("the DOM element helper is defined once and imported everywhere else", () => {
  const definitions = SOURCES.filter(([, source]) => source.includes("function element(tag, className, text)")).map(([name]) => name);
  assert.deepEqual(definitions, ["shared/dom/elements.js"], "element() must not be copied back into feature modules");
});

/**
 * The documented scale lives in shared/styles/tokens.css. Media queries cannot
 * read custom properties, so this test is what keeps the values from drifting.
 */
// Five points, six ranges, and every one of them a value a reader of any other
// project would recognise:
//
//   30rem   480   small phone
//   36rem   576   phone            Bootstrap sm
//   48rem   768   tablet           Bootstrap md, Tailwind md
//   64rem  1024   laptop           Tailwind lg
//   80rem  1280   desktop          Tailwind xl
//
// The .01 partners are gone with the pairs that needed them. The module is
// desktop-first: the widest arrangement is the base and each max-width narrows
// it, so a boundary belongs to the query that names it and there is no gap to
// bridge with a hundredth of a rem.
const RESPONSIVE_SCALE = new Set(["80rem", "64rem", "48rem", "36rem", "30rem"]);

// Deliberately empty. Two exceptions used to live here — 26.5625rem and 23rem —
// and both turned out to be a value chosen at one screen rather than a tier the
// module needed.
const SCALE_EXCEPTIONS = new Map();

function stylesheets(directory = SRC_DIR) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) return stylesheets(full);
    return entry.name.endsWith(".css") ? [[full.slice(SRC_DIR.length + 1).replaceAll("\\", "/"), readFileSync(full, "utf8")]] : [];
  });
}

// Every width in a query, not the first one. A single pattern anchored at
// `@media` stops at the condition it matches, so in
// `@media (min-width: 64rem) and (max-width: 999rem)` it read 64rem, found no
// second `@media`, and let 999rem through unchecked. The prelude is collected
// first, then scanned on its own for as many widths as it holds.
function mediaWidths(source) {
  return [...source.matchAll(/@media[^{]*/g)].flatMap((query) =>
    [...query[0].matchAll(/\((?:max|min)-width:\s*([\d.]+(?:rem|px|em))\)/g)]
      .map((match) => match[1]));
}

test("stylesheets break only at the documented responsive scale", () => {
  const sheets = stylesheets();
  const widths = sheets.flatMap(([, source]) => mediaWidths(source));
  assert.ok(sheets.length >= 10, "expected the feature and shared stylesheets to be discovered");
  assert.ok(widths.length >= 25, "the media-query scan found nothing, so this guard would pass vacuously");

  const offenders = sheets.flatMap(([name, source]) =>
    mediaWidths(source)
      .filter((width) => !RESPONSIVE_SCALE.has(width) && SCALE_EXCEPTIONS.get(width) !== name)
      .map((width) => `${name}: ${width}`));
  assert.deepEqual(
    offenders,
    [],
    "add the width to the scale above and say why, or reuse a tier. A px value is caught here too: "
    + "the scan used to read rem only, which is how 425px and 424.98px once reached the stylesheet unnoticed.",
  );
});
