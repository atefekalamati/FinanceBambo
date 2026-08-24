import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { compactMoneyFromIrr, compactMoneyScale, formatCompactMoneyFromIrr, formatTomanFromIrr, irrToDisplayValue } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { reportWarningText } from "../../shared/warnings/finance-warning-labels.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { createCombinationChart } from "../../shared/components/combination-chart.js";
import { buildMonthlyTrend, TREND_MODES } from "./monthly-trend.js";
import { buildValueTicks } from "../../shared/charts/value-ticks.js";
import { buildBreakdownPresentation, buildOverviewComparisons } from "./report-presentation.js";

const SUMMARY_ITEMS = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه", "مبنای اولیه برآورد پروژه"],
  ["actualCostIrr", "هزینه واقعی ثبت‌شده", "فقط اسناد مالی تأییدشده"],
  ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع", "براساس زیربنای کل پروژه"],
  ["currentExecutedValueIrr", "ارزش روز کار انجام‌شده", "مقدار اجراشده با قیمت روز"],
  ["remainingPhysicalCostIrr", "هزینه کار باقی‌مانده", "کار باقیمانده با قیمت روز"],
  ["forecastFinalCostIrr", "پیش‌بینی هزینه نهایی", "هزینه واقعی به‌اضافه پول ادامه"],
  ["forecastPerSquareMeterIrr", "پیش‌بینی هزینه هر مترمربع", "پیش‌بینی نهایی تقسیم بر زیربنا"],
  ["moneyRequiredToContinueIrr", "بودجه موردنیاز تا تکمیل", "با لحاظ خرید ثبت‌شده مصالح"],
]);

const PRIMARY_SUMMARY_KEYS = new Set(["initialEstimateIrr", "actualCostIrr", "remainingPhysicalCostIrr", "forecastFinalCostIrr"]);
const RELATED_SUMMARY_KEYS = new Set(["actualCostPerSquareMeterIrr", "forecastPerSquareMeterIrr"]);
const SUPPLEMENTARY_SUMMARY_KEYS = new Set([
  "actualCostPerSquareMeterIrr",
  "currentExecutedValueIrr",
  "forecastPerSquareMeterIrr",
  "moneyRequiredToContinueIrr",
]);

const WORK_AREAS = Object.freeze([
  { key: "financial-items", title: "اقلام و برآورد", description: "مدیریت اقلام پروژه، ریز برآورد و مقدارهای اولیه و اصلاح‌شده", meta: "اقلام · برآورد · اصلاحات", href: "#/financial-items" },
  { key: "prices", title: "قیمت روز و تبدیل واحد", description: "ثبت قیمت پایه سازمان، قیمت اختصاصی پروژه و مشاهده تاریخچه قیمت", meta: "قیمت روز · تاریخچه · واحد", href: "#/prices" },
  { key: "progress", title: "پیشرفت و مقادیر انجام‌شده", description: "مشاهده نسخه پیشرفت پروژه، کیفیت داده و اصلاح دستی مقدار", meta: "نسخه پیشرفت · مقدار انجام‌شده · هشدار", href: "#/progress" },
  { key: "invoices", title: "فاکتورها", description: "مشاهده فهرست، وضعیت، منبع، فروشنده، مبلغ و جزئیات خطوط", meta: "فهرست · جزئیات · وضعیت", href: "#/invoices" },
  { key: "reports", title: "گزارش مالی", description: "مشاهده گزارش به‌روز، ثبت گزارش دوره‌ای و دریافت خروجی", meta: "گزارش به‌روز · گزارش ثبت‌شده · چاپ", href: "#/reports" },
  { key: "period-report", title: "گزارش دوره‌ای", description: "ساخت گزارش برای یک بازه زمانی دلخواه با خروجی چاپ و CSV", meta: "بازه دلخواه · مقایسه · خروجی", href: "#/period-report" },
  { key: "audit", title: "تاریخچه تغییرات مالی", description: "ردیابی اصلاحات، تأییدها و عملیات حساس مالی", meta: "انجام‌دهنده · زمان · دلیل", href: "#/audit" },
]);

function createTomanDisplay(value, { compact = false } = {}) {
  const display = document.createElement("span");
  display.className = "money-display";
  if (!/^-?\d+$/.test(String(value ?? ""))) {
    display.textContent = "قابل محاسبه نیست";
    return display;
  }
  const compactValue = compact ? compactMoneyFromIrr(value) : null;
  const exactValue = formatTomanFromIrr(value);
  const unit = document.createElement("span");
  unit.className = "money-display__unit";
  unit.textContent = compactValue?.unit ?? getDisplayCurrencyLabel();
  const amount = document.createElement("bdi");
  amount.className = "money-display__amount numeric";
  amount.dir = "ltr";
  amount.textContent = compactValue?.amount ?? formatDisplayNumber(irrToDisplayValue(value));
  display.append(unit, amount);
  if (compactValue?.compact) {
    display.classList.add("compact-money");
    display.dataset.exact = exactValue;
    display.setAttribute("aria-label", exactValue);
    display.tabIndex = 0;
  }
  return display;
}

