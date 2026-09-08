import { subscribeHostProjectContext } from "../adapters/host/context-adapter.js";
import { resolveRuntimeContext } from "../adapters/host/runtime-context.js";
import { getStandaloneContext } from "../adapters/mock/standalone-context.js";
import { createMockSettingsAdapter } from "../adapters/mock/settings-adapter.js";
import { createMockFinancialItemsAdapter } from "../adapters/mock/financial-items-adapter.js";
import { createMockPricesAdapter } from "../adapters/mock/prices-adapter.js";
import { createMockProgressAdapter } from "../adapters/mock/progress-adapter.js";
import { createMockInvoicesAdapter } from "../adapters/mock/invoices-adapter.js";
import { createMockAttachmentsAdapter } from "../adapters/mock/attachments-adapter.js";
import { createApiClient } from "../core/api/api-client.js";
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
import { createReportsPage } from "../features/reports/reports-page.js";
import { createPeriodReportPage } from "../features/period-report/period-report-page.js";
import { createReportBuilderPage } from "../features/report-builder/report-builder-page.js";
import { createLevelOnePage } from "../features/level-one/level-one-page.js";
import { createWorkAreasPage } from "../features/work-areas/work-areas-page.js";
import { createAuditPage } from "../features/audit/audit-page.js";
import { DISPLAY_CURRENCY_CHANGED_EVENT } from "../shared/preferences/currency-preference.js";

const root = document.querySelector("#finance-module-root");
const liveRegion = document.querySelector("#finance-live-region");

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

function resolveContext() {
  const { runtime, context } = resolveRuntimeContext({
    mode: document.body.dataset.financeRuntime,
    hostContext: window.__BAMBO_FINANCE_CONTEXT__,
    createStandaloneContext: getStandaloneContext,
  });
  document.body.dataset.financeRuntime = runtime;
  return context;
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
  if (route.key === "report-home") root.append(createFinanceHomePage({ context, reportsAdapter: adapters.reports, progressAdapter: adapters.progress, pricesAdapter: adapters.prices }));
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
  if (route.key === "reports") root.append(createReportsPage({ context, adapter: adapters.reports }));
  if (route.key === "period-report") {
    root.append(createPeriodReportPage({
      context,
      reportsAdapter: adapters.reports,
      auditAdapter: adapters.audit,
      invoicesAdapter: adapters.invoices,
      progressAdapter: adapters.progress,
    }));
  }
  if (route.key === "work-areas") root.append(createWorkAreasPage());
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
  liveRegion.textContent = `صفحه ${route.label} نمایش داده شد.`;
  root.focus();
}

try {
  let context = resolveContext();
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
  createHashRouter({ routes: ROUTES, defaultPath: defaultRouteFor(context), onNavigate: (route, routeQuery) => {
    activeRoute = route;
    activeRouteQuery = routeQuery;
    renderRoute(route, context, adapters, routeQuery);
  } }).start();
  window.addEventListener(DISPLAY_CURRENCY_CHANGED_EVENT, () => {
    if (activeRoute) renderRoute(activeRoute, context, adapters, activeRouteQuery);
  });
  if (document.body.dataset.financeRuntime === "host") {
    subscribeHostProjectContext((nextContext) => {
      context = nextContext;
      adapters = createHostAdapters(context);
      if (activeRoute) renderRoute(activeRoute, context, adapters, activeRouteQuery);
      liveRegion.textContent = `اطلاعات مالی پروژه ${context.projectName || context.projectId} بارگذاری شد.`;
    }, (error) => {
      liveRegion.textContent = `تغییر پروژه انجام نشد: ${error.message}`;
    });
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
