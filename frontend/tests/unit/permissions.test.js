import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { canAccessRoute, canAccessSurface, defaultRouteFor, hasPermission } from "../../src/core/auth/permissions.js";
import { ROUTES, SURFACES, homeRouteFor, readOnlyTwinOf, routesForSurface, surfaceOfPath } from "../../src/core/config/routes.js";

const context = { permissionCodes: ["finance.view"] };

test("checks existing coarse permission codes", () => {
  assert.equal(hasPermission(context, "finance.view"), true);
  assert.equal(hasPermission(context, "finance.edit"), false);
});

test("allows routes without a permission and rejects unavailable permissions", () => {
  assert.equal(canAccessRoute(context, { permission: null }), true);
  assert.equal(canAccessRoute(context, { permission: "finance.edit" }), false);
});

/**
 * Every route opens a page whose first request is a GET, and the Backend gates
 * those on reading, not writing: finance.view everywhere except the reporting
 * routes, which ask for finance_report.view. A route demanding finance.edit
 * would hide a page the API would have served — settings did exactly that,
 * because PATCH /settings needs the edit permission and the route copied it.
 * Write permissions belong on the buttons inside a page, never on its door.
 *
 * That holds for finance.manage_invoice too, and it is worth saying why, since
 * the code names a capability rather than a single action. An account that may
 * read the register may open every invoice page and see every document on it,
 * including the decisions each one is waiting on. The grant decides whether the
 * controls in those pages work, not whether the pages open — so a reader is
 * never shown a register with the deciding half of it silently missing.
 */
const ROUTE_PERMISSIONS = Object.freeze({
  "finance-home": "finance.view",
  "financial-items": "finance.view",
  prices: "finance.view",
  progress: "finance.view",
  invoices: "finance.view",
  "invoice-files": "finance.view",
  "ai-review": "finance.view",
  audit: "finance.view",
  settings: "finance.view",
  "report-home": "finance.view",
  "report-prices": "finance.view",
  // The builder composes reports, so it asks for the reporting permission its
  // own contents already ask for.
  "report-builder": "finance_report.view",
  "report-items": "finance.view",
  // Cost rolled up the breakdown structure, from GET /reports/live/by-wbs —
  // a report of what the figures turned out to be, so it asks for the report
  // reading permission like the other two report pages.
  "level-one": "finance_report.view",
  // The destinations page is the list of links that used to close the overview.
  // It reads nothing of its own, so it asks for the same reading permission the
  // pages it points at do.
  // The reader-only settings view shows a currency choice held in this browser
  // and a read-back of the permissions the host granted. Its one request is
  // GET /settings, so it asks for reading like every other door.
  "report-settings": "finance.view",
});

test("every route asks for the permission its Backend GET asks for", () => {
  assert.deepEqual(
    Object.fromEntries(ROUTES.map((route) => [route.key, route.permission])),
    ROUTE_PERMISSIONS,
  );
});

test("no route is gated on a write permission", () => {
  const writeGated = ROUTES.filter((route) => /\.(edit|issue|export)$/.test(route.permission ?? ""));
  assert.deepEqual(writeGated.map((route) => route.key), [], "a write permission gates a control, not a page");
});

/**
 * The host's administrator grants these codes freely and this module never
 * learns which role received which, so what has to hold is that every sensible
 * combination produces a coherent module — not that some particular role does.
 * Each entry below is one such combination, written as the codes it holds.
 */
const ACCOUNTS = Object.freeze({
  // Reads what the project cost, records nothing.
  reader: ["finance.view", "finance_report.view", "finance_report.export"],
  // Authors the plan's numbers, and has no business on the customer's side.
  author: ["finance.view", "finance.edit"],
  // Records and confirms documents, and never enters the workspace. Holds no
  // reporting code at all, which is the case a single surface code would break.
  recorder: ["finance.view", "finance.manage_invoice"],
  everything: ["finance.view", "finance.edit", "finance_report.view",
               "finance_report.export", "finance.manage_invoice"],
});

test("each surface opens for any one of its own codes", () => {
  const doors = {
    reader: { [SURFACES.OPERATIONS]: false, [SURFACES.REPORT]: true },
    author: { [SURFACES.OPERATIONS]: true, [SURFACES.REPORT]: false },
    recorder: { [SURFACES.OPERATIONS]: false, [SURFACES.REPORT]: true },
    everything: { [SURFACES.OPERATIONS]: true, [SURFACES.REPORT]: true },
  };
  Object.entries(doors).forEach(([name, expected]) => {
    Object.entries(expected).forEach(([surface, open]) => {
      assert.equal(canAccessSurface({ permissionCodes: ACCOUNTS[name] }, surface), open,
        `${surface} is ${open ? "closed to" : "open to"} ${name}`);
    });
  });
});

