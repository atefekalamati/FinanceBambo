import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ROUTES, SURFACES, homeRouteFor, routesForSurface } from "../../src/core/config/routes.js";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

test("each surface home is dispatched to its own page", () => {
  const bootstrap = read("../../src/app/bootstrap.js");
  assert.match(bootstrap, /route\.key === "finance-home"\) root\.append\(createOperationsHomePage/);
  assert.match(bootstrap, /route\.key === "report-home"\) root\.append\(createFinanceHomePage/);
  // Both settings routes open the same page; the surface decides what it shows.
  assert.match(bootstrap, /route\.key === "settings" \|\| route\.key === "report-settings"/);
  assert.match(bootstrap, /surface: route\.surface/);
});

test("every route the router can reach has a page behind it", () => {
  // A route with no dispatch renders a blank frame with a live-region message
  // saying the page was shown, which is worse than an error.
  const bootstrap = read("../../src/app/bootstrap.js");
  ROUTES.filter((route) => route.enabled).forEach((route) => {
    assert.match(bootstrap, new RegExp(`route\.key === "${route.key}"`), `${route.key} has no page`);
  });
});

test("the operations home shows no money, and the report home shows no operations", () => {
  const operations = read("../../src/features/finance-home/operations-home-page.js");
  // The report surface's destinations moved off the overview onto a page of
  // their own, reached from the bar at the top. Both files together are what
  // that surface offers.
  // The destinations page is withdrawn, so the overview is the whole of what
  // this surface offers.
  const report = read("../../src/features/finance-home/finance-home-page.js");
  // Two screens quoting the same total is how two screens start disagreeing:
  // the figures live on the report, and the operations home links to them.
  assert.doesNotMatch(operations, /summary-card|managerial-combo-chart|bullet-chart/, "the operations home must not draw the figures");
  assert.match(operations, /work-area-card/);
  // Neither home offers the other surface's destinations.
  const linked = (source) => [...source.matchAll(/href: "#\/([a-z-]+)"/g)].map((match) => match[1]);
  const operationsPaths = routesForSurface(SURFACES.OPERATIONS).map((route) => route.path.slice(1));
  const reportPaths = routesForSurface(SURFACES.REPORT).map((route) => route.path.slice(1));
  linked(operations).forEach((path) => assert.ok(operationsPaths.includes(path), `امور مالی links to ${path}, which is not its own`));
  // The same rule in the other direction, and stated over the whole surface
  // rather than over one spelling of an href: امور مالی named the report home
  // in a template literal, which the matcher above never saw.
  routesForSurface(SURFACES.REPORT).forEach((route) => {
    assert.doesNotMatch(operations, new RegExp(`"#${route.path}"`),
      `the operations home links to ${route.path}, which belongs to گزارش مالی`);
  });
  linked(report).forEach((path) => assert.ok(reportPaths.includes(path), `گزارش مالی links to ${path}, which is not its own`));
  // Every destination of a surface, apart from its home, stays reachable. The
  // report overview owns contextual entries for level one, invoices, prices and
  // display settings; its report builder and destinations link are furniture.
  // Only routes with no such entry remain as destination cards.
  const FROM_FURNITURE = new Set([
    "report-builder",
    "work-areas",
    "level-one",
    "invoices",
    "report-prices",
    "report-settings",
    // Reached from the deviation rows through readOnlyTwinOf, which is a
    // redirect rather than a link, so no page names it and none should.
    "report-items",
    // Reached from the فاکتورها card on the board and from the invoice list,
    // both of which are this surface's own furniture.
    "invoice-files",
    "ai-review",
  ]);
  const offered = (surface, home) => routesForSurface(surface)
    .map((route) => route.path.slice(1))
    .filter((path) => path !== home && !FROM_FURNITURE.has(path));
  assert.deepEqual(linked(operations).sort(), offered(SURFACES.OPERATIONS, homeRouteFor(SURFACES.OPERATIONS).path.slice(1)).sort());
  assert.deepEqual(linked(report).sort(), offered(SURFACES.REPORT, homeRouteFor(SURFACES.REPORT).path.slice(1)).sort());
});

/**
 * Three pages left the interface without leaving the codebase: the two report
 * pages, whose every section is an entry in the builder's catalogue now, and the
 * destinations page that listed them. Withdrawn is not deleted -- the route
 * stays declared and the dispatch stays wired, so the pages keep their tests and
 * turning one back on is one word.
 */
/* گزارش وضعیت مالی, گزارش دوره‌ای and بخش‌های گزارش مالی were withdrawn behind
   `enabled: false` and then deleted: every section they drew is a report in the
   builder's catalogue, and a page nobody can open is a page nobody maintains.
   What survives of them is `shared/reports/period-comparison.js`, which the
   builder's two period reports are built on.

   تنظیمات نمایش is the one still in the table. Its page is the settings page
   under another surface, so the route costs nothing to keep and bringing it back
   is one word. */