function createSummaryCard(key, label, description, data) {
  const card = document.createElement("article");
  const unavailable = data?.[key] === null || data?.[key] === undefined;
  const hierarchy = PRIMARY_SUMMARY_KEYS.has(key) ? "primary" : RELATED_SUMMARY_KEYS.has(key) ? "related" : "support";
  card.className = `summary-card summary-card--${hierarchy}${unavailable ? " summary-card--unavailable" : ""}`;
  card.dataset.metric = key;
  const title = document.createElement("h2");
  title.textContent = label;
  const value = document.createElement("p");
  value.className = "summary-card__value";
  value.append(createTomanDisplay(data?.[key], { compact: true }));
  const unit = document.createElement("span");
  unit.className = "summary-card__unit";
  unit.textContent = unavailable ? "داده مبنا موجود نیست" : description;
  card.append(title, value, unit);
  return card;
}

function createWorkAreaCard(area) {
  const card = document.createElement("article");
  card.className = "work-area-card";
  const marker = document.createElement("span");
  marker.className = "work-area-card__marker";
  marker.setAttribute("aria-hidden", "true");
  marker.textContent = area.title.slice(0, 1);
  const content = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = area.title;
  const description = document.createElement("p");
  description.textContent = area.description;
  const meta = document.createElement("span");
  meta.className = "work-area-card__meta";
  meta.textContent = area.meta;
  content.append(title, description, meta);
  const action = document.createElement(area.href ? "a" : "button");
  action.className = `button ${area.href ? "button--primary" : "button--ghost"}`;
  action.textContent = area.href ? "ورود" : "به‌زودی";
  if (area.href) action.href = area.href;
  else {
    action.type = "button";
    action.disabled = true;
  }
  card.append(marker, content, action);
  return card;
}

function createBreakdownChart(rows) {
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
  hint.textContent = "مقیاس هر دو سری در تمام ردیف‌ها یکسان است";
  heading.append(copy, hint);

  const legend = document.createElement("ul");
  legend.className = "breakdown-legend";
  [["initial", "برآورد اولیه"], ["actual", "هزینه واقعی"]].forEach(([key, label]) => {
    const item = document.createElement("li");
    item.dataset.series = key;
    item.textContent = label;
    legend.append(item);
  });

  const chart = document.createElement("div");
  chart.className = "breakdown-chart";
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", "نمودار مقایسه برآورد اولیه و هزینه واقعی به تفکیک نوع قلم هزینه");
  rows.forEach((row) => {
    const group = document.createElement("article");
    group.className = "breakdown-chart__group";
    const label = document.createElement("h3");
    label.textContent = row.label;
    const bars = document.createElement("div");
    bars.className = "breakdown-chart__bars";
    [["initial", row.bars.initial, row.initialEstimateIrr, "برآورد اولیه"], ["actual", row.bars.actual, row.actualCostIrr, "هزینه واقعی"]].forEach(([series, magnitude, value, seriesLabel]) => {
      const seriesRow = document.createElement("div");
      seriesRow.className = "breakdown-chart__series";
      seriesRow.setAttribute("aria-label", `${seriesLabel}: ${formatTomanFromIrr(value)}`);
      const track = document.createElement("div");
      track.className = "breakdown-chart__track";
      const bar = document.createElement("span");
      bar.className = `breakdown-chart__bar breakdown-chart__bar--${series} chart-mark`;
      bar.style.setProperty("--bar-width", `${magnitude}%`);
      bar.title = `${seriesLabel}: ${formatTomanFromIrr(value)}`;
      track.append(bar);
      const amount = document.createElement("span");
      amount.className = "breakdown-chart__value numeric";
      amount.textContent = formatCompactMoneyFromIrr(value);
      amount.dataset.exact = formatTomanFromIrr(value);
      amount.classList.add("compact-money");
      amount.setAttribute("aria-label", formatTomanFromIrr(value));
      amount.tabIndex = 0;
      seriesRow.append(track, amount);
      bars.append(seriesRow);
    });
    group.append(label, bars);
    chart.append(group);
  });
  const chartViewport = document.createElement("div");
  chartViewport.className = "breakdown-chart-viewport";
  chartViewport.append(chart);

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
  ["نوع قلم هزینه", "برآورد اولیه", "هزینه واقعی ثبت‌شده", "پیش‌بینی هزینه نهایی"].forEach((text) => {
    const cell = document.createElement("th");
    cell.textContent = text;
    header.append(cell);
  });
  thead.append(header);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const record = document.createElement("tr");
    [row.label, row.initialEstimateIrr, row.actualCostIrr, row.forecastFinalIrr].forEach((text, index) => {
      const cell = document.createElement("td");
      if (index === 0) cell.textContent = text;
      else cell.append(createTomanDisplay(text));
      record.append(cell);
    });
    tbody.append(record);
  });
  table.append(caption, thead, tbody);
  wrapper.append(table);
  section.append(heading, legend, chartViewport, wrapper);
  return section;
}

const ANALYSIS_CHARTS = Object.freeze({
  managerial: { label: "تجمیعی", title: "تصویر مدیریتی هزینه پروژه", description: "مقایسه هزینه‌های پروژه با خط مرجع برآورد اولیه" },
  monthly: { label: "روند ماهانه", title: "روند ماهانه هزینه پروژه", description: "هزینه واقعی هر ماه در برابر برآورد همان ماه" },
});