test("recording a document gates the controls, never the register", () => {
  // Reading the register and recording into it are separate grants, and the
  // separation is drawn inside the page. Anyone who may read the project's
  // figures may open all three invoice pages and see every document on them;
  // whether the controls work is capabilitiesFor().manageInvoice, checked by
  // each page against its own buttons.
  const invoicePages = ["invoices", "invoice-files", "ai-review"]
    .map((key) => ROUTES.find((route) => route.key === key));
  invoicePages.forEach((route) => {
    assert.equal(route.permission, "finance.view", `${route.key} gates its door on a write grant`);
    ["reader", "author", "recorder", "everything"].forEach((name) => {
      const holdsReportDoor = ACCOUNTS[name].some((code) =>
        ["finance_report.view", "finance.manage_invoice"].includes(code));
      assert.equal(canAccessRoute({ permissionCodes: ACCOUNTS[name] }, route), holdsReportDoor,
        `${route.key} answers ${name} wrongly`);
    });
  });
  // And the pages that hold those controls all ask the one capability, so a
  // grant added to one is not forgotten in another.
  ["../../src/features/invoices/invoices-page.js",
   "../../src/features/ai-review/ai-review-page.js",
   "../../src/features/ai-review/invoice-files-page.js"].forEach((path) => {
    const source = readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
    assert.match(source, /capabilitiesFor\(context\)\.manageInvoice/, `${path} does not ask for the invoice grant`);
    assert.match(source, /createPermissionNotice\(/, `${path} switches a control off without saying why`);
  });
});

test("امور مالی is closed to an account that cannot author anything", () => {
  // The route permission is still the reading one its GET needs. What keeps a
  // customer out of the workspace is the surface requirement, checked once
  // rather than control by control on every page.
  const reader = { permissionCodes: ACCOUNTS.reader };
  const admin = { permissionCodes: ACCOUNTS.everything };
  routesForSurface(SURFACES.OPERATIONS).forEach((route) => {
    assert.equal(canAccessRoute(reader, route), false, `${route.key} is open to an account that cannot write`);
    assert.equal(canAccessRoute(admin, route), true, `${route.key} is closed to an administrator`);
  });
  // Nothing on گزارش مالی is closed to a reader: the register opens for anyone
  // who may read the figures, and what they may do inside it is decided there.
  routesForSurface(SURFACES.REPORT).forEach((route) => {
    assert.equal(canAccessRoute(reader, route), true, `${route.key} is closed to a reader`);
    assert.equal(canAccessRoute(admin, route), true, `${route.key} is closed to an administrator`);
  });
});

test("a reader reaching for an operations table is sent to the read-only one", () => {
  const reader = { permissionCodes: ["finance.view", "finance_report.view"] };
  [["/prices", "/report-prices"], ["/financial-items", "/report-items"]].forEach(([from, to]) => {
    const twin = readOnlyTwinOf(from);
    assert.equal(twin?.path, to, `${from} has no read-only twin`);
    assert.equal(canAccessRoute(reader, twin), true, `${to} is closed to the account the redirect is for`);
    assert.equal(surfaceOfPath(to), SURFACES.REPORT);
  });
  // Pages with nothing to read for a customer have no twin and stay closed.
  ["/progress", "/settings", "/audit", "/invoice-files", "/ai-review", "/finance"].forEach((path) => {
    assert.equal(readOnlyTwinOf(path), null, `${path} should not have a read-only twin`);
  });
});

test("an account lands on a home it is allowed to open", () => {
  const reader = { permissionCodes: ["finance.view", "finance_report.view"] };
  const admin = { permissionCodes: ["finance.view", "finance.edit"] };
  assert.equal(defaultRouteFor(admin), homeRouteFor(SURFACES.OPERATIONS).path);
  assert.equal(defaultRouteFor(reader), homeRouteFor(SURFACES.REPORT).path);
  // Even with nothing at all, the module must resolve to some path rather than
  // hand the router undefined.
  assert.equal(typeof defaultRouteFor(null), "string");
});

test("each route belongs to exactly one surface, and each surface has one home", () => {
  const surfaces = new Set([SURFACES.OPERATIONS, SURFACES.REPORT]);
  ROUTES.forEach((route) => {
    assert.ok(surfaces.has(route.surface), `${route.key} belongs to no surface`);
  });
  [...surfaces].forEach((surface) => {
    const homes = routesForSurface(surface).filter((route) => route.home);
    assert.equal(homes.length, 1, `${surface} must have exactly one home`);
    assert.equal(homeRouteFor(surface), homes[0]);
  });
  // Two routes sharing a path would make surfaceOfPath answer at random.
  const paths = ROUTES.map((route) => route.path);
  assert.equal(new Set(paths).size, paths.length, "two routes share a path");
});

test("the split moved pages between surfaces without dropping any", () => {
  // Whatever the surfaces are, together they must still be the whole module:
  // a page that belongs to neither is a page nobody can reach. A withdrawn
  // route is not such a page -- it is declared, dispatched and deliberately not
  // offered, so it is measured against the same enabled filter both sides use.
  const covered = [...routesForSurface(SURFACES.OPERATIONS), ...routesForSurface(SURFACES.REPORT)];
  assert.deepEqual(
    covered.map((route) => route.key).sort(),
    ROUTES.filter((route) => route.enabled).map((route) => route.key).sort(),
  );
  // What the customer reads, and what the operator authors.
  assert.deepEqual(routesForSurface(SURFACES.REPORT).map((route) => route.key), [
    "report-home",
    "level-one",
    "invoices",
    "invoice-files",
    "ai-review",
    "report-prices",
    "report-items",
    "report-builder",
  ]);
  assert.deepEqual(routesForSurface(SURFACES.OPERATIONS).map((route) => route.key), [
    "finance-home",
    "financial-items",
    "prices",
    "progress",
    "audit",
    "settings",
  ]);
});

test("each home belongs to the surface it opens", () => {
  assert.equal(surfaceOfPath(homeRouteFor(SURFACES.OPERATIONS).path), SURFACES.OPERATIONS);
  assert.equal(surfaceOfPath(homeRouteFor(SURFACES.REPORT).path), SURFACES.REPORT);
  assert.equal(surfaceOfPath("/nowhere"), null);
});
