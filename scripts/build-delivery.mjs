/**
 * The delivery package: one archive, three folders, nothing the host cannot use.
 *
 *   node scripts/build-delivery.mjs [outputDir]      default: ../finance-delivery
 *
 * WHY ONE ARCHIVE AND NOT TWO
 * The browser package and the service are one release: the client calls an API contract
 * the service publishes, and a frontend from Tuesday against a backend from Friday is a
 * bug nobody can see until a field is missing. Two archives invite exactly that drift, so
 * they travel together under one commit and one VERSION.txt.
 *
 * WHY IT IS DERIVED FROM `git ls-files`
 * Everything shippable is tracked. Walking the working tree would sweep in `.env`,
 * `__pycache__`, `.pytest_cache`, a 4 MB backup folder and whatever a probe left behind
 * last week -- and the one that matters is `.env`, which carries two database passwords.
 * Starting from the tracked list means an untracked secret cannot reach the archive even
 * by accident, and the exclusions below only remove things that ARE tracked.
 *
 * WHAT IS EXCLUDED AND WHY -- see EXCLUDE below. Every entry has a reason, because a
 * delivery package that quietly drops a file the host needed is worse than one that is
 * too big.
 */

import { execFileSync } from "node:child_process";
import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const outRoot = resolve(process.argv[2] ?? join(root, "..", "finance-delivery"));

const git = (...args) =>
  execFileSync("git", args, { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });

/**
 * A tracked path is shipped unless a rule here matches it.
 *
 * `test` receives the repository-relative path with forward slashes.
 */
const EXCLUDE = [
  // ---------------------------------------------------------------- never, at any cost
  { why: "carries two database passwords", test: (p) => p === ".env" || p.startsWith(".env.") && p !== ".env.example" },

  // ------------------------------------------------------------------ development only
  { why: "the test suite; the host runs its own CI against its own composition",
    test: (p) => p.startsWith("backend/tests/") || p === "backend/requirements-test.txt" },
  { why: "frontend tests and their DOM stub",
    test: (p) => p.startsWith("frontend/tests/") },
  { why: "the development host's demo fixtures -- seed data must never reach a deployed database",
    test: (p) => p.startsWith("backend/scripts/demo/") },
  { why: "scripts that build and probe a local test database",
    test: (p) => p.startsWith("backend/scripts/test_only/") },
  { why: "a Windows launcher for a developer's own machine",
    test: (p) => p.startsWith("backend/scripts/dev/") },
  { why: "the development host's seed rows and the generators behind them -- 104 KB of demo invoices, prices and progress that must never reach a deployed database",
    test: (p) => /^backend\/devhost\/(seed\.py|seed\.sql|generate_seed_sql\.py|synthetic_progress\.py|inspect\.py)$/.test(p) },
  { why: "operational scripts whose own docstrings say «a local Finance test database»",
    test: (p) => /^backend\/scripts\/ops\/(backup_canonical_test|copy_material_work|import_into_terrace|migrate_canonical_test)\.py$/.test(p) },
  { why: "sample and generated invoices used while developing the reader",
    test: (p) => p.startsWith("backend/extraction/test_data/")
              || p.startsWith("backend/extraction/test_results/")
              || p.startsWith("backend/extraction/samples/") },
  { why: "CI configuration for THIS repository, not the host's",
    test: (p) => p.startsWith(".github/") },
  { why: "the standalone browser preview and the mock adapters behind it -- the host package must not contain demo data at all",
    test: (p) => p === "frontend/index.html" || p.startsWith("frontend/src/adapters/mock/") },
  { why: "the frontend's own tooling and manifests; the package is served as-is, with no build step",
    test: (p) => p.startsWith("frontend/scripts/") || p === "frontend/package.json"
              || p === "frontend/package-lock.json" || p === "frontend/AGENTS.md"
              || p === "frontend/README.md" || p.startsWith("frontend/docs/") },

  { why: "dated internal audits, phase reports and handoffs between us -- decision history, not deployment references; the repository keeps them",
    test: (p) => /^backend\/docs\/(HANDOFF_2026|PHASE[0-9]|SECTION_AUDIT_|FINANCE_EVIDENCE_AUDIT_|ACCEPTANCE_REVIEW_|API_AUDIT_HANDOFF_|DECISION_PACKS_|DEMO_DATA_ALIGNMENT_|DBEAVER_DEMO_GUIDE_|ALEMBIC_DEMO_CHANGELOG_)/.test(p) },

  // ------------------------------------------------------------------- local test data
  // The owner's instruction, and it is the right one: nothing in the development database
  // is real. The host reads its own data from its own tables.
  { why: "schedule files, a database dump and a spreadsheet from local testing -- no data from here is valid on the host",
    test: (p) => p.startsWith("Sources/") || p === "msp_tasks.csv" },

  // ------------------------------------------------------------------ superseded notes
  { why: "working notes and requests to a colleague who no longer works on this; superseded by DEPLOY_HANDOFF_FA.md",
    test: (p) => ["AI_USAGE.md", "ESTIMATE_SOURCE_REQUEST_FA.md", "FINANCE_HANDOFF.md",
                  "FINANCE_INVOICE_AI_HARDENING_HANDOFF.md",
                  "HOST_TEAM_INTEGRATION_REQUEST_FA.txt"].includes(p) },
  { why: "a delivery kit built 2026-09-13 against a branch that no longer exists; it also tells the reader to restore a database dump, which is now wrong",
    test: (p) => p.startsWith("delivery/") },

  // ------------------------------------------------------------------------ parked code
  // Reachable from nothing the host runs. Verified: the frontend package is derived from
  // the import graph and already leaves these out; they are named here so the exclusion
  // is a decision rather than a side effect.
  { why: "parked -- its own comment says the overview does not show it",
    test: (p) => p === "frontend/src/features/finance-home/breakdown-donut.js" },
  { why: "reachable from no page; only a test names it",
    test: (p) => p === "frontend/src/features/finance-home/variance-panel.js"
              || p === "frontend/src/features/prices/prices-csv.js"
              || p === "frontend/src/features/prices/material-label-form.js" },
];