/**
 * Holds both cost charts and shows exactly one at a time. The managerial
 * comparison is the default; the monthly trend is revealed by the switch in
 * this card's heading.
 */
function createManagerialComparisonPanel(metrics, entries, monthly = null, { activeChart = "managerial", onChartChange = () => {} } = {}) {
  const section = document.createElement("section");
  section.className = "finance-analysis-card finance-managerial-comparison";
  const heading = document.createElement("div");
  heading.className = "finance-analysis-card__heading";
  const headingCopy = document.createElement("div");
  const headingTitle = document.createElement("h2");
  headingTitle.textContent = ANALYSIS_CHARTS.managerial.title;
  const headingDescription = document.createElement("p");
  headingDescription.textContent = ANALYSIS_CHARTS.managerial.description;
  headingCopy.append(headingTitle, headingDescription);
  heading.append(headingCopy);

  const chart = document.createElement("div");
  chart.className = "managerial-combo-chart";
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", "مقایسه برآورد اولیه، هزینه واقعی، هزینه باقی‌مانده و پیش‌بینی نهایی");
  /**
   * Three bands stacked over one column set: the money, the bars, the labels.
   * Each bar used to sit in a grid of its own, so a label that wrapped to a
   * second line took that height out of its own bar and left the four bars
   * standing on four different floors. A band is one grid over all four
   * columns, so a cell is always under the cell above it, and the label band is
   * given a height in lines rather than taking one from its text.
   */
  const plot = document.createElement("div");
  plot.className = "managerial-combo-chart__plot";
  const valuesBand = document.createElement("div");
  valuesBand.className = "managerial-combo-chart__band managerial-combo-chart__band--values";
  const barsBand = document.createElement("div");
  barsBand.className = "managerial-combo-chart__band managerial-combo-chart__band--bars";
  const labelsBand = document.createElement("div");
  labelsBand.className = "managerial-combo-chart__band managerial-combo-chart__band--labels";

  entries.forEach((entry) => {
    // Each cell is its own inline-size container, which is what lets the money
    // inside it size itself against the width of its own column.
    const valueCell = document.createElement("div");
    valueCell.className = "managerial-combo-chart__cell managerial-combo-chart__cell--value";
    const value = createTomanDisplay(entry.value, { compact: true });
    value.classList.add("managerial-combo-chart__value");
    valueCell.append(value);
    valuesBand.append(valueCell);

    const barCell = document.createElement("div");
    barCell.className = `managerial-combo-chart__cell managerial-combo-chart__item--${entry.key}`;
    const column = document.createElement("div");
    column.className = "managerial-combo-chart__column chart-mark";
    column.style.setProperty("--column-size", `${entry.magnitude}%`);
    barCell.append(column);
    barsBand.append(barCell);

    const label = document.createElement("h3");
    label.className = "managerial-combo-chart__label";
    label.textContent = entry.label;
    // The band holds a fixed number of lines, so a longer label is clamped
    // rather than allowed to move anything. The full wording stays on hover.
    label.title = entry.label;
    labelsBand.append(label);
  });

  /**
   * A value guide beside the columns: rows at round amounts, so the reader can
   * tell what a bar's height is worth without reading its label.
   *
   * The amounts come from the project's own magnitude — a project topping out
   * in millions gets lines in millions, one topping out in billions gets lines
   * in billions — and they are round numbers rather than equal divisions of the
   * largest bar, which is what makes them readable.
   *
   * Nothing already on the chart moves: the guide draws into the strip that was
   * already reserved on the inline-start edge and into the empty space behind
   * the bars, and its top line never rises above the tallest bar, so no column
   * is rescaled.
   */
  const largestIrr = entries.reduce((largest, entry) => {
    const value = /^-?\d+$/.test(String(entry.value ?? "")) ? BigInt(entry.value) : 0n;
    const magnitude = value < 0n ? -value : value;
    return magnitude > largest ? magnitude : largest;
  }, 0n);
  const ticks = buildValueTicks(largestIrr);
  const tickScale = ticks.length ? compactMoneyScale(largestIrr.toString()) : null;

  if (tickScale) {
    const guide = element("div", "managerial-combo-chart__scale");
    guide.setAttribute("aria-hidden", "true");
    guide.append(element("span", "managerial-combo-chart__scale-unit", tickScale.unit));
    ticks.forEach((tick) => {
      const row = element("div", "managerial-combo-chart__scale-row");
      row.style.setProperty("--scale-size", `${tick.magnitude}%`);
      row.append(element("span", "managerial-combo-chart__scale-value", tickScale.format(tick.valueIrr) ?? ""));
      guide.append(row);
    });
    barsBand.append(guide);
  }

  // The line marks the top of the initial-estimate bar, drawn from the same
  // percentage of the same band the bar itself is drawn from — so it follows
  // the bar through every resize and every value change, unmeasured.
  const baseline = document.createElement("div");
  baseline.className = "managerial-combo-chart__baseline";
  baseline.setAttribute("aria-hidden", "true");
  const baselineLabel = document.createElement("div");
  baselineLabel.className = "managerial-combo-chart__reference";
  // Two deliberate lines: the chip is narrow so it can stand clear of the bars,
  // and letting the text find its own break would put it wherever it landed.
  baselineLabel.append(element("span", "", "خط مرجع"), element("strong", "", "برآورد اولیه"));
  baseline.append(baselineLabel);

  const initialEntry = entries.find((entry) => entry.key === "initial");
  if (initialEntry?.value != null) {
    barsBand.style.setProperty("--baseline-size", `${initialEntry.magnitude}%`);
    barsBand.append(baseline);
  }

  plot.append(valuesBand, barsBand, labelsBand);
  chart.append(plot);
  // forecastFinalCostIrr is nullable in LiveMetrics: null means the Backend
  // could not compute it. Reading that as zero would subtract the whole initial
  // estimate and announce a saving the project has not made, so an
  // uncomputable side is reported as uncomputable instead of being counted.
  const exact = (value) => (/^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null);
  const initial = exact(metrics.initialEstimateIrr);
  const forecast = exact(metrics.forecastFinalCostIrr);
  const deviation = initial === null || forecast === null ? null : forecast - initial;
  const tone = deviation === null ? "unknown" : deviation > 0n ? "increase" : deviation < 0n ? "decrease" : "stable";
  const label = deviation === null
    ? "قابل محاسبه نیست"
    : deviation > 0n ? "بیشتر از برآورد اولیه" : deviation < 0n ? "کمتر از برآورد اولیه" : "برابر با برآورد اولیه";
  const summary = document.createElement("div");
  summary.className = `managerial-deviation managerial-deviation--${tone}`;
  const title = document.createElement("span");
  title.textContent = "انحراف پیش‌بینی نهایی";
  const value = document.createElement("strong");
  value.className = "numeric";
  value.textContent = deviation === null || deviation === 0n
    ? label
    : `${formatCompactMoneyFromIrr((deviation < 0n ? -deviation : deviation).toString())} ${label}`;
  if (deviation !== null && deviation !== 0n) value.title = formatTomanFromIrr((deviation < 0n ? -deviation : deviation).toString());
  if (deviation === null) value.title = "پیش‌بینی هزینه نهایی یا برآورد اولیه در این گزارش محاسبه نشده است.";
  summary.append(title, value);

  const managerialPanel = element("div", "analysis-chart-panel");
  managerialPanel.dataset.chart = "managerial";
  managerialPanel.append(chart, summary);
  section.append(heading, managerialPanel);

  if (!monthly) return section;

  section.append(monthly.panel);
  const panels = { managerial: managerialPanel, monthly: monthly.panel };
  const buttons = {};

  function activate(key) {
    Object.entries(panels).forEach(([name, node]) => {
      node.hidden = name !== key;
    });
    Object.entries(buttons).forEach(([name, button]) => {
      button.setAttribute("aria-pressed", String(name === key));
      button.className = `button button--small ${name === key ? "button--primary" : "button--ghost"}`;
    });
    headingTitle.textContent = ANALYSIS_CHARTS[key].title;
    headingDescription.textContent = key === "monthly" ? monthly.description : ANALYSIS_CHARTS[key].description;
    // The monthly chart measures zero while its panel is hidden, so it is
    // redrawn once the panel actually has a width.
    if (key === "monthly") monthly.chart?.resize();
  }

  const switcher = element("div", "analysis-chart-switch");
  switcher.setAttribute("role", "group");
  switcher.setAttribute("aria-label", "انتخاب نمودار هزینه");
  Object.entries(ANALYSIS_CHARTS).forEach(([key, meta]) => {
    const button = element("button", "button button--small button--ghost", meta.label);
    button.type = "button";
    button.dataset.chart = key;
    button.addEventListener("click", () => {
      activate(key);
      onChartChange(key);
    });
    buttons[key] = button;
    switcher.append(button);
  });
  heading.append(switcher);
  // Honour the page's remembered choice: switching the monthly mode repaints
  // the whole overview, and defaulting here would throw the reader back to the
  // managerial chart every time they changed it.
  activate(panels[activeChart] ? activeChart : "managerial");
  return section;
}

