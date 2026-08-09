import { getHostContext } from "../adapters/host/context-adapter.js";
import { getStandaloneContext } from "../adapters/mock/standalone-context.js";
import { createMockSettingsAdapter } from "../adapters/mock/settings-adapter.js";
import { createMockFinancialItemsAdapter } from "../adapters/mock/financial-items-adapter.js";
import { createMockPricesAdapter } from "../adapters/mock/prices-adapter.js";
import { createMockProgressAdapter } from "../adapters/mock/progress-adapter.js";
import { createMockInvoicesAdapter } from "../adapters/mock/invoices-adapter.js";
import { createMockAttachmentsAdapter } from "../adapters/mock/attachments-adapter.js";
import { canAccessRoute } from "../core/auth/permissions.js";
import { DEFAULT_ROUTE, ROUTES } from "../core/config/routes.js";
import { createHashRouter } from "../core/routing/router.js";
import { createFinanceHomePage } from "../features/finance-home/finance-home-page.js";
import { createFinancialItemsPage } from "../features/financial-items/financial-items-page.js";
import { createPricesPage } from "../features/prices/prices-page.js";
import { createProgressPage } from "../features/progress/progress-page.js";
import { createInvoicesPage } from "../features/invoices/invoices-page.js";
import { createInvoiceFilesPage } from "../features/ai-review/invoice-files-page.js";
import { createSettingsPage } from "../features/settings/settings-page.js";
import { formatArea } from "../shared/formatters/display.js";

const root = document.querySelector("#finance-module-root");
const contextSlot = document.querySelector("#project-context-slot");
const liveRegion = document.querySelector("#finance-live-region");

function resolveContext() {
  const hostContext = getHostContext();
  document.body.dataset.financeRuntime = hostContext ? "host" : "standalone";
  return hostContext ?? getStandaloneContext();
}

function renderContext(context) {
  const project = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = context.projectName || context.projectId;
  const meta = document.createElement("small");
  meta.textContent = `${context.projectCode || context.projectId} · ${formatArea(context.grossBuiltArea)}`;
  project.append(title, document.createElement("br"), meta);
  const organization = document.createElement("span");
  organization.textContent = context.organizationName || "سازمان BAMBO";
  contextSlot.replaceChildren(project, organization);
}

function renderDenied() {
  const section = document.createElement("section");
  section.className = "state-card state-card--danger";
  const heading = document.createElement("h1");
  heading.textContent = "دسترسی ندارید";
  const message = document.createElement("p");
  message.textContent = "مجوز لازم برای مشاهده این صفحه مالی وجود ندارد.";
  section.append(heading, message);
  root.replaceChildren(section);
}

function renderRoute(route, context, adapters) {
  root.replaceChildren();
  if (!canAccessRoute(context, route)) {
    renderDenied();
    return;
  }

  if (route.key === "finance-home") root.append(createFinanceHomePage());
  if (route.key === "financial-items") {
    root.append(createFinancialItemsPage({ context, adapter: adapters.financialItems }));
  }
  if (route.key === "prices") root.append(createPricesPage({ context, adapter: adapters.prices }));
  if (route.key === "progress") root.append(createProgressPage({ context, adapter: adapters.progress }));
  if (route.key === "invoices") root.append(createInvoicesPage({ context, adapter: adapters.invoices }));
  if (route.key === "invoice-files") root.append(createInvoiceFilesPage({ context, adapter: adapters.attachments }));
  if (route.key === "settings") {
    root.append(createSettingsPage({
      context,
      adapter: adapters.settings,
      onSettingsUpdated: (settings) => renderContext({ ...context, grossBuiltArea: settings.grossBuiltArea }),
    }));
  }
  liveRegion.textContent = `صفحه ${route.label} نمایش داده شد.`;
  root.focus();
}

try {
  const context = resolveContext();
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
  const adapters = Object.freeze({
    settings: createMockSettingsAdapter(context, { initialState: settingsState }),
    financialItems: createMockFinancialItemsAdapter(context, { initialState: itemsState }),
    prices: createMockPricesAdapter(context, { initialState: pricesState }),
    progress: createMockProgressAdapter(context, { initialState: progressState }),
    invoices: createMockInvoicesAdapter(context, { initialState: invoicesState }),
    attachments: createMockAttachmentsAdapter(context, { initialState: filesState }),
  });
  renderContext(context);
  createHashRouter({ routes: ROUTES, defaultPath: DEFAULT_ROUTE, onNavigate: (route) => renderRoute(route, context, adapters) }).start();
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