/** The two folders that make up the archive, and where each tracked path lands. */
function destination(path) {
  /* The development host is not shipped as code -- it is a SUBSTITUTE host, and the real
     one is the BAMBO dashboard. But `devhost/app.py::wire()` is the only worked example of
     assembling the fourteen required components, and a team wiring them from prose alone
     is guessing. So it travels under `reference/`, where the name says what it is, with
     the seed files removed by the rule above: without them it does not run, which is the
     honest state for a file nobody should run. */
  if (path.startsWith("backend/devhost/")) {
    return "reference/" + path.slice("backend/".length);
  }
  if (path.startsWith("backend/")) return path;
  if (path.startsWith("frontend/")) return null;          // built separately, see below
  return null;
}

async function main() {
  const tracked = git("ls-files").split("\n").map((line) => line.trim()).filter(Boolean);
  const kept = [];
  const dropped = new Map();
  for (const path of tracked) {
    const rule = EXCLUDE.find((entry) => entry.test(path));
    if (rule) {
      dropped.set(rule.why, (dropped.get(rule.why) ?? 0) + 1);
      continue;
    }
    kept.push(path);
  }

  const commit = git("rev-parse", "--short", "HEAD").trim();
  const full = git("rev-parse", "HEAD").trim();
  const dirty = git("status", "--porcelain").trim();
  if (dirty) {
    console.error("REFUSED: the working tree has uncommitted changes.");
    console.error("A package must name the commit it came from, and this one would not.");
    console.error(dirty);
    process.exit(1);
  }

  const out = join(outRoot, `bambo-finance-${commit}`);
  await rm(outRoot, { recursive: true, force: true });
  await mkdir(out, { recursive: true });

  // ----------------------------------------------------------------- backend + docs
  let copied = 0;
  for (const path of kept) {
    const to = destination(path);
    if (!to) continue;
    const target = join(out, to);
    await mkdir(dirname(target), { recursive: true });
    await cp(join(root, path), target);
    copied += 1;
  }

  await writeFile(join(out, "reference", "README_FIRST_FA.md"),
`# مرجع — اجرا نمی‌شود، خوانده می‌شود

این پوشه **کد قابل اجرا نیست** و بخشی از سرویس نیست.

\`devhost\` میزبان توسعهٔ ماژول است — جایگزینی برای داشبورد BAMBO، که میزبان واقعی است.
اینجا آمده چون \`devhost/app.py::wire()\` تنها نمونهٔ کاملِ سرهم‌کردن آن ۱۴ مؤلفه‌ای است
که \`DEPLOY_HANDOFF_FA.md\` بخش ۳ نام می‌برد. خواندنش سریع‌تر از حدس‌زدن از روی متن است.

**فایل‌های seed عمداً حذف شده‌اند** (\`seed.py\`، \`seed.sql\`، \`generate_seed_sql.py\`،
\`synthetic_progress.py\`، \`inspect.py\`). بدون آن‌ها این کد اجرا نمی‌شود — که وضعیت
درستِ فایلی است که هیچ‌کس نباید اجرایش کند. آن فایل‌ها ۱۰۴ کیلوبایت فاکتور و قیمت و
پیشرفت نمایشی بودند؛ هیچ‌کدام دادهٔ واقعی نیست.

## چه چیزی را از اینجا بخوانید

| فایل | برای چه |
|---|---|
| \`devhost/app.py\` تابع \`wire()\` | چطور ۱۴ مؤلفه روی \`application.state\` نشانده می‌شوند |
| \`devhost/ports.py\` | پیاده‌سازی نمونهٔ پورت‌های میزبان |
| \`devhost/environment.py\` | چطور هر تنظیم خوانده و اعتبارسنجی می‌شود |
| \`devhost/connection.py\` · \`database.py\` | ساخت connection pool سازگار با psycopg |
`, "utf8");
  copied += 1;

  // The root documents, flattened so the first thing in the archive is the way in.
  for (const doc of ["DEPLOY_HANDOFF_FA.md", "README.md", ".env.example"]) {
    if (!kept.includes(doc)) continue;
    await cp(join(root, doc), join(out, doc === "README.md" ? "README_MODULE.md" : doc));
    copied += 1;
  }

  // -------------------------------------------------------------------- frontend
  // Delegated to the frontend's own packager rather than copied by the list above: it
  // walks the import graph and copies exactly what the browser fetches, so a module added
  // next month is included without anyone remembering to add it here.
  execFileSync(process.execPath, ["scripts/build-package.mjs", join(out, "frontend")],
               { cwd: join(root, "frontend"), stdio: "inherit" });

  // ------------------------------------------------------------------- VERSION.txt
  const head = git("log", "-1", "--format=%H%n%cI%n%s").trim().split("\n");
  const migrations = git("ls-files", "backend/alembic/versions")
    .split("\n").filter((line) => line.endsWith(".py"));
  const latest = migrations.map((p) => p.split("/").pop().split("_")[0]).sort().at(-1);
  const frontendFiles = git("ls-files", "frontend/src").split("\n").filter(Boolean).length;

  await writeFile(join(out, "VERSION.txt"),
`BAMBO Finance module — delivery package

commit          ${full}
short           ${commit}
committed       ${head[1]}
subject         ${head[2]}
packaged        ${new Date().toISOString()}

alembic head    ${latest}
migrations      ${migrations.length}

backend files   ${copied}
frontend source ${frontendFiles} modules in the repository (the package carries the reachable subset)

Contents
  DEPLOY_HANDOFF_FA.md   start here — everything the deploy team must do
  backend/               the service, migrations, adapters and API contract
  frontend/              the browser package, served as-is (no build step)
  reference/             devhost, READ ONLY -- the worked example of wiring the host
  backend/docs/          runbooks: deployment, backup/restore, extraction setup
  .env.example           every setting, with its own explanation

NOT in this package, deliberately
  no .env, no credential, no database dump, no schedule file
  no test suite, no demo fixtures, no seed data
  nothing from the development database — the host reads its own
`, "utf8");

  console.log(`\n${copied} backend/doc files + the frontend package -> ${out}`);
  console.log("\nexcluded, by reason:");
  for (const [why, n] of [...dropped].sort((a, b) => b[1] - a[1])) {
    console.log(`  ${String(n).padStart(4)}  ${why}`);
  }
  if (existsSync(join(out, ".env"))) {
    console.error("\nREFUSED: .env reached the package.");
    process.exit(1);
  }
}

await main();