const WITHDRAWN = Object.freeze(["report-settings"]);
const DELETED = Object.freeze(["reports", "period-report", "work-areas"]);

test("a withdrawn page keeps its dispatch and is offered nowhere", () => {
  const bootstrap = read("../../src/app/bootstrap.js");
  WITHDRAWN.forEach((key) => {
    const route = ROUTES.find((candidate) => candidate.key === key);
    assert.equal(route?.enabled, false, `${key} is still offered to a reader`);
    assert.match(bootstrap, new RegExp(`route\.key === "${key}"`),
      `${key} lost the dispatch that keeps the page alive behind the route`);
  });
});

test("a deleted page leaves no route, no dispatch and no folder", () => {
  // A route with no page behind it resolves to a blank frame, which reads as a
  // broken module rather than a withdrawn feature. The three go together.
  const bootstrap = read("../../src/app/bootstrap.js");
  DELETED.forEach((key) => {
    assert.equal(ROUTES.find((route) => route.key === key), undefined,
      `${key} still has a route with nothing behind it`);
    assert.doesNotMatch(bootstrap, new RegExp(`route\.key === "${key}"`),
      `${key} is still dispatched`);
    assert.doesNotMatch(bootstrap, new RegExp(`features/${key}/`),
      `${key} is still imported`);
  });
});

test("nothing still standing offers a way into a withdrawn page", () => {
  // A link to a route the router refuses is a dead end the reader finds before
  // anyone else does. The sweep covers every source but the withdrawn pages
  // themselves, which are allowed to go on naming each other.
  const withdrawnPaths = WITHDRAWN.map((key) => ROUTES.find((route) => route.key === key).path);
  const withdrawnDirs = ["/reports/", "/period-report/", "/work-areas/"];
  const roots = [fileURLToPath(new URL("../../src/features/", import.meta.url)),
                 fileURLToPath(new URL("../../src/app/", import.meta.url)),
                 fileURLToPath(new URL("../../src/shared/", import.meta.url))];
  const files = roots.flatMap((root) => readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".js"))
    .map((entry) => join(entry.parentPath ?? entry.path, entry.name)));
  files
    .filter((file) => !withdrawnDirs.some((dir) => file.replaceAll("\\", "/").includes(dir)))
    .forEach((file) => {
      const source = readFileSync(file, "utf8");
      withdrawnPaths.forEach((path) => {
        assert.doesNotMatch(source, new RegExp(`"#${path}"`),
          `${file} offers a way into ${path}, which is withdrawn`);
      });
    });
});

test("امور مالی offers no way to record a document", () => {
  // A receipt is not one of the numbers this workspace authors. Invoices are
  // recorded, reviewed and confirmed on گزارش مالی, by every route they take —
  // typed, photographed or spoken — so the workspace names none of them.
  const INVOICE_ROUTES = ["/invoices", "/invoice-files", "/ai-review"];
  INVOICE_ROUTES.forEach((path) => {
    const route = ROUTES.find((candidate) => candidate.path === path);
    assert.equal(route?.surface, SURFACES.REPORT, `${path} is not on گزارش مالی`);
  });
  const operations = read("../../src/features/finance-home/operations-home-page.js");
  INVOICE_ROUTES.forEach((path) => {
    assert.doesNotMatch(operations, new RegExp(`"#${path}"`),
      `the operations home still offers ${path}`);
  });
});

test("the overview keeps a way to everything it is the only entry to", () => {
  const overviewEntries = [
    ["level-one", read("../../src/features/level-one/level-one-section.js"), /href = "#\/level-one"/],
    ["invoices", read("../../src/features/finance-home/invoices-entry.js"), /href = "#\/invoices"/],
    ["report-prices", read("../../src/features/finance-home/prices-summary.js"), /all\.href = "#\/report-prices"/],
  ];
  overviewEntries.forEach(([key, source, pattern]) => {
    assert.match(source, pattern, `${key} has no entry point on the report overview`);
  });
});