function createSupplementarySummary(metrics) {
  const section = document.createElement("aside");
  section.className = "finance-supplementary-summary";
  section.setAttribute("aria-label", "اطلاعات تکمیلی وضعیت مالی");
  const heading = document.createElement("div");
  heading.className = "finance-supplementary-summary__heading";
  const eyebrow = document.createElement("span");
  eyebrow.textContent = "شاخص‌های مکمل";
  const title = document.createElement("h2");
  title.textContent = "اطلاعات تکمیلی";
  const description = document.createElement("p");
  description.textContent = "جزئیات مؤثر برای تفسیر تصویر مالی پروژه";
  heading.append(eyebrow, title, description);
  const list = document.createElement("div");
  list.className = "finance-supplementary-summary__list";
  SUMMARY_ITEMS
    .filter(([key]) => SUPPLEMENTARY_SUMMARY_KEYS.has(key))
    .forEach(([key, label, detail]) => {
      const item = createSummaryCard(key, label, detail, metrics);
      item.classList.add("summary-card--compact");
      list.append(item);
    });
  section.append(heading, list);
  return section;
}

function createVariancePanel(title, rows, valueKey, valueFormatter, baseHref) {
  const section = document.createElement("section");
  section.className = "finance-analysis-card finance-variance-card";
  const heading = document.createElement("h2");
  heading.textContent = title;
  section.append(heading);
  if (!rows?.length) {
    const empty = document.createElement("p");
    empty.className = "finance-analysis-card__empty";
    empty.textContent = "برای این تحلیل هنوز داده معتبری ثبت نشده است.";
    section.append(empty);
    return section;
  }
  const list = document.createElement("ol");
  rows.slice(0, 5).forEach((row) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.className = "finance-variance-card__link";
    const target = new URLSearchParams();
    if (row.resourceId) target.set("resourceId", row.resourceId);
    if (row.estimateLineId) target.set("estimateLineId", row.estimateLineId);
    link.href = `${baseHref}${target.size ? `?${target.toString()}` : ""}`;
    link.setAttribute("aria-label", `${row.resourceTitle || row.resourceCode || "قلم هزینه بدون عنوان"}؛ مشاهده جزئیات ${title}`);
    const identity = document.createElement("span");
    identity.textContent = row.resourceTitle || row.resourceCode || "قلم هزینه بدون عنوان";
    const value = document.createElement("strong");
    value.className = "numeric";
    value.textContent = valueFormatter(row[valueKey]);
    const indicator = document.createElement("span");
    indicator.className = "finance-variance-card__indicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.textContent = "‹";
    link.append(identity, value, indicator);
    item.append(link);
    list.append(item);
  });
  section.append(list);
  return section;
}

