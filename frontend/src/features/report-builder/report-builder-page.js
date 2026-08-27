import { element } from "../../shared/dom/elements.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { buildPeriodPresets, validatePeriod } from "../../shared/dates/reporting-periods.js";
import { datasetsFor, findReport, normalizeSelection, selectionUsesPeriod } from "./report-catalog.js";
import { REPORT_SECTIONS } from "./report-sections.js";
import { reportFooter, reportSection } from "./report-document.js";
import { createReportHeader, projectFacts } from "../../shared/reports/report-header.js";

/**
 * The document a chosen set of reports produces.
 *
 * It is a page rather than something printed straight out of a dialog, so the
 * selection lives in the address: a document can be re-opened, corrected and
 * handed to someone else without being rebuilt from memory. Print is the last
 * step, not the only one.
 */
export function createReportBuilderPage({ context, adapters, selection = [], period = null }) {
  const root = element("div", "report-builder-page");
  const chosen = normalizeSelection(selection);
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let generatedAt = null;

  const range = resolvePeriod(period);

  function resolvePeriod(requested) {
    if (requested?.from && requested?.to && validatePeriod(requested).valid) return requested;
    const presets = buildPeriodPresets(getTehranTodayIso());
    return presets.find((preset) => preset.key === "yearToDate")?.range ?? null;
  }

  async function load() {
    if (!chosen.length) {
      state = createRequestState(REQUEST_STATUS.EMPTY);
      paint();
      return;
    }
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const snapshots = await adapters.progress.getSnapshots();
      const reportable = snapshots.filter((snapshot) => snapshot.status === "ready");
      if (!reportable.length) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
        paint();
        return;
      }
      const snapshot = reportable[0];
      // Only what the chosen reports asked for. A document of two summaries must
      // not make the reader wait on the price list it does not contain.
      const wanted = new Set(datasetsFor(chosen));
      const [overview, monthly, invoices, audit, prices, financialItems] = await Promise.all([
        wanted.has("overview")
          ? adapters.reports.getOverview({ reportingDate: snapshot.reportingDate, progressSnapshotId: snapshot.progressSnapshotId })
          : null,
        wanted.has("monthly") ? adapters.reports.getMonthlyTrend({ reportingDate: snapshot.reportingDate }) : null,
        wanted.has("invoices") ? adapters.invoices.getInvoices({ pageSize: 200 }) : null,
        wanted.has("audit") ? adapters.audit.getEvents({ occurredFrom: range?.from, occurredTo: range?.to, pageSize: 200 }) : null,
        wanted.has("prices") ? adapters.prices.getPrices() : null,
        wanted.has("financialItems") ? adapters.financialItems.getWorkspace() : null,
      ]);
      generatedAt = new Date().toISOString();
      state = createRequestState(REQUEST_STATUS.SUCCESS, {
        snapshot,
        overview,
        monthly,
        invoices,
        audit,
        prices,
        financialItems,
        period: range,
      });
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    const header = element("header", "feature-header report-builder-page__header");
    const copy = element("div", "feature-header__copy");
    copy.append(
      element("span", "feature-header__eyebrow", "گزارش‌ساز هوشمند"),
      element("h1", "", "گزارش اختصاصی مالی"),
      element("p", "", "این سند از بخش‌هایی ساخته شده که خودتان انتخاب کرده‌اید. برای گرفتن خروجی PDF، دستور چاپ را اجرا کنید."),
    );
    const navigation = element("div", "feature-header__navigation");
    const actions = element("div", "feature-header__other-actions");
    const print = element("button", "button button--primary", "چاپ یا ذخیره PDF");
    print.type = "button";
    print.addEventListener("click", () => window.print());
    actions.append(print);
    const back = element("a", "button button--ghost finance-back-link", `بازگشت به ${SURFACE_LABELS[SURFACES.REPORT]}`);
    back.href = `#${homeRouteFor(SURFACES.REPORT)?.path ?? "/finance-report"}`;
    navigation.append(actions, back);
    header.append(copy, navigation);
    return header;
  }

  function renderEmpty() {
    const card = element("section", "state-card");
    card.append(
      element("h2", "", chosen.length ? "این گزارش هنوز قابل ساخت نیست" : "هیچ بخشی برای گزارش انتخاب نشده است"),
      element("p", "", chosen.length
        ? "برای ساخت گزارش، دست‌کم یک نسخه پیشرفت آماده لازم است."
        : "به صفحه گزارش مالی برگردید و از گزارش‌ساز هوشمند، بخش‌های موردنیاز خود را انتخاب کنید."),
    );
    const back = element("a", "button button--primary", "بازگشت به گزارش‌ساز");
    back.href = `#${homeRouteFor(SURFACES.REPORT)?.path ?? "/finance-report"}`;
    card.append(back);
    return card;
  }

  function renderContent(data) {
    const document_ = element("article", "report-doc");
    document_.append(createReportHeader({
      title: "گزارش اختصاصی مالی",
      facts: projectFacts({
        project: { name: context.projectName, code: context.projectCode },
        snapshot: data.snapshot?.sourceFileNameSafe ?? null,
        reportingDate: data.snapshot?.reportingDate ?? null,
        // Only claimed when something in the document actually uses it.
        period: selectionUsesPeriod(chosen) ? data.period : null,
      }),
    }));

    chosen.forEach((key, index) => {
      const definition = findReport(key);
      const render = REPORT_SECTIONS[key];
      if (!definition || !render) return;
      const section = reportSection(index + 1, definition.title, definition.summary);
      render(data).forEach((node) => section.append(node));
      document_.append(section);
    });

    document_.append(reportFooter(generatedAt));
    return document_;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
