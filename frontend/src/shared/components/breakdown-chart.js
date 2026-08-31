import { element, tableCaption, tableHead } from "../dom/elements.js";
import { compactMoneyFromIrr, compactMoneyScale, formatCompactMoneyFromIrr, formatTomanFromIrr } from "../formatters/money.js";
import { formatDisplayNumber } from "../formatters/display.js";
import { createTomanDisplay } from "./money-display.js";

/**
 * ترکیب هزینه — actual cost per kind of item against the estimate for that kind.
 *
 * Lifted out of the finance overview so the report page can show the full
 * comparison while the overview shows a summary of it. One implementation, two
 * places: the overview's donut is a way in, not a second version of this.
 */

/**
 * The bullet form of the cost comparison.
 *
 * One track per category. The bar is what was spent; the marker across it is
 * what was estimated. Passing the marker is the whole point of the chart, so it
 * is a thing the eye lands on rather than a difference between two lengths in
 * two different rows.
 *
 * The scale is shared and ends on a round number, so the categories stay
 * comparable as amounts and every bar can be read against the axis. What a
 * shared scale cannot show — how far through its own budget a category is — is
 * the percentage beside it.
 */
function createBulletChart(view) {
  const chart = element("div", "bullet-chart");
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", "نمودار هزینه واقعی هر نوع قلم در برابر برآورد همان نوع");

  const gridlines = () => {
    const grid = element("span", "bullet-chart__grid");
    grid.setAttribute("aria-hidden", "true");
    view.ticks.forEach((tick) => {
      const line = element("span", "bullet-chart__gridline");
      line.style.setProperty("--at", `${tick.magnitude}%`);
      grid.append(line);
    });
    return grid;
  };

  view.rows.forEach((row) => {
    const article = element("article", `bullet-chart__row${row.overBudget ? " bullet-chart__row--over" : ""}`);
    article.append(element("h3", "", row.label));

    const track = element("div", "bullet-chart__track");
    track.append(gridlines());
    if (!row.actualBelowZero && row.actualMagnitude > 0) {
      const fill = element("span", `bullet-chart__fill chart-mark${row.overBudget ? " bullet-chart__fill--over" : ""}`);
      fill.style.setProperty("--fill", `${row.actualMagnitude}%`);
      track.append(fill);
    }
    if (row.estimateMagnitude !== null) {
      const target = element("span", "bullet-chart__target chart-mark");
      target.style.setProperty("--at", `${row.estimateMagnitude}%`);
      target.title = `برآورد اولیه: ${formatTomanFromIrr(row.initialEstimateIrr)}`;
      track.append(target);
    }

    const amount = element("span", "bullet-chart__value numeric compact-money", formatCompactMoneyFromIrr(row.actualCostIrr));
    amount.dataset.exact = formatTomanFromIrr(row.actualCostIrr);
    amount.setAttribute("aria-label", formatTomanFromIrr(row.actualCostIrr));
    amount.tabIndex = 0;

    // One sentence per row, because the shape only means something next to the
    // number it stands for.
    const ratio = element("span", `bullet-chart__ratio${row.overBudget ? " bullet-chart__ratio--over" : ""}`);
    if (row.consumedPercent !== null) {
      ratio.textContent = row.overBudget
        ? `${formatDisplayNumber(String(Math.round(row.consumedPercent)))}٪ برآورد`
        : `${formatDisplayNumber(String(Math.round(row.consumedPercent)))}٪ مصرف‌شده`;
    } else if (row.actualCostIrr !== "0") {
      ratio.classList.add("bullet-chart__ratio--unknown");
      ratio.textContent = "برآورد ثبت نشده";
    } else {
      ratio.classList.add("bullet-chart__ratio--unknown");
      ratio.textContent = "بدون داده";
    }

    article.setAttribute("aria-label", `${row.label}؛ هزینه واقعی ${formatTomanFromIrr(row.actualCostIrr)}؛ ${row.hasEstimate ? `برآورد ${formatTomanFromIrr(row.initialEstimateIrr)}؛ ${ratio.textContent}` : "برآوردی ثبت نشده است"}`);
    article.append(track, amount, ratio);
    chart.append(article);
  });

  const scale = element("div", "bullet-chart__scale");
  scale.setAttribute("aria-hidden", "true");
  scale.append(element("span", "bullet-chart__scale-label", compactMoneyScale(view.ceilingIrr)?.unit ?? ""));
  const scaleTrack = element("div", "bullet-chart__scale-track");
  view.ticks.forEach((tick) => {
    const mark = element("span", "bullet-chart__scale-mark", formatDisplayNumber(compactMoneyScale(view.ceilingIrr)?.format(tick.valueIrr) ?? ""));
    mark.style.setProperty("--at", `${tick.magnitude}%`);
    scaleTrack.append(mark);
  });
  scale.append(scaleTrack);
  chart.append(scale);

  const viewport = element("div", "bullet-chart-viewport");
  viewport.append(chart);
  return viewport;
}

