import { element } from "../../shared/dom/elements.js";
import { formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { buildWbsView } from "../../shared/reports/wbs-rollup.js";
import { createLevelOneChart } from "./level-one-chart.js";

/**
 * گزارش مالی سطح ۱ on the report overview — a section of its own, not a card.
 *
 * The project has nineteen phases and each needs two columns, which is more than
 * any card width can hold. It therefore gets the page's full measure and scrolls
 * horizontally inside itself. That is a deliberate exception to the module's
 * rule against internal horizontal scroll: the alternative is columns too narrow
 * to read or a chart that shows only the first few phases, and the reader was
 * asked for by name to be able to move between them.
 */
export function createLevelOneSection({ rollup, error = null }) {
  const section = element("section", "level-one-section");
  section.setAttribute("aria-label", "گزارش مالی سطح ۱");

  const heading = element("div", "section-heading");
  const copy = element("div");
  copy.append(
    element("span", "", "گزارش مالی سطح ۱"),
    element("h2", "", "هزینه هر مرحله در برابر برآورد آن"),
  );
  const link = element("a", "button button--ghost button--small", "مشاهده جزئیات مراحل");
  link.href = "#/level-one";
  heading.append(copy, link);
  section.append(heading);

  if (error) {
    section.append(element("p", "inline-notice", formatApiErrorMessage(error, "دریافت گزارش سطح ۱ انجام نشد.")));
    return section;
  }
  if (rollup?.available === false) {
    section.append(element("p", "inline-notice", "سرویس مالی هنوز هزینه‌ها را بر اساس ساختار شکست کار جمع نمی‌زند. این بخش به‌محض آماده‌شدن سرویس، داده واقعی را نشان می‌دهد."));
    return section;
  }

  const view = buildWbsView({ nodes: rollup?.nodes ?? [], unattributedActualIrr: rollup?.unattributedActualIrr });
  if (view.isEmpty) {
    section.append(element("p", "inline-notice", "برای هیچ مرحله‌ای از پروژه هزینه یا برآوردی ثبت نشده است."));
    return section;
  }

  section.append(createLevelOneChart({
    rows: view.rows.map((row) => ({
      title: row.title,
      href: `#/level-one?wbs=${encodeURIComponent(row.wbsCode)}`,
      planIrr: row.initialEstimateIrr,
      actualIrr: row.actualCostIrr,
      overBudget: row.overBudget,
    })),
    formatExact: (value) => formatTomanFromIrr(value),
    ariaLabel: "نمودار ستونی هزینه واقعی هر مرحله در برابر برآورد اولیه همان مرحله",
  }));

  if (view.overBudgetCount > 0) {
    const note = element("p", "level-one-section__note",
      `${view.overBudgetCount === 1 ? "یک مرحله" : `${view.overBudgetCount} مرحله`} از برآورد اولیه خود عبور کرده است.`);
    section.append(note);
  }
  if (view.unattributed) {
    section.append(element("p", "level-one-section__note",
      `${formatCompactMoneyFromIrr(view.unattributed.actualCostIrr)} از هزینه ثبت‌شده به هیچ مرحله‌ای وصل نیست و در این نمودار نیامده است.`));
  }
  return section;
}
