import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { defaultSnapshot } from "../../shared/progress/project-snapshot.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { buildWbsView } from "../../shared/reports/wbs-rollup.js";
import { createLevelOneChart } from "./level-one-chart.js";

/** A percentage the way the rest of the module writes one. */
function percent(value) {
  return value === null || value === undefined ? "—" : `${formatDisplayNumber(value)}٪`;
}

/**
 * گزارش مالی سطح ۱ — cost by phase, and one phase in detail.
 *
 * The same page serves both: with no `wbs` in the address it lists the project's
 * phases, and with one it opens that phase — its level-2 breakdown and the items
 * the money went on. That keeps the drill-down in the address, so a phase can be
 * linked to and reopened rather than only reached by clicking.
 *
 * The figures come from `GET /reports/live/by-wbs`, which is specified but not
 * built (docs/BACKEND_NEEDS_LEVEL1_REPORT_FA.md). Until it is, the API adapter
 * answers `available: false` and this page says exactly what is missing instead
 * of drawing an empty chart that looks like a finished answer.
 */
export function createLevelOnePage({ context, adapters, wbsCode = null }) {
  const root = element("div", "level-one-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const snapshots = await adapters.progress.getSnapshots();
      // The same snapshot the page that links here reads: a drilldown that quietly picked
      // a different one would show phase shares that do not add up to the page above it.
      const snapshot = defaultSnapshot(snapshots);
      if (!snapshot) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
        paint();
        return;
      }
      const request = {
        reportingDate: snapshot.reportingDate,
        progressSnapshotId: snapshot.progressSnapshotId,
      };
      // The phase list is always fetched: the detail view needs its parent's own
      // figures to say what share of the phase each child accounts for.
      const [top, children] = await Promise.all([
        adapters.reports.getWbsRollup(request),
        wbsCode ? adapters.reports.getWbsRollup({ ...request, parentWbsCode: wbsCode }) : null,
      ]);
      state = createRequestState(REQUEST_STATUS.SUCCESS, { snapshot, top, children });
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader(data) {
    const parent = data ? data.top.nodes.find((node) => node.wbsCode === wbsCode) : null;
    return createFinancePageHeader(wbsCode ? (parent?.title ?? `مرحله ${wbsCode}`) : "هزینه مراحل پروژه");
  }

  function renderUnavailable() {
    const card = element("section", "state-card");
    card.append(
      element("h2", "", "گزارش سطح‌بندی هزینه هنوز در دسترس نیست"),
      element("p", "", "سرویس مالی هنوز هزینه‌ها را بر اساس ساختار شکست کار جمع نمی‌زند. ساختار این صفحه آماده است و به‌محض آماده‌شدن سرویس، همین صفحه داده واقعی را نشان می‌دهد."),
    );
    return card;
  }

  function renderTotals(view) {
    const grid = element("div", "level-one-totals");
    [
      ["برآورد اولیه مراحل", view.totals.initialEstimateIrr, ""],
      ["هزینه واقعی مراحل", view.totals.actualCostIrr, ""],
      ["مصرف‌شده از برآورد", percent(view.totals.consumedPercent), "text"],
      ["مراحل بیشتر از برآورد", formatDisplayNumber(String(view.overBudgetCount)), "text"],
    ].forEach(([label, value, kind]) => {
      const card = element("article", "level-one-totals__card");
      const figure = element("strong", "level-one-totals__value numeric",
        kind === "text" ? value : formatCompactMoneyFromIrr(value));
      if (kind !== "text") figure.title = formatTomanFromIrr(value);
      card.append(figure, element("span", "level-one-totals__label", label));
      grid.append(card);
    });
    return grid;
  }

  /**
   * The cost that reaches no phase. Shown as its own line rather than folded
   * into a phase or dropped: folding it would put money where it did not go,
   * and dropping it would leave the phases summing to less than the project
   * with nothing on the page to explain the gap.
   */
  function renderUnattributed(view) {
    const notice = element("aside", "level-one-unattributed");
    notice.append(
      element("h3", "", "هزینه تخصیص‌نیافته"),
      element("p", "", `${formatCompactMoneyFromIrr(view.unattributed.actualCostIrr)} از هزینه ثبت‌شده به هیچ مرحله‌ای وصل نیست، چون خط فاکتور آن به ردیف برآوردی ارجاع ندارد. این مبلغ در جمع مراحل بالا نیامده است.`),
    );
    const value = element("strong", "numeric", percent(view.unattributed.sharePercent));
    value.title = formatTomanFromIrr(view.unattributed.actualCostIrr);
    notice.append(value);
    return notice;
  }

  function renderTable(view, { caption, linked }) {
    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table level-one-table");
    const columns = ["کد", "عنوان", "تعداد فعالیت", "برآورد اولیه", "هزینه واقعی", "نسبت به برآورد", "پیش‌بینی نهایی"];
    table.append(tableCaption(caption), tableHead(columns));
    const body = document.createElement("tbody");
    view.rows.forEach((row) => {
      const record = document.createElement("tr");
      if (row.overBudget) record.dataset.state = "over";
      const code = document.createElement("td");
      if (linked && row.hasChildren) {
        const link = element("a", "", row.wbsCode);
        link.href = `#/level-one?wbs=${encodeURIComponent(row.wbsCode)}`;
        code.append(link);
      } else {
        code.textContent = row.wbsCode;
      }
      code.className = "numeric";
      const cells = [
        row.title,
        formatDisplayNumber(String(row.activityCount)),
        formatCompactMoneyFromIrr(row.initialEstimateIrr),
        formatCompactMoneyFromIrr(row.actualCostIrr),
        row.hasEstimate ? percent(row.consumedPercent) : "—",
        formatCompactMoneyFromIrr(row.forecastFinalIrr),
      ];
      record.append(code);
      cells.forEach((text, index) => {
        const cell = element("td", index === 0 ? "" : "numeric");
        cell.textContent = text;
        if (index === 2 || index === 3 || index === 5) {
          cell.title = formatTomanFromIrr([row.initialEstimateIrr, row.actualCostIrr, row.forecastFinalIrr][index === 2 ? 0 : index === 3 ? 1 : 2]);
        }
        record.append(cell);
      });
      body.append(record);
    });
    table.append(body);
    wrapper.append(table);
    return wrapper;
  }

  /** What the money in one phase was spent on, by kind of item. */
  function renderBreakdown(row) {
    const section = element("section", "level-one-breakdown");
    section.append(element("h2", "", "ترکیب هزینه این مرحله"));
    if (!row?.breakdown?.length) {
      section.append(element("p", "inline-notice", "تفکیک اقلام این مرحله ثبت نشده است."));
      return section;
    }
    const list = element("div", "level-one-breakdown__list");
    row.breakdown.forEach((entry) => {
      const item = element("article", "level-one-breakdown__item");
      const head = element("div", "level-one-breakdown__head");
      head.append(element("h3", "", entry.label), element("strong", "numeric", formatCompactMoneyFromIrr(entry.amountIrr)));
      const track = element("div", "level-one-breakdown__track");
      const bar = element("span", "level-one-breakdown__bar chart-mark");
      bar.style.setProperty("--bar-width", `${entry.magnitude}%`);
      bar.title = formatTomanFromIrr(entry.amountIrr);
      track.append(bar);
      item.append(head, track, element("span", "level-one-breakdown__share", `${percent(entry.sharePercent)} از هزینه این مرحله`));
      list.append(item);
    });
    section.append(list);
    return section;
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();
    if (data.top.available === false) {
      fragment.append(renderUnavailable());
      return fragment;
    }

    const topView = buildWbsView({
      nodes: data.top.nodes,
      unattributedActualIrr: data.top.unattributedActualIrr,
    });
    if (topView.isEmpty) {
      fragment.append(renderUnavailable());
      return fragment;
    }

    if (!wbsCode) {
      const chartCard = element("section", "level-one-card");
      chartCard.append(element("h2", "", "هزینه هر مرحله در برابر برآورد آن"));
      chartCard.append(createLevelOneChart({
        rows: chartRows(topView),
        formatExact: (value) => formatTomanFromIrr(value),
        ariaLabel: "نمودار هزینه واقعی هر مرحله در برابر برآورد اولیه همان مرحله",
      }));
      fragment.append(renderTotals(topView), chartCard);
      if (topView.unattributed) fragment.append(renderUnattributed(topView));
      fragment.append(renderTable(topView, { caption: "هزینه مراحل سطح ۱", linked: true }));
      return fragment;
    }

    const parent = topView.rows.find((row) => row.wbsCode === wbsCode) ?? null;
    if (!parent) {
      fragment.append(element("p", "inline-notice", "این مرحله در ساختار پروژه پیدا نشد."));
      return fragment;
    }
    fragment.append(renderTotals(buildWbsView({ nodes: [rawOf(data.top.nodes, wbsCode)] })));

    const childView = buildWbsView({ nodes: data.children?.nodes ?? [] });
    const childCard = element("section", "level-one-card");
    childCard.append(element("h2", "", "گزارش سطح ۲ این مرحله"));
    if (childView.isEmpty) {
      childCard.append(element("p", "inline-notice", "برای این مرحله زیرمجموعه‌ای در ساختار پروژه ثبت نشده است."));
    } else {
      childCard.append(createLevelOneChart({
        rows: chartRows(childView, { linked: false }),
        formatExact: (value) => formatTomanFromIrr(value),
        ariaLabel: `نمودار هزینه زیرمجموعه‌های مرحله ${wbsCode}`,
      }));
    }
    fragment.append(childCard);
    if (!childView.isEmpty) fragment.append(renderTable(childView, { caption: `زیرمجموعه‌های مرحله ${wbsCode}`, linked: false }));
    fragment.append(renderBreakdown(parent));
    return fragment;
  }

  /** The chart speaks in plan/actual pairs; the view speaks in phases. */
  function chartRows(view, { linked = true } = {}) {
    return view.rows.map((row) => ({
      title: row.title,
      href: linked ? `#/level-one?wbs=${encodeURIComponent(row.wbsCode)}` : null,
      planIrr: row.initialEstimateIrr,
      actualIrr: row.actualCostIrr,
      overBudget: row.overBudget,
    }));
  }

  function rawOf(nodes, code) {
    return nodes.find((node) => node.wbsCode === code) ?? nodes[0];
  }

  function renderEmpty() {
    const card = element("section", "state-card");
    card.append(
      element("h2", "", "هنوز نسخه پیشرفتی برای این گزارش ثبت نشده است"),
      element("p", "", "گزارش سطح ۱ روی یک نسخه پیشرفت آماده ساخته می‌شود."),
    );
    return card;
  }

  function paint() {
    const data = state.status === REQUEST_STATUS.SUCCESS ? state.data : null;
    root.replaceChildren(
      renderHeader(data),
      renderPageState(state, { renderContent, renderEmpty, onRetry: load }),
    );
  }

  load();
  return root;
}
