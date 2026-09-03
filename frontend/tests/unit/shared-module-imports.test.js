import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SHARED_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "src", "shared");

/**
 * A shared module has to carry its own dependencies.
 *
 * This exists because of a real break: `createBreakdownChart` was lifted out of
 * the finance overview into `shared/components` so the report page could draw
 * the same comparison, and the helper it calls to render an amount stayed
 * behind. Nothing failed until the report page was opened in a browser, where
 * it threw and the section rendered empty — a page that had passed every test
 * and every layout run.
 *
 * The check is deliberately narrow: a bare call, not a method call, to a name
 * the file neither imports nor defines. That is the shape a half-finished
 * extraction leaves and it is cheap to detect.
 */

function modules(directory = SHARED_DIR) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = join(directory, entry.name);
    if (entry.isDirectory()) return modules(full);
    if (!entry.name.endsWith(".js")) return [];
    return [[full.slice(SHARED_DIR.length + 1).replaceAll("\\", "/"), readFileSync(full, "utf8")]];
  });
}

/** Comments and string bodies are not code; a name inside one proves nothing. */
function stripLiterals(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1 ")
    .replace(/`(?:\\.|\$\{[^}]*\}|[^`\\])*`/g, "``")
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, "''");
}

/* Anything the language itself provides, plus the browser surface these
   modules legitimately reach for. */
const AMBIENT = new Set([
  "if", "for", "while", "switch", "catch", "return", "typeof", "function", "await",
  "requestAnimationFrame", "cancelAnimationFrame", "setTimeout", "clearTimeout", "fetch",
  "structuredClone", "queueMicrotask", "isNaN", "parseInt", "parseFloat", "encodeURIComponent",
  "decodeURIComponent", "getComputedStyle",
]);

test("every shared module imports or defines what it calls", () => {
  const files = modules();
  assert.ok(files.length >= 15, "expected the shared layer to be discovered");

  const offenders = files.flatMap(([name, raw]) => {
    const source = stripLiterals(raw);
    const imported = new Set(
      [...source.matchAll(/import\s*\{([^}]*)\}/g)]
        .flatMap((match) => match[1].split(","))
        .map((part) => part.trim().split(/\s+as\s+/).pop())
        .filter(Boolean),
    );
    [...source.matchAll(/import\s+(\w+)\s+from/g)].forEach((m) => imported.add(m[1]));

    // A bare call: not a method on something else.
    const calls = [...source.matchAll(/(?<![.\w$])([a-z][A-Za-z0-9_$]*)\s*\(/g)].map((m) => m[1]);

    return [...new Set(calls)].filter((identifier) => {
      if (imported.has(identifier) || AMBIENT.has(identifier)) return false;
      // Its own declaration reads as a call to the pattern above.
      if (new RegExp(String.raw`function\s+${identifier}\b`).test(source)) return false;
      // Shorthand method on an object literal — `setData(next) { … }` — is a
      // definition, and the call regex cannot tell it from a call.
      if (new RegExp(String.raw`(?<![.\w$])${identifier}\s*\([^()]*\)\s*\{`).test(source)) return false;
      // Anything defined, destructured or taken as a parameter is mentioned
      // somewhere other than at a call site. A name that appears only where it
      // is called appears nowhere it could have come from.
      const total = (source.match(new RegExp(String.raw`\b${identifier}\b`, "g")) ?? []).length;
      const called = calls.filter((c) => c === identifier).length;
      return total <= called;
    }).map((identifier) => `${name}: ${identifier}()`);
  });

  assert.deepEqual(
    offenders,
    [],
    "a shared module calls something it neither imports nor defines — the browser is the only place this would have failed",
  );
});
