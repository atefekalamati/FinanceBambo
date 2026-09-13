import { subscribeHostProjectContext } from "../adapters/host/context-adapter.js";
import { resolveRuntimeContext } from "../adapters/host/runtime-context.js";
import { discoverHostContext } from "../adapters/host/host-context-discovery.js";
import { getStandaloneContext } from "../adapters/mock/standalone-context.js";
import { createMockSettingsAdapter } from "../adapters/mock/settings-adapter.js";
import { createMockFinancialItemsAdapter } from "../adapters/mock/financial-items-adapter.js";
import { createMockPricesAdapter } from "../adapters/mock/prices-adapter.js";
import { createMockProgressAdapter } from "../adapters/mock/progress-adapter.js";
import { createMockInvoicesAdapter } from "../adapters/mock/invoices-adapter.js";
import { createMockAttachmentsAdapter } from "../adapters/mock/attachments-adapter.js";
import { SESSION_ENDED_EVENT, createApiClient } from "../core/api/api-client.js";
import { createApiSettingsAdapter } from "../adapters/api/settings-api-adapter.js";
import { createApiFinancialItemsAdapter } from "../adapters/api/financial-items-api-adapter.js";
import { createApiPricesAdapter } from "../adapters/api/prices-api-adapter.js";
import { createApiProgressAdapter } from "../adapters/api/progress-api-adapter.js";
import { createApiInvoicesAdapter } from "../adapters/api/invoices-api-adapter.js";
import { createApiAttachmentsAdapter } from "../adapters/api/attachments-api-adapter.js";
import { createApiReportsAdapter } from "../adapters/api/reports-api-adapter.js";
import { createMockReportsAdapter } from "../adapters/mock/reports-adapter.js";
import { createApiAuditAdapter } from "../adapters/api/audit-api-adapter.js";
import { createMockAuditAdapter } from "../adapters/mock/audit-adapter.js";
import { canAccessRoute, defaultRouteFor } from "../core/auth/permissions.js";
import { ROUTES, readOnlyTwinOf } from "../core/config/routes.js";
import { createHashRouter } from "../core/routing/router.js";
import { createFinanceHomePage } from "../features/finance-home/finance-home-page.js";
import { createOperationsHomePage } from "../features/finance-home/operations-home-page.js";
import { createFinancialItemsPage } from "../features/financial-items/financial-items-page.js";
import { createPricesPage } from "../features/prices/prices-page.js";
import { createProgressPage } from "../features/progress/progress-page.js";
import { createInvoicesPage } from "../features/invoices/invoices-page.js";
import { createInvoiceFilesPage } from "../features/ai-review/invoice-files-page.js";
import { createAiReviewPage } from "../features/ai-review/ai-review-page.js";
import { createSettingsPage } from "../features/settings/settings-page.js";
import { createReportBuilderPage } from "../features/report-builder/report-builder-page.js";
import { createLevelOnePage } from "../features/level-one/level-one-page.js";
import { createAuditPage } from "../features/audit/audit-page.js";
import { DISPLAY_CURRENCY_CHANGED_EVENT } from "../shared/preferences/currency-preference.js";

const root = document.querySelector("#finance-module-root");

function createHostAdapters(context) {
  const client = createApiClient();
  const invoices = createApiInvoicesAdapter(context, client);
  return Object.freeze({
    settings: createApiSettingsAdapter(context, client),
    financialItems: createApiFinancialItemsAdapter(context, client),
    prices: createApiPricesAdapter(context, client),
    progress: createApiProgressAdapter(context, client),
    invoices,
    attachments: createApiAttachmentsAdapter(context, client, invoices),
    reports: createApiReportsAdapter(context, client),
    audit: createApiAuditAdapter(context, client),
  });
}

/**
 * The context, however the host is able to give it.
 *
 * A context set on `window` still wins: it is the stated contract, it needs no
 * requests, and a host that adopts it keeps working unchanged. What follows is
 * for the host as it is today, which sets nothing — the project is in the
 * address bar and everything else is behind endpoints it already serves, so
 * they are read rather than waited for.
 *
 * The standalone preview never reaches the network: it is marked, and a marked
 * page has its own context.
 */
async function resolveContext() {
  const mode = document.body.dataset.financeRuntime;
  let hostContext = window.__BAMBO_FINANCE_CONTEXT__;
  if (!hostContext && mode !== "standalone") {
    hostContext = await discoverHostContext();
    // Published where the contract says to look for it. Nothing here reads it
    // back, but the project-change subscriber does -- and it is the first thing
    // anyone opens a console to check when a page shows the wrong project.
    if (hostContext) window.__BAMBO_FINANCE_CONTEXT__ = hostContext;
  }
  const { runtime, context } = resolveRuntimeContext({
    mode,
    hostContext,
    createStandaloneContext: getStandaloneContext,
  });
  document.body.dataset.financeRuntime = runtime;
  return context;
}

