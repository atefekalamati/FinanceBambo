/**
 * The deployable package, derived rather than listed.
 *
 * A hand-written manifest goes stale the first time someone adds a module and
 * does not think of it, and the failure is a blank page on the host's server
 * rather than a red test here. So this walks the same graph the browser walks --
 * every `import` reachable from the entry point, every `@import` reachable from
 * the stylesheet, and every asset those two name -- and copies exactly that.
 *
 *   node scripts/build-package.mjs [outputDir]     default: ../finance-package
 *
 * It refuses to write anything if a file the graph needs is missing, because a
 * package that is quietly short one module is worse than no package at all.
 *
 * WHAT IS DELIBERATELY LEFT OUT
 * tests, docs, scripts, package.json and the READMEs: none is fetched by the
 * browser, and docs/ carries internal decision records that have no business on
 * a public server. index.html goes in as a preview and is not what the host
 * mounts -- host.html is.
 *
 * WHAT IS NO LONGER IN IT
 * src/adapters/mock, and index.html which is the only page that turns it on. The entry
 * point now reaches the preview adapters through a dynamic import inside the standalone
 * branch, so they are no longer in the static graph -- and the host is served a package
 * that does not contain demo data at all, rather than one that merely never runs it.
 *
 * Pass --with-preview to get the old output: index.html plus everything the dynamic
 * imports reach. That is a development artefact and the file list says so.
 */

import { readFile, mkdir, copyFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const outDir = resolve(process.argv[2] ?? join(root, "..", "finance-package"));

const ENTRY_JS = "src/app/bootstrap.js";
const ENTRY_CSS = "src/shared/styles/index.css";
/* The host mounts host.html. index.html is the standalone preview and is the only page
   that sets `data-finance-runtime="standalone"`, so it ships only when asked for. */
const WITH_PREVIEW = process.argv.includes("--with-preview");
const HTML = WITH_PREVIEW ? ["host.html", "index.html"] : ["host.html"];

/* `from "x"` and a bare `import "x"`, but NOT `import("x")`: a dynamic import is how the
   preview's adapters are reached, and following it would put them back in the package the
   host is served. With --with-preview the paren is allowed again. */
const IMPORT = WITH_PREVIEW
  ? /(?:from|import)\s*\(?\s*["']([^"']+)["']/g
  : /(?:from\s*|import\s+)["']([^"']+)["']/g;
const CSS_IMPORT = /@import\s+url\(\s*["']?([^"')]+)/g;
const HTML_REF = /(?:href|src)="([^"]+)"/g;
const CSS_URL = /url\(\s*["']?([^"')]+?)["']?\s*\)/g;

const read = (rel) => readFile(join(root, rel), "utf8");
const isRelative = (spec) => spec.startsWith(".");
const normalize = (from, spec) => relative(root, resolve(join(root, dirname(from)), spec)).split("\\").join("/");

async function closure(entry, pattern, onlyRelative) {
  const seen = new Set();
  const stack = [entry];
  while (stack.length) {
    const file = stack.pop();
    if (seen.has(file) || !existsSync(join(root, file))) continue;
    seen.add(file);
    const text = await read(file);
    for (const [, spec] of text.matchAll(pattern)) {
      if (onlyRelative && !isRelative(spec)) continue;
      stack.push(normalize(file, spec));
    }
  }
  return seen;
}

const js = await closure(ENTRY_JS, IMPORT, true);
const css = await closure(ENTRY_CSS, CSS_IMPORT, false);

/* Fonts and the favicon: named by the HTML and the stylesheets, never imported,
   so nothing above would have found them. */
const assets = new Set();
for (const file of [...js, ...css, ...HTML]) {
  if (!existsSync(join(root, file))) continue;
  const text = await read(file);
  const base = file.endsWith(".html") ? "." : dirname(file);
  for (const pattern of [HTML_REF, CSS_URL]) {
    for (const [, ref] of text.matchAll(pattern)) {
      if (/^(#|https?:|data:)/.test(ref)) continue;
      const target = relative(root, resolve(join(root, base), ref)).split("\\").join("/");
      if (/\.(js|css)$/.test(target)) continue;
      if (existsSync(join(root, target))) assets.add(target);
    }
  }
}

const files = [...new Set([...js, ...css, ...assets, ...HTML])].sort();
const absent = files.filter((f) => !existsSync(join(root, f)));
if (absent.length) {
  console.error("the graph names files that are not here:\n  " + absent.join("\n  "));
  process.exit(1);
}

await rm(outDir, { recursive: true, force: true });
for (const file of files) {
  const target = join(outDir, file);
  await mkdir(dirname(target), { recursive: true });
  await copyFile(join(root, file), target);
}
await writeFile(join(outDir, "MANIFEST.txt"),
  `# ${files.length} files, derived from the module graph on ${new Date().toISOString().slice(0, 10)}\n`
  + `# entry: ${ENTRY_JS} and ${ENTRY_CSS}\n`
  + (WITH_PREVIEW
      ? `# DEVELOPMENT BUILD: includes index.html and the standalone preview's adapters\n\n`
      : `# the host mounts host.html; the standalone preview is not in this package\n\n`)
  + files.join("\n") + "\n", "utf8");

const counts = files.reduce((tally, f) => {
  const kind = f.endsWith(".js") ? "js" : f.endsWith(".css") ? "css" : f.endsWith(".html") ? "html" : "asset";
  return { ...tally, [kind]: (tally[kind] ?? 0) + 1 };
}, {});
console.log(`${files.length} files -> ${outDir}`);
console.log(Object.entries(counts).map(([k, v]) => `  ${v} ${k}`).join("\n"));