const SNAPSHOT_STATUS_LABELS = Object.freeze({
  ready: "آماده",
  superseded: "جایگزین‌شده",
});

/**
 * Which progress snapshot these figures were computed from.
 *
 * Five of the eight headline metrics are derived from the executed quantity the
 * progress feed reports — the day value of work done, the remaining physical
 * cost, the money required to continue, the final forecast and the forecast per
 * square metre. Change the snapshot and those five change with it, so a reader
 * who cannot see which snapshot was used cannot defend the numbers.
 *
 * The selector re-asks the Backend rather than recomputing anything here: the
 * report endpoints accept a progressSnapshotId and rebuild the whole picture
 * against it. No finance arithmetic happens in this file.
 */
function createSnapshotProvenance({ snapshots = [], selected, report, onSelect }) {
  if (!selected) return null;
  const section = element("section", "finance-snapshot-provenance");
  section.setAttribute("aria-label", "نسخه پیشرفت مبنای این محاسبه");
  section.append(element("span", "finance-snapshot-provenance__lead", "مبنای محاسبه"));

  /**
   * The strip stays on one line at every width, so each fact carries a short
   * label as well as a full one — the same long/narrow pairing the combination
   * chart uses for its category names — and the facts drop out in order of how
   * little they say as the room runs out. The file name is the only value with
   * no natural length, so it is the one that gives way with an ellipsis.
   */
  const facts = element("dl", "finance-snapshot-provenance__facts");
  [
    ["date", "تاریخ گزارش نسخه", "تاریخ", formatBusinessDate(selected.reportingDate)],
    ["status", "وضعیت", "وضعیت", SNAPSHOT_STATUS_LABELS[selected.status] ?? "نامشخص"],
    ["file", "فایل مبدأ", "فایل", selected.sourceFileNameSafe ?? "—"],
    ["imported", "ورود به سیستم", "ورود", formatSystemDateTime(selected.importedAt)],
  ].forEach(([key, label, shortLabel, value]) => {
    const item = element("div", `finance-snapshot-provenance__fact finance-snapshot-provenance__fact--${key}`);
    const term = element("dt");
    term.append(
      element("span", "finance-snapshot-provenance__label--full", label),
      element("span", "finance-snapshot-provenance__label--short", shortLabel),
    );
    const definition = element("dd", "", value);
    // Truncation hides characters, so the whole value stays reachable.
    definition.title = value;
    item.append(term, definition);
    facts.append(item);
  });
  section.append(facts);

  // Only a ready snapshot can be reported on: the report endpoints refuse a
  // superseded one, so it is listed and disabled rather than silently failing.
  const selectable = snapshots.filter((snapshot) => snapshot.status === "ready");
  if (selectable.length > 1 && typeof onSelect === "function") {
    const picker = document.createElement("select");
    picker.className = "app-select finance-snapshot-provenance__picker";
    picker.setAttribute("aria-label", "انتخاب نسخه پیشرفت مبنای محاسبه");
    picker.title = "با تغییر نسخه، محاسبه از سمت سرویس مالی دوباره انجام می‌شود.";
    snapshots.forEach((snapshot) => {
      const option = document.createElement("option");
      option.value = snapshot.progressSnapshotId;
      const status = snapshot.status === "ready" ? "" : ` · ${SNAPSHOT_STATUS_LABELS[snapshot.status] ?? "نامشخص"}`;
      option.textContent = `${formatBusinessDate(snapshot.reportingDate)}${status}`;
      option.disabled = snapshot.status !== "ready";
      option.selected = snapshot.progressSnapshotId === selected.progressSnapshotId;
      picker.append(option);
    });
    picker.addEventListener("change", () => onSelect(picker.value));
    section.append(picker);
  }

  // The response states which snapshot it actually used. If that is not the one
  // we asked for, the reader is told — below the strip rather than inside it,
  // so the strip keeps its single line and the warning still gets said.
  const answered = report?.progressSnapshotId;
  if (!answered || answered === selected.progressSnapshotId) return section;

  const notice = element("p", "inline-notice finance-snapshot-provenance__notice", "سرویس مالی این ارقام را بر پایه نسخه دیگری محاسبه کرده است؛ نسخه انتخابی برای این تاریخ گزارش قابل استفاده نبود.");
  notice.setAttribute("role", "status");
  const group = document.createDocumentFragment();
  group.append(section, notice);
  return group;
}

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

