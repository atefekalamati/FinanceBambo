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
  assert.doesNotMatch(operations, /summary-card|managerial-combo-chart|breakdown-chart/, "the operations home must not draw the figures");
  assert.match(operations, /work-area-card/);
  // Neither home offers the other surface's destinations.
  const linked = (source) => [...source.matchAll(/href: "#\/([a-z-]+)"/g)].map((match) => match[1]);
  const operationsPaths = routesForSurface(SURFACES.OPERATIONS).map((route) => route.path.slice(1));
  const reportPaths = routesForSurface(SURFACES.REPORT).map((route) => route.path.slice(1));
  linked(operations).forEach((path) => assert.ok(operationsPaths.includes(path), `امور مالی links to ${path}, which is not its own`));
  linked(report).forEach((path) => assert.ok(reportPaths.includes(path), `گزارش مالی links to ${path}, which is not its own`));
  // Every destination of a surface, apart from its home, is offered by it.
  assert.deepEqual(
    linked(operations).sort(),
    operationsPaths.filter((path) => path !== homeRouteFor(SURFACES.OPERATIONS).path.slice(1)).sort(),
  );
  assert.deepEqual(
    linked(report).sort(),
    reportPaths.filter((path) => path !== homeRouteFor(SURFACES.REPORT).path.slice(1)).sort(),
  );
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

test("the report home leads into امور مالی only for an account that can act there", () => {
  const source = read("../../src/features/finance-home/finance-home-page.js");
  // The three shortcuts that cross the split: the two deviation drill-downs and
  // the empty state's way to the progress versions. Each is behind canOperate,
  // which is the edit permission — the accounts that had the shortcut before
  // still have it, and a reader is not sent to a page they cannot use.
  assert.match(source, /const canOperate = capabilitiesFor\(context\)\.writeFinance/);
  assert.match(source, /canOperate \? "#\/prices" : null/);
  assert.match(source, /canOperate \? "#\/financial-items" : null/);
  assert.match(source, /if \(canOperate\) \{[\s\S]{0,220}?"#\/progress"/);
  // The gear on the report opens the settings this surface owns, not the ones
  // that change what the figures come out as.
  assert.match(source, /finance-project-settings-link[\s\S]{0,320}?link\.href = "#\/report-settings"/);
  assert.doesNotMatch(source, /link\.href = "#\/settings"/);
  // A row that goes nowhere must not be an anchor, must not carry the chevron
  // that promises somewhere to go, and must not light up on hover.
  assert.match(source, /document\.createElement\(baseHref \? "a" : "div"\)/);
  assert.match(source, /if \(baseHref\) indicator\.textContent = "‹"/);
  assert.match(read("../../src/features/finance-home/finance-home.css"), /a\.finance-variance-card__link:hover/);
});
