import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  linked(report).forEach((path) => assert.ok(reportPaths.includes(path), `گزارش مالی links to ${path}, which is not its own`));
  // Every destination of a surface, apart from its home, is offered by it. The
  // report builder is the exception: it is not somewhere to go from a card, it
  // is what its own section on the page produces.
  const offered = (surface, home) => routesForSurface(surface)
    .map((route) => route.path.slice(1))
    .filter((path) => path !== home && path !== "report-builder");
  assert.deepEqual(linked(operations).sort(), offered(SURFACES.OPERATIONS, homeRouteFor(SURFACES.OPERATIONS).path.slice(1)).sort());
  assert.deepEqual(linked(report).sort(), offered(SURFACES.REPORT, homeRouteFor(SURFACES.REPORT).path.slice(1)).sort());
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
  assert.match(source, /formatCompactMoneyFromIrr, "#\/report-prices"\)/);
  assert.match(source, /formatDisplayNumber, "#\/report-items"\)/);
  assert.doesNotMatch(source, /"#\/prices"/);
  assert.doesNotMatch(source, /"#\/financial-items"/);
  // The one shortcut left that crosses the split is behind the surface check
  // itself, not a permission this page names for itself.
  assert.match(source, /const canOperate = canAccessSurface\(context, SURFACES\.OPERATIONS\)/);
  assert.match(source, /if \(canOperate\) \{[\s\S]{0,220}?"#\/progress"/);
  // The gear opens the settings this surface owns.
  assert.match(source, /finance-project-settings-link[\s\S]{0,320}?link\.href = "#\/report-settings"/);
  assert.doesNotMatch(source, /link\.href = "#\/settings"/);
});

test("the read-only mode follows the route, not the account", () => {
  // An administrator reading the report gets the read-only table too. One mode
  // per route is a thing you can reason about; one mode per account is not.
  ["../../src/features/prices/prices-page.js", "../../src/features/financial-items/financial-items-page.js"].forEach((path) => {
    const source = read(path);
    assert.match(source, /const readOnly = surface === SURFACES\.REPORT;/, `${path} does not read its surface`);
    assert.match(source, /const canEdit = !readOnly && capabilitiesFor\(context\)\.writeFinance;/, `${path} lets the permission alone decide`);
    // The back link and the framing follow the same surface, so a reader is not
    // told they came from a workspace they were never on.
    assert.match(source, /homeRouteFor\(surface\)\?\.path/, `${path} sends the reader back to the wrong surface`);
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