/**
 * A gear, built node by node the way the price sparkline is.
 *
 * There is no icon set in this project, so the shape is drawn here: a hub, a
 * body, and eight teeth placed by rotation. Everything strokes in
 * `currentColor`, so the link's own hover and focus colours carry the icon with
 * them and no second palette appears.
 */
function createSettingsIcon() {
  const icon = document.createElementNS(SVG_NAMESPACE, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("focusable", "false");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("fill", "none");
  icon.setAttribute("stroke", "currentColor");
  icon.setAttribute("stroke-width", "1.7");
  icon.setAttribute("stroke-linecap", "round");
  icon.classList.add("finance-project-settings-link__icon");

  // Each tooth starts just inside the body so the two read as one shape rather
  // than as spokes around a hub, and squares off at the tip the way a tooth does.
  const teeth = document.createElementNS(SVG_NAMESPACE, "g");
  teeth.setAttribute("stroke-width", "2.4");
  teeth.setAttribute("stroke-linecap", "butt");
  for (let index = 0; index < 8; index += 1) {
    const tooth = document.createElementNS(SVG_NAMESPACE, "line");
    tooth.setAttribute("x1", "12");
    tooth.setAttribute("y1", "3.9");
    tooth.setAttribute("x2", "12");
    tooth.setAttribute("y2", "6.8");
    tooth.setAttribute("transform", `rotate(${index * 45} 12 12)`);
    teeth.append(tooth);
  }

  const body = document.createElementNS(SVG_NAMESPACE, "circle");
  body.setAttribute("cx", "12");
  body.setAttribute("cy", "12");
  body.setAttribute("r", "5.9");
  body.setAttribute("stroke-width", "2.2");

  const hub = document.createElementNS(SVG_NAMESPACE, "circle");
  hub.setAttribute("cx", "12");
  hub.setAttribute("cy", "12");
  hub.setAttribute("r", "2.5");

  icon.append(teeth, body, hub);
  return icon;
}

function createSettingsLink() {
  const link = document.createElement("a");
  link.className = "finance-project-settings-link";
  link.href = "#/settings";
  // The icon carries no text, so the name has to be spoken here — and shown on
  // hover, since a lone gear is only conventional, never self-explanatory.
  link.setAttribute("aria-label", "تنظیمات مالی پروژه");
  link.title = "تنظیمات مالی پروژه";
  link.append(createSettingsIcon());
  return link;
}

function renderFinanceHome(data, monthly = null, chartState = {}, provenance = null) {
  const fragment = document.createDocumentFragment();
  const pageHeader = document.createElement("header");
  pageHeader.className = "finance-page-header";
  const pageTitle = document.createElement("h1");
  pageTitle.className = "finance-page-title";
  pageTitle.textContent = "نمای کلی مالی";
  pageHeader.append(pageTitle);

  const summaryHeader = document.createElement("div");
  summaryHeader.className = "section-heading";
  const summaryHeading = document.createElement("div");
  const summaryEyebrow = document.createElement("span");
  summaryEyebrow.textContent = "وضعیت مالی پروژه";
  const summaryTitle = document.createElement("h2");
  summaryTitle.textContent = "شاخص‌های اصلی در یک نگاه";
  summaryHeading.append(summaryEyebrow, summaryTitle);
  const reportMeta = document.createElement("small");
  reportMeta.className = "finance-report-meta";
  reportMeta.textContent = `تاریخ گزارش ${formatBusinessDate(data.reportingDate)} · نسخه پیشرفت پروژه`;
  // The heading sits at one end of the row and these at the other, which is
  // what .section-heading's own space-between already arranges.
  const summaryTrailing = element("div", "section-heading__trailing");
  summaryTrailing.append(reportMeta, createSettingsLink());
  summaryHeader.append(summaryHeading, summaryTrailing);
  const comparisons = buildOverviewComparisons(data.metrics);
  const overviewPanel = document.createElement("section");
  overviewPanel.className = "finance-overview-panel";
  const overviewLayout = document.createElement("div");
  overviewLayout.className = "finance-overview-layout";
  overviewLayout.append(
    createManagerialComparisonPanel(data.metrics, comparisons.management, monthly, chartState),
    createSupplementarySummary(data.metrics),
  );
  overviewPanel.append(summaryHeader, overviewLayout);

  const warnings = document.createElement("section");
  warnings.className = "finance-warnings";
  warnings.setAttribute("aria-label", "هشدارهای محاسبات مالی");
  const reportWarnings = [...(data.warnings ?? [])];
  if (data.calculationStatus === "incomplete") {
    reportWarnings.unshift({
      code: "CALCULATION_INCOMPLETE",
      message: `محاسبات مالی کامل نیست؛ ${formatDisplayNumber(data.missingPriceCount ?? 0)} قیمت و ${formatDisplayNumber(data.excludedEstimateLineCount ?? 0)} ردیف برآورد در محاسبه نهایی لحاظ نشده است.`,
    });
  }
  if (reportWarnings.length) {
    const warningTitle = document.createElement("h2");
    warningTitle.textContent = "هشدارهای کیفیت محاسبه";
    const list = document.createElement("ul");
    reportWarnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = reportWarningText(warning);
      list.append(item);
    });
    warnings.append(warningTitle, list);
  } else {
    warnings.classList.add("finance-warnings--clear");
    warnings.textContent = "برای محاسبات زنده فعلی هشداری ثبت نشده است.";
  }

  const breakdownRows = buildBreakdownPresentation(data.breakdown);
  const breakdown = breakdownRows.length ? createBreakdownChart(breakdownRows) : document.createDocumentFragment();
  const insights = document.createElement("section");
  insights.className = "finance-insights";
  insights.setAttribute("aria-label", "تحلیل و هشدارهای مالی");
  const riskStack = document.createElement("div");
  riskStack.className = "finance-risk-stack";
  riskStack.append(
    warnings,
    createVariancePanel("بیشترین انحراف قیمت", data.topPriceVariances, "varianceIrr", formatCompactMoneyFromIrr, "#/prices"),
    createVariancePanel("بیشترین انحراف مقدار", data.topQuantityVariances, "varianceQuantity", formatDisplayNumber, "#/financial-items"),
  );
  insights.append(breakdown, riskStack);

  const areasHeader = document.createElement("div");
  areasHeader.className = "section-heading";
  const areasHeading = document.createElement("div");
  areasHeading.append(element("span", "", "فضای کاری"), element("h2", "", "عملیات مالی پروژه"));
  areasHeader.append(areasHeading);
  const areas = document.createElement("section");
  areas.className = "work-area-grid";
  areas.setAttribute("aria-label", "بخش‌های امور مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  if (provenance) fragment.append(pageHeader, provenance, overviewPanel, insights, areasHeader, areas);
  else fragment.append(pageHeader, overviewPanel, insights, areasHeader, areas);
  return fragment;
}

