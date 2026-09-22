import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { defaultSnapshot } from "../../shared/progress/project-snapshot.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
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
      /* TODAY, not the snapshot's own date -- the same choice the page that links here
         makes, and for the same reason: the snapshot says which PROGRESS facts to use and
         is not the financial cutoff. Reading at the snapshot's date asked what the
         estimate was on 2025-10-02, before any of these lines existed, and the honest
         answer to that question is nothing. So every phase showed «—» on a page reached
         from one showing 3,607,438,967,777 rial, and the figures appeared to vanish on
         the way in. Same project, same source version, two different questions. */
      const request = {
        reportingDate: getTehranTodayIso(),
        progressSnapshotId: snapshot.progressSnapshotId,
      };
      // The phase list is always fetched: the detail view needs its parent's own
      // figures to say what share of the phase each child accounts for.
      const [top, children] = await Promise.all([
        adapters.reports.getWbsRollup(request),
        wbsCode ? adapters.reports.getWbsRollup({ ...request, parentWbsCode: wbsCode }) : null,
      ]);
      state = createRequestState(REQUEST_STATUS.SUCCESS,
                                 { snapshot, top, children, reportingDate: request.reportingDate });
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader(data) {
    const parent = data ? data.top.nodes.find((node) => node.wbsCode === wbsCode) : null;
    return createFinancePageHeader(
      wbsCode ? (parent?.title ?? `مرحله ${wbsCode}`) : "هزینه مراحل پروژه");
  }

  /**
   * Which day these figures are for, and from which schedule.
   *
   * Every amount on this page is bound by the reporting date: at the snapshot's own date
   * the estimates are all unknown, and at a later one they are stated -- same page, same
   * project, same source version, two different readings. A page that does not name its
   * date produces numbers that cannot be compared with anything.
   *
   * It sits with the figures rather than in the header, which by contract carries a
   * heading and a back link and nothing else.
   */
  function renderProvenance(data) {
    const snapshot = data?.snapshot;
    if (!data?.reportingDate) return null;
    /* Two dates, and they are two different facts. The report date is the financial
       cutoff these amounts are read at; the schedule date is when the source file said
       the work stood. Printing the snapshot's date beside figures read at today would
       name a day the numbers are not from. */
    return element("p", "level-one-provenance",
      `تاریخ گزارش: ${formatBusinessDate(data.reportingDate)}`
      + (snapshot?.reportingDate
        ? ` · وضعیت برنامه زمانی: ${formatBusinessDate(snapshot.reportingDate)}` : "")
      + (snapshot?.sourceFileNameSafe ? ` · برنامه زمانی: ${snapshot.sourceFileNameSafe}` : ""));
  }

  function renderUnavailable() {
    const card = element("section", "state-card");
    card.append(
      element("h2", "", "گزارش سطح‌بندی هزینه هنوز در دسترس نیست"),
      element("p", "", "سرویس مالی هنوز هزینه‌ها را بر اساس ساختار شکست کار جمع نمی‌زند. ساختار این صفحه آماده است و به‌محض آماده‌شدن سرویس، همین صفحه داده واقعی را نشان می‌دهد."),
    );
    return card;
  }

  /**
   * What the estimate on this page does NOT include.
   *
   * The service reports the sum of the lines that state a baseline, and says how
   * many it could not include. Those two facts have to arrive together: the figure
   * alone is a smaller number wearing the name of the whole, which is exactly the
   * reason it used to be withheld entirely — and withholding it hid the estimate
   * that WAS stated, which was most of it.
   */
  function renderPartialEstimateNotice(view) {
    if (!view.totals?.estimateIsPartial) return null;
    const count = formatDisplayNumber(String(view.totals.missingEstimateLineCount));
    const notice = element("aside", "level-one-partial");
    notice.append(
      element("h3", "", "برآورد ناقص است"),
      element("p", "", `${count} ردیف برآوردی مبلغ اولیه‌ای ثبت نکرده‌اند و در ارقام «برآورد اولیه» این صفحه نیامده‌اند. آنچه می‌بینید جمع ردیف‌هایی است که برآورد دارند، نه کل برآورد پروژه.`),
    );
    return notice;
  }

  /**
   * Phases nobody has costed at all.
   *
   * Their estimate cell is blank, and a blank cell is read as "nothing here" unless
   * something says otherwise. The service reports zero estimate lines for them, which is
   * the evidence: there is nothing to sum, so there is no figure -- as opposed to a figure
   * that came out at zero, which would print as zero and mean something quite different.
   */
  function renderUnknownEstimateNotice(view) {
    const without = (view.rows ?? []).filter((row) => !row.hasEstimateBasis);
    if (!without.length) return null;
    const notice = element("aside", "level-one-partial");
    notice.append(
      element("h3", "", "برآورد این مراحل نامعلوم است، نه صفر"),
      // "As of this report's date" is not a hedge: an estimate line recorded after the
      // reporting date is not part of that date's picture, so a stage can have no lines on
      // one day and many on another. Saying it without the date would describe the project
      // when it only describes the day.
      element("p", "", `تا تاریخ این گزارش، ${formatDisplayNumber(String(without.length))} مرحله `
        + `هیچ ردیف برآوردی ندارند، پس مبلغی برای جمع‌زدن وجود ندارد و خانه برآوردشان خالی است: `
        + `${without.map((row) => row.wbsCode).join("، ")}. `
        + `این با مرحله‌ای که برآوردش محاسبه و صفر شده فرق دارد؛ آن یکی صفر نشان داده می‌شود.`),
    );
    return notice;
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
      // The estimate card is the one figure on this grid that can be a subtotal, so
      // it is the one that has to say so where it is read, not only in the notice.
      if (label === "برآورد اولیه مراحل" && view.totals.estimateIsPartial) {
        card.dataset.partial = "true";
        card.append(element("span", "level-one-totals__note",
          `ناقص — ${formatDisplayNumber(String(view.totals.missingEstimateLineCount))} ردیف بدون برآورد`));
      }
      grid.append(card);
    });
    return grid;
  }

  /**
   * The ESTIMATE that reaches no phase, for the same reason the cost below is shown.
   *
   * A line reaches a phase through its activity. One naming an activity the catalogue
   * does not know, or an activity carrying no WBS code, is in the project's estimate and
   * in none of the rows above -- so the stages sum to less than the project and nothing
   * said by how much. Measured on the candidate: 40.8 million toman across 75 lines,
   * which is why the page's total card and the API's own figure disagreed.
   *
   * Separate from «برآورد ناقص است», which is a different absence: that one is lines
   * inside a phase that state no baseline. A line can be in neither, either, or both.
   */
  function renderUnplacedEstimate(view) {
    const amount = view.totals?.unmappedEstimateIrr;
    const count = view.totals?.unmappedEstimateLineCount ?? 0;
    if (!count || amount === null || amount === undefined) return null;
    const notice = element("aside", "level-one-unattributed");
    notice.append(
      element("h3", "", "برآورد خارج از مراحل"),
      element("p", "", `${formatCompactMoneyFromIrr(amount)} برآورد روی ${formatDisplayNumber(String(count))} ردیف ثبت شده که فعالیتشان به هیچ مرحله‌ای نمی‌رسد، پس در جمع مراحل بالا نیامده است. این مبلغ در «برآورد اولیه» کل پروژه هست.`),
    );
    const value = element("strong", "numeric", formatCompactMoneyFromIrr(amount));
    value.title = formatTomanFromIrr(amount);
    notice.append(value);
    return notice;
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
    const marked = view.rows.some((row) => row.estimateIsPartial);
    table.append(
      tableCaption(marked
        ? `${caption} — ٭ یعنی برآورد این مرحله ناقص است و ردیف‌های بدون برآورد در آن نیامده‌اند`
        : caption),
      tableHead(columns));
    const body = document.createElement("tbody");
    view.rows.forEach((row) => {
      const record = document.createElement("tr");
      if (row.overBudget) record.dataset.state = "over";
      const code = document.createElement("td");
      if (linked && row.hasChildren) {
        const link = element("a", "", row.wbsCode);
        link.href = `#finance/level-one?wbs=${encodeURIComponent(row.wbsCode)}`;
        code.append(link);
      } else {
        code.textContent = row.wbsCode;
      }
      code.className = "numeric";
      const cells = [
        row.title,
        formatDisplayNumber(String(row.activityCount)),
        // A phase whose estimate is a subtotal is marked in the cell itself. The
        // mark is explained in the table's caption and in the notice above it, so
        // it is never the only thing a reader has to go on.
        row.estimateIsPartial
          ? `${formatCompactMoneyFromIrr(row.initialEstimateIrr)}٭`
          : formatCompactMoneyFromIrr(row.initialEstimateIrr),
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
        if (index === 2 && row.estimateIsPartial) {
          cell.dataset.partial = "true";
          cell.title = `${cell.title} — ${formatDisplayNumber(String(row.missingEstimateLineCount))} ردیف این مرحله برآورد اولیه ندارند و در این مبلغ نیستند`;
        }
        record.append(cell);
      });
      body.append(record);
    });
    table.append(body);
    wrapper.append(table);
    return wrapper;
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();
    const provenance = renderProvenance(data);
    if (provenance) fragment.append(provenance);
    if (data.top.available === false) {
      fragment.append(renderUnavailable());
      return fragment;
    }

    const topView = buildWbsView({
      nodes: data.top.nodes,
      unattributedActualIrr: data.top.unattributedActualIrr,
      // Only the top level carries these: a phase's children account for all of it, so
      // claiming the project's unplaced lines again inside one phase would double-count.
      unmappedEstimateIrr: data.top.unmappedEstimateIrr,
      unmappedEstimateLineCount: data.top.unmappedEstimateLineCount,
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
      const partial = renderPartialEstimateNotice(topView);
      if (partial) fragment.append(partial);
      const unknown = renderUnknownEstimateNotice(topView);
      if (unknown) fragment.append(unknown);
      const unplaced = renderUnplacedEstimate(topView);
      if (unplaced) fragment.append(unplaced);
      if (topView.unattributed) fragment.append(renderUnattributed(topView));
      fragment.append(renderTable(topView, { caption: "هزینه مراحل سطح ۱", linked: true }));
      return fragment;
    }

    const parent = topView.rows.find((row) => row.wbsCode === wbsCode) ?? null;
    if (!parent) {
      fragment.append(element("p", "inline-notice", "این مرحله در ساختار پروژه پیدا نشد."));
      return fragment;
    }
    const parentView = buildWbsView({ nodes: [rawOf(data.top.nodes, wbsCode)] });
    fragment.append(renderTotals(parentView));
    const parentPartial = renderPartialEstimateNotice(parentView);
    if (parentPartial) fragment.append(parentPartial);
    const parentUnknown = renderUnknownEstimateNotice(parentView);
    if (parentUnknown) fragment.append(parentUnknown);

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
    return fragment;
  }

  /** The chart speaks in plan/actual pairs; the view speaks in phases. */
  function chartRows(view, { linked = true } = {}) {
    return view.rows.map((row) => ({
      title: row.title,
      href: linked ? `#finance/level-one?wbs=${encodeURIComponent(row.wbsCode)}` : null,
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
