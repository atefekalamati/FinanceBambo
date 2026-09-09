import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { element } from "../../shared/dom/elements.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { SURFACES, homeRouteFor } from "../../core/config/routes.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { buildPeriodPresets, validatePeriod } from "../../shared/dates/reporting-periods.js";
import { findReport, normalizeSelection } from "./report-catalog.js";
import { loadReportData } from "./report-data.js";
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
      const data = await loadReportData({ adapters, selection: chosen, period: range, today: getTehranTodayIso() });
      generatedAt = new Date().toISOString();
      state = createRequestState(data ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, data);
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    const header = createFinancePageHeader("گزارش اختصاصی مالی", "feature-header report-builder-page__header");
    const actions = element("div", "finance-page-actions");
    const print = element("button", "button button--primary", "چاپ یا ذخیره PDF");
    print.type = "button";
    print.disabled = state.status !== REQUEST_STATUS.SUCCESS;
    print.addEventListener("click", () => window.print());
    actions.append(print);
    const fragment = document.createDocumentFragment();
    fragment.append(header);
    if (actions.childElementCount) fragment.append(actions);
    return fragment;
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
    chosen.forEach((key, index) => {
      const definition = findReport(key);
      const render = REPORT_SECTIONS[key];
      if (!definition || !render) return;
      const chapter = element("article", "report-doc__chapter");
      const usesSnapshot = definition.needs.some((need) => ["overview", "wbs"].includes(need));
      const monthlyPeriod = data.monthly?.windowStart && data.monthly?.windowEnd
        ? { from: data.monthly.windowStart, to: data.monthly.windowEnd } : null;
      chapter.append(createReportHeader({
        title: definition.title,
        facts: projectFacts({
          project: { name: context.projectName, code: context.projectCode },
          snapshot: usesSnapshot ? data.snapshot?.sourceFileNameSafe : null,
          reportingDate: usesSnapshot || definition.needs.includes("monthly") ? data.reportingDate : data.asOfDate,
          period: definition.period ? data.period : definition.needs.includes("monthly") ? monthlyPeriod : null,
        }),
      }));
      const section = reportSection(index + 1, definition.title, definition.summary);
      section.dataset.reportKey = key;
      render(data).forEach((node) => section.append(node));
      chapter.append(section, reportFooter(generatedAt));
      document_.append(chapter);
    });

    return document_;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