test("the reader-only settings view offers nothing that changes a number", () => {
  const source = read("../../src/features/settings/settings-page.js");
  // It returns before the area editor, the conversions and the revision history
  // are ever built, so there is no control there to be found by a keyboard or a
  // screen reader either.
  assert.match(source, /if \(readerOnly\) \{\s*\n\s*const readerGrid/);
  assert.match(source, /readerGrid\.append\(renderCurrencyPolicy\(\), renderAccessSummary\(\)\);/);
  // And it asks the service for nothing, so an unrecorded gross built area or a
  // refused settings read cannot take the currency choice down with it.
  assert.match(source, /if \(readerOnly\) \{[\s\S]{0,400}?REQUEST_STATUS\.SUCCESS, null\)/);
  // Hiding a control is not a permission check, and must not be mistaken for
  // one: the edit permission still gates the form on the operations surface.
  assert.match(source, /mayReviseArea\(data\) \? renderEditor\(data\) : renderRevisionDenied\(data\)/);
});

test("both surfaces read the same adapters, so one shows what the other changed", () => {
  const bootstrap = read("../../src/app/bootstrap.js");
  // One set of adapters is built per context and handed to every route. A page
  // built its own would read a different cache and could show a stale total.
  assert.equal(bootstrap.match(/createHostAdapters\(context\)/g).length, 3, "adapters are built in one place");
  assert.match(bootstrap, /renderRoute\(route, context, adapters, routeQuery\)/);
  assert.doesNotMatch(bootstrap, /createApi\w+Adapter\(context, client\)[\s\S]{0,200}?route\.key/, "no route builds an adapter of its own");
});

test("the deviation rows lead to this surface's own read-only tables", () => {
  const source = read("../../src/features/finance-home/finance-home-page.js");
  // They used to lead into the price and item editors on امور مالی — a link
  // that worked for an administrator and was a way straight past the split for
  // everyone else. The twin routes are read-only whoever opens them.
  // The deviation panel is parked in features/finance-home/variance-panel.js
  // while the owner decides what belongs on the board, so nothing wires it and
  // there is no call site left to read a href out of. The rule it was written
  // for has not gone anywhere and is what these check: neither the overview nor
  // the parked panel names an editor on امور مالی. Its destination is still the
  // caller's argument, so wiring it back cannot reintroduce one without
  // tripping this.
  const parked = read("../../src/features/finance-home/variance-panel.js");
  assert.match(parked, /baseHref/, "the panel still takes its destination from the caller");
  [source, parked].forEach((text) => {
    assert.doesNotMatch(text, /"#\/prices"/);
    assert.doesNotMatch(text, /"#\/financial-items"/);
  });
  // Nothing crosses the split any more. The two surfaces are reached from the
  // host's own sidebar, each behind its own permission, so a link from one into
  // the other would offer a door this page cannot know the reader may open --
  // and would be dead furniture for every reader who may not. The rule is now
  // the whole surface rather than the editors alone: no destination of امور
  // مالی may be named here, whatever it is called.
  routesForSurface(SURFACES.OPERATIONS).forEach((route) => {
    assert.doesNotMatch(source, new RegExp(`"#${route.path}"`),
      `the report home links to ${route.path}, which belongs to امور مالی`);
  });
  // The strip that carried the gear is gone with the rest of the page's
  // furniture, so the overview names no settings route at all -- least of all
  // امور مالی's, which is what this line has always been guarding.
  assert.doesNotMatch(source, /link\.href = "#\/settings"/);
});

test("the read-only mode follows the route, not the account", () => {
  // An administrator reading the report gets the read-only table too. One mode
  // per route is a thing you can reason about; one mode per account is not.
  ["../../src/features/prices/prices-page.js", "../../src/features/financial-items/financial-items-page.js"].forEach((path) => {
    const source = read(path);
    assert.match(source, /const readOnly = surface === SURFACES\.REPORT;/, `${path} does not read its surface`);
    assert.match(source, /const canEdit = !readOnly && capabilitiesFor\(context\)\.writeFinance;/, `${path} lets the permission alone decide`);
    // Both twins use the shared header; the surface passed to the page decides
    // whether its back link returns to operations or to the report dashboard.
    assert.match(source, /createFinancePageHeader\(/, `${path} bypasses the shared report navigation`);
  });
  const bootstrap = read("../../src/app/bootstrap.js");
  assert.match(bootstrap, /route\.key === "prices" \|\| route\.key === "report-prices"/);
  assert.match(bootstrap, /route\.key === "financial-items" \|\| route\.key === "report-items"/);
  assert.equal((bootstrap.match(/surface: route\.surface/g) ?? []).length, 3, "every twinned page must be told which route opened it");
});

test("a closed door redirects to the readable twin instead of denying", () => {
  const bootstrap = read("../../src/app/bootstrap.js");
  assert.match(bootstrap, /const twin = readOnlyTwinOf\(route\.path\)/);
  assert.match(bootstrap, /if \(twin && canAccessRoute\(context, twin\)\)/);
  // The deep link's own query has to survive the redirect, or the row the
  // reader clicked is not the row they arrive at.
  assert.match(bootstrap, /window\.location\.hash = `#\$\{twin\.path\}\$\{query \? `\?\$\{query\}` : ""\}`/);
  // And the landing route is resolved from the account, not fixed.
  assert.match(bootstrap, /defaultPath: defaultRouteFor\(context\)/);
});