/**
 * The session ended, said once and in place of everything else.
 *
 * The host sets a cookie and the browser sends it; this module holds no token
 * and can refresh nothing, so a 401 is not a page that failed to load but an
 * account that is no longer signed in. Leaving it to the pages would show a
 * retry button behind every failed request, and pressing it would fail the same
 * way -- the reader would learn the module is broken rather than that they need
 * to sign in.
 *
 * The button reloads rather than navigating to a login address. This module is
 * served by the host, so a fresh load goes through whatever the host does for an
 * unauthenticated visitor -- which is the host's decision to make and not one to
 * guess at with a URL written here. Reloading rather than redirecting on its own
 * also leaves an open dialog closed by the reader, not by us.
 */
function renderSessionEnded() {
  const section = document.createElement("section");
  section.className = "state-card state-card--danger";
  const heading = document.createElement("h1");
  heading.textContent = "نشست شما پایان یافته است";
  const message = document.createElement("p");
  message.textContent = "برای ادامه، دوباره وارد سایت اصلی بامبو شوید. اطلاعات مالی تغییری نکرده است.";
  const again = document.createElement("button");
  again.type = "button";
  again.className = "button button--primary";
  again.textContent = "ورود دوباره";
  again.addEventListener("click", () => window.location.reload());
  section.append(heading, message, again);
  return section;
}

function renderDenied(context = null) {
  const section = document.createElement("section");
  section.className = "state-card state-card--danger";
  const heading = document.createElement("h1");
  heading.textContent = "دسترسی ندارید";
  const message = document.createElement("p");
  message.textContent = "مجوز لازم برای مشاهده این صفحه مالی وجود ندارد.";
  section.append(heading, message);
  // A refusal with no way out is a dead end. Whoever arrived here has a home of
  // their own, and it is one click away.
  const home = context ? ROUTES.find((route) => route.path === defaultRouteFor(context)) : null;
  if (home) {
    const link = document.createElement("a");
    link.className = "button button--primary";
    link.href = `#${home.path}`;
    link.textContent = `رفتن به ${home.label}`;
    section.append(link);
  }
  root.replaceChildren(section);
}

function renderRoute(route, context, adapters, routeQuery = new URLSearchParams()) {
  root.replaceChildren();
  if (!canAccessRoute(context, route)) {
    // An account that may not be on امور مالی can still read the table it was
    // reaching for. Sending it to the read-only twin is a better answer than a
    // locked door, and it keeps a link that was written for an administrator
    // working for everyone else.
    const twin = readOnlyTwinOf(route.path);
    if (twin && canAccessRoute(context, twin)) {
      const query = routeQuery.toString();
      window.location.hash = `#${twin.path}${query ? `?${query}` : ""}`;
      return;
    }
    renderDenied(context);
    return;
  }

  // امور مالی opens on the state of the inputs; گزارش مالی opens on the figures
  // those inputs produce. Both read the same adapters, so the report shows an
  // operations change as soon as the service has it.
  if (route.key === "finance-home") root.append(createOperationsHomePage({ progressAdapter: adapters.progress }));
  if (route.key === "report-home") root.append(createFinanceHomePage({ reportsAdapter: adapters.reports, progressAdapter: adapters.progress, pricesAdapter: adapters.prices, financialItemsAdapter: adapters.financialItems }));
  if (route.key === "financial-items" || route.key === "report-items") {
    root.append(createFinancialItemsPage({
      context,
      adapter: adapters.financialItems,
      surface: route.surface,
      focusResourceId: routeQuery.get("resourceId") ?? "",
      focusEstimateLineId: routeQuery.get("estimateLineId") ?? "",
    }));
  }
  if (route.key === "prices" || route.key === "report-prices") {
    root.append(createPricesPage({ context, adapter: adapters.prices, surface: route.surface, focusResourceId: routeQuery.get("resourceId") ?? "" }));
  }
  if (route.key === "progress") root.append(createProgressPage({ context, adapter: adapters.progress }));
  if (route.key === "invoices") root.append(createInvoicesPage({ context, adapter: adapters.invoices }));
  if (route.key === "invoice-files") root.append(createInvoiceFilesPage({ context, adapter: adapters.attachments }));
  if (route.key === "ai-review") root.append(createAiReviewPage({ context, adapter: adapters.attachments }));
  if (route.key === "level-one") {
    root.append(createLevelOnePage({
      context,
      adapters,
      // The phase being opened travels in the address, so it can be linked to
      // and reopened rather than only reached by clicking through the list.
      wbsCode: routeQuery.get("wbs") || null,
    }));
  }
  if (route.key === "report-builder") {
    root.append(createReportBuilderPage({
      context,
      adapters,
      // The chosen reports travel in the address, so a produced document can
      // be reopened and handed on rather than rebuilt from memory.
      selection: (routeQuery.get("sections") ?? "").split(",").filter(Boolean),
      period: { from: routeQuery.get("from") ?? "", to: routeQuery.get("to") ?? "" },
    }));
  }
  if (route.key === "audit") root.append(createAuditPage({ adapter: adapters.audit }));
  if (route.key === "settings" || route.key === "report-settings") {
    root.append(createSettingsPage({
      context,
      adapter: adapters.settings,
      pricesAdapter: adapters.prices,
      surface: route.surface,
    }));
  }
  /* Moving focus is what tells a screen reader the page changed. There was a
     live region above this line saying so in words as well; it asked the host
     for a second element beside the mount, and a missing one -- an empty,
     invisible div nobody would notice -- took the whole module down with a
     TypeError on the first render. The mount carries tabindex="-1" and every
     page opens with its own heading, so the announcement survives the element
     that used to carry it. */
  root.focus();
}