function createBreakdownChart(view) {
  const section = document.createElement("section");
  section.className = "finance-breakdown";
  const heading = document.createElement("div");
  heading.className = "section-heading";
  const copy = document.createElement("div");
  const eyebrow = document.createElement("span");
  eyebrow.textContent = "ترکیب هزینه";
  const title = document.createElement("h2");
  title.textContent = "مقایسه برآورد اولیه و هزینه واقعی";
  copy.append(eyebrow, title);
  const hint = document.createElement("small");
  hint.textContent = "میله هزینه واقعی است و نشانگر، برآورد همان نوع قلم";
  heading.append(copy, hint);

  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll breakdown-table-wrapper";
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "مقادیر دقیق مقایسه مالی");
  wrapper.tabIndex = 0;
  const table = document.createElement("table");
  table.className = "data-table breakdown-table";
  const caption = document.createElement("caption");
  caption.textContent = "جدول جایگزین نمودار ترکیب هزینه به تفکیک نوع قلم هزینه";
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  ["نوع قلم هزینه", "برآورد اولیه", "هزینه واقعی ثبت‌شده", "نسبت به برآورد", "پیش‌بینی هزینه نهایی"].forEach((text) => {
    const cell = document.createElement("th");
    cell.textContent = text;
    header.append(cell);
  });
  thead.append(header);
  const tbody = document.createElement("tbody");
  view.rows.forEach((row) => {
    const record = document.createElement("tr");
    [row.label, row.initialEstimateIrr, row.actualCostIrr].forEach((text, index) => {
      const cell = document.createElement("td");
      if (index === 0) cell.textContent = text;
      else cell.append(createTomanDisplay(text));
      record.append(cell);
    });
    // The one column the table never had: the comparison itself, in a number.
    const ratioCell = document.createElement("td");
    if (row.consumedPercent === null) {
      ratioCell.textContent = row.actualCostIrr === "0" ? "—" : "برآورد ثبت نشده";
    } else {
      ratioCell.className = `numeric${row.overBudget ? " variance-direction variance-direction--increase" : ""}`;
      ratioCell.textContent = `${formatDisplayNumber(String(Math.round(row.consumedPercent)))}٪`;
    }
    record.append(ratioCell);
    const forecast = document.createElement("td");
    forecast.append(createTomanDisplay(row.forecastFinalIrr));
    record.append(forecast);
    tbody.append(record);
  });
  table.append(caption, thead, tbody);
  wrapper.append(table);
  section.append(heading, createBulletLegend(), createBulletChart(view), wrapper);
  return section;
}

function createBulletLegend() {
  const legend = element("ul", "breakdown-legend breakdown-legend--bullet");
  const actual = element("li", "", "هزینه واقعی ثبت‌شده");
  actual.dataset.series = "actual";
  const target = element("li", "", "برآورد اولیه");
  target.dataset.series = "target";
  const over = element("li", "", "بیش از برآورد");
  over.dataset.series = "over";
  legend.append(actual, target, over);
  return legend;
}

export { createBulletChart, createBreakdownChart, createBulletLegend };