const DIRECTION_LABELS = Object.freeze({
  over: "بیشتر از برآورد",
  under: "کمتر از برآورد",
  onTarget: "برابر برآورد",
});

function trendTooltip(point) {
  const panel = element("div", "combo-chart__tooltip-body");
  panel.append(element("strong", "combo-chart__tooltip-title", point.fullLabel));
  const rows = element("dl", "combo-chart__tooltip-rows");
  const addRow = (label, value, valueClass = "numeric") => {
    const row = element("div");
    row.append(element("dt", "", label), element("dd", valueClass, value));
    rows.append(row);
  };
  addRow("برآورد", point.estimateIrr === null ? "ثبت نشده" : formatCompactMoneyFromIrr(point.estimateIrr));
  addRow("هزینه واقعی", formatCompactMoneyFromIrr(point.actualIrr));
  if (point.deviationIrr !== null) {
    const percent = point.deviationPercent === null ? "" : ` · ${formatDisplayNumber(point.deviationPercent)}٪`;
    addRow("انحراف", `${formatCompactMoneyFromIrr(point.deviationIrr)}${percent}`, `numeric combo-chart__deviation combo-chart__deviation--${point.direction}`);
    addRow("وضعیت", DIRECTION_LABELS[point.direction] ?? "—", "");
  }
  panel.append(rows);
  return panel;
}

