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
  heading.append(copy);
  section.append(heading);

  /**
   * The way to the phases' own page, under the chart rather than beside the
   * heading. It was a ghost button up there, which put a second bordered box
   * inside a card that is already one and took height off the chart on a board
   * that has none to give. As a line of text it reads the way the invoices card
   * says its own way in — same place, same weight, smaller than the body.
   *
   * It is appended last in every branch, including the ones that have no chart:
   * a reader who is told the rollup is not ready yet still has somewhere to go.
   */
  const finish = () => {
    const link = element("a", "level-one-section__link");
    link.href = "#/level-one";
    link.append(document.createTextNode("مشاهده جزئیات مراحل"), element("span", "level-one-section__chevron", "‹"));
    section.append(link);
    return section;
  };

  if (error) {
    section.append(element("p", "inline-notice", formatApiErrorMessage(error, "دریافت گزارش سطح ۱ انجام نشد.")));
    return finish();
  }
  if (rollup?.available === false) {
    section.append(element("p", "inline-notice", "سرویس مالی هنوز هزینه‌ها را بر اساس ساختار شکست کار جمع نمی‌زند. این بخش به‌محض آماده‌شدن سرویس، داده واقعی را نشان می‌دهد."));
    return finish();
  }

  const view = buildWbsView({ nodes: rollup?.nodes ?? [], unattributedActualIrr: rollup?.unattributedActualIrr });
  if (view.isEmpty) {
    section.append(element("p", "inline-notice", "برای هیچ مرحله‌ای از پروژه هزینه یا برآوردی ثبت نشده است."));
    return finish();
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
  return finish();
}