try {
  let context = await resolveContext();
  const allowedMockStates = new Set(["success", "empty", "error"]);
  const requestedMockState = new URLSearchParams(window.location.search).get("settingsState");
  const settingsState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedMockState) ? requestedMockState : "success";
  const requestedItemsState = new URLSearchParams(window.location.search).get("itemsState");
  const itemsState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedItemsState) ? requestedItemsState : "success";
  const requestedPricesState = new URLSearchParams(window.location.search).get("pricesState");
  const pricesState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedPricesState) ? requestedPricesState : "success";
  const requestedProgressState = new URLSearchParams(window.location.search).get("progressState");
  const progressState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedProgressState) ? requestedProgressState : "success";
  const requestedInvoicesState = new URLSearchParams(window.location.search).get("invoicesState");
  const invoicesState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedInvoicesState) ? requestedInvoicesState : "success";
  const requestedFilesState = new URLSearchParams(window.location.search).get("filesState");
  const filesState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedFilesState) ? requestedFilesState : "success";
  const requestedReportsState = new URLSearchParams(window.location.search).get("reportsState");
  const reportsState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedReportsState) ? requestedReportsState : "success";
  const requestedAuditState = new URLSearchParams(window.location.search).get("auditState");
  const auditState = document.body.dataset.financeRuntime === "standalone" && allowedMockStates.has(requestedAuditState) ? requestedAuditState : "success";
  let adapters;
  if (document.body.dataset.financeRuntime === "host") {
    adapters = createHostAdapters(context);
  } else {
    const invoices = createMockInvoicesAdapter(context, { initialState: invoicesState });
    const financialItems = createMockFinancialItemsAdapter(context, { initialState: itemsState });
    adapters = Object.freeze({
      settings: createMockSettingsAdapter(context, { initialState: settingsState }),
      financialItems,
      prices: createMockPricesAdapter(context, { initialState: pricesState, resourceProvider: () => financialItems.getResourceSnapshot() }),
      progress: createMockProgressAdapter(context, { initialState: progressState }),
      invoices,
      attachments: createMockAttachmentsAdapter(context, { initialState: filesState, invoiceAdapter: invoices }),
      reports: createMockReportsAdapter(context, { initialState: reportsState }),
      audit: createMockAuditAdapter(context, { initialState: auditState }),
    });
  }
  let activeRoute = null;
  let activeRouteQuery = new URLSearchParams();
  // Where an account lands with no route of its own depends on which home it
  // may open: a customer must not be dropped at the door of امور مالی.
  const router = createHashRouter({ routes: ROUTES, defaultPath: defaultRouteFor(context), onNavigate: (route, routeQuery) => {
    activeRoute = route;
    activeRouteQuery = routeQuery;
    renderRoute(route, context, adapters, routeQuery);
  } });
  router.start();
  /* Once, and over everything. Whatever was on screen was calculated for an
     account that is no longer signed in, and leaving it there invites the reader
     to act on it. */
  window.addEventListener(SESSION_ENDED_EVENT, () => {
    router.stop();
    root.replaceChildren(renderSessionEnded());
    root.focus();
  }, { once: true });
  window.addEventListener(DISPLAY_CURRENCY_CHANGED_EVENT, () => {
    if (activeRoute) renderRoute(activeRoute, context, adapters, activeRouteQuery);
  });
  if (document.body.dataset.financeRuntime === "host") {
    subscribeHostProjectContext((nextContext) => {
      context = nextContext;
      adapters = createHostAdapters(context);
      if (activeRoute) renderRoute(activeRoute, context, adapters, activeRouteQuery);
    }, (error) => {
      // The re-render above is what a successful switch shows; a failed one
      // changes nothing on screen, so it would leave no trace at all. This is
      // not a message for the reader -- the page they are looking at is still
      // the project they were looking at -- but a switch that failed silently
      // is the kind nobody reports.
      console.warn("[BAMBO Finance] تغییر پروژه انجام نشد.", error);
    }, { rediscover: () => discoverHostContext() });
  }
} catch (error) {
  const section = document.createElement("section");
  section.className = "state-card state-card--danger";
  const heading = document.createElement("h1");
  heading.textContent = "راه‌اندازی ماژول انجام نشد";
  const message = document.createElement("p");
  message.textContent = error.message;
  section.append(heading, message);
  root.replaceChildren(section);
}