function trendTable(view) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table monthly-trend-table");
  table.append(
    tableCaption("جدول جایگزین نمودار روند ماهانه هزینه"),
    tableHead(["ماه", "برآورد", "هزینه واقعی", "انحراف"]),
  );
  const body = document.createElement("tbody");
  view.points.forEach((point) => {
    const row = document.createElement("tr");
    const deviation = point.deviationIrr === null
      ? "—"
      : `${formatCompactMoneyFromIrr(point.deviationIrr)}${point.deviationPercent === null ? "" : ` · ${formatDisplayNumber(point.deviationPercent)}٪`}`;
    row.append(
      element("td", "", point.fullLabel),
      element("td", "numeric", point.estimateIrr === null ? "ثبت نشده" : formatCompactMoneyFromIrr(point.estimateIrr)),
      element("td", "numeric", formatCompactMoneyFromIrr(point.actualIrr)),
      element("td", "numeric", deviation),
    );
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function trendLegend() {
  const legend = element("ul", "breakdown-legend monthly-trend-legend");
  [["actual", "هزینه واقعی ثبت‌شده"], ["initial", "برآورد ماهانه"]].forEach(([series, label]) => {
    const item = element("li", "", label);
    item.dataset.series = series;
    legend.append(item);
  });
  return legend;
}

/**
 * Builds the monthly trend as a panel inside the managerial card, and hands the
 * chart instance back with it so the page disposes exactly one instance per
 * render instead of leaving a ResizeObserver behind.
 *
 * Each month stands alone here; the card's switch is what contrasts this with
 * the cumulative managerial picture, so the panel carries no mode control.
 */
function createMonthlyTrendPanel({ trend, trendError }) {
  const panel = element("div", "analysis-chart-panel finance-monthly-trend");
  panel.dataset.chart = "monthly";
  const description = ANALYSIS_CHARTS.monthly.description;

  if (trendError) {
    panel.append(element("p", "inline-notice", formatApiErrorMessage(trendError, "دریافت روند ماهانه هزینه انجام نشد.")));
    return { panel, chart: null, description };
  }

  const view = buildMonthlyTrend({ months: trend?.months ?? [], mode: TREND_MODES.PERIODIC });
  if (view.isEmpty) {
    const reason = trend?.unavailableReason ?? "هنوز فاکتور تأییدشده‌ای برای ساخت روند ماهانه ثبت نشده است.";
    panel.append(element("p", "inline-notice", reason));
    return { panel, chart: null, description };
  }

  // TEMPORARY: remove with monthly-trend-preview.js. Placeholder money on a
  // finance screen is indistinguishable from real money once it is drawn, so it
  // says what it is, above the chart, every time.
  if (trend?.estimateSource === "preview") {
    const warning = element("p", "inline-notice monthly-trend-preview-notice");
    warning.setAttribute("role", "status");
    warning.append(
      element("strong", "", "داده نمایشی"),
      document.createTextNode(` ${trend.previewNotice ?? "این نمودار با داده آزمایشی رسم شده است."}`),
    );
    panel.append(warning);
  }

  const axisScale = compactMoneyScale(view.maximumIrr);
  panel.append(trendLegend());
  const chart = createCombinationChart({
    barSeries: { magnitudeKey: "actualMagnitude" },
    lineSeries: { magnitudeKey: "estimateMagnitude" },
    formatValue: (value) => axisScale?.format(value) ?? "",
    renderTooltip: trendTooltip,
    ariaLabel: "نمودار ستونی هزینه واقعی و خط برآورد ماهانه",
  });
  chart.setData({ points: view.points, ticks: view.axisTicks });
  panel.append(chart.element);

  if (!view.hasEstimate) {
    panel.append(element("p", "inline-notice", "برآورد ماهانه در دسترس نیست و فقط هزینه واقعی ثبت‌شده رسم شده است."));
  } else if (view.estimatePartial) {
    panel.append(element("p", "inline-notice", "برای بخشی از ماه‌ها برآورد ثبت نشده و خط برآورد در آن بازه‌ها پیوسته نیست."));
  }
  panel.append(trendTable(view));
  return {
    panel,
    chart,
    description: axisScale ? `${description} ارقام محور بر حسب ${axisScale.unit} است.` : description,
  };
}

export function createFinanceHomePage({ reportsAdapter, progressAdapter }) {
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let trend = null;
  let trendError = null;
  let activeChart = "managerial";
  let chart = null;
  let snapshots = [];
  let selectedSnapshotId = null;
  const root = document.createElement("div");
  root.className = "finance-home-page";

  function disposeChart() {
    chart?.destroy();
    chart = null;
  }

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      snapshots = await progressAdapter.getSnapshots();
      // Only a ready snapshot can be reported on. Defaulting to snapshots[0]
      // would ask the Backend for a superseded one and be answered with a 404.
      const reportable = snapshots.filter((snapshot) => snapshot.status === "ready");
      if (!reportable.length) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
      } else {
        const latest = reportable.find((snapshot) => snapshot.progressSnapshotId === selectedSnapshotId) ?? reportable[0];
        selectedSnapshotId = latest.progressSnapshotId;
        // The trend is independent of the overview: a failure there must not
        // take the eight headline metrics down with it.
        const [report, monthly] = await Promise.all([
          reportsAdapter.getOverview({ reportingDate: latest.reportingDate, progressSnapshotId: latest.progressSnapshotId }),
          reportsAdapter.getMonthlyTrend({ reportingDate: latest.reportingDate }).then(
            (value) => { trendError = null; return value; },
            (error) => { trendError = error; return null; },
          ),
        ]);
        trend = monthly;
        state = report ? createRequestState(REQUEST_STATUS.SUCCESS, report) : createRequestState(REQUEST_STATUS.EMPTY);
      }
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function setActiveChart(nextChart) {
    activeChart = nextChart;
  }

  function selectSnapshot(nextSnapshotId) {
    if (!nextSnapshotId || nextSnapshotId === selectedSnapshotId) return;
    selectedSnapshotId = nextSnapshotId;
    load();
  }

  function renderEmpty() {
    const card = document.createElement("section");
    card.className = "state-card";
    const title = document.createElement("h1");
    title.textContent = "خلاصه مالی هنوز قابل محاسبه نیست";
    const message = document.createElement("p");
    message.textContent = "برای محاسبه شاخص‌های مالی، حداقل یک نسخه پیشرفت پروژه لازم است.";
    const link = document.createElement("a");
    link.className = "button button--primary";
    link.href = "#/progress";
    link.textContent = "مشاهده نسخه‌های پیشرفت";
    card.append(title, message, link);
    return card;
  }

  function paint() {
    disposeChart();
    const renderContent = (data) => {
      const built = createMonthlyTrendPanel({ trend, trendError });
      chart = built.chart;
      const provenance = createSnapshotProvenance({
        snapshots,
        selected: snapshots.find((snapshot) => snapshot.progressSnapshotId === selectedSnapshotId) ?? null,
        report: data,
        onSelect: selectSnapshot,
      });
      return renderFinanceHome(data, built, { activeChart, onChartChange: setActiveChart }, provenance);
    };
    root.replaceChildren(renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
