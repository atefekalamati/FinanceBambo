import {
  createRequestState,
  REQUEST_STATUS,
} from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import {
  formatBusinessDate,
  formatDisplayNumber,
  formatSystemDateTime,
} from "../../shared/formatters/display.js";
import {
  compactMoneyFromIrr,
  compactMoneyScale,
  formatCompactMoneyFromIrr,
  formatTomanFromIrr,
  irrToDisplayValue,
} from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { reportWarningText } from "../../shared/warnings/finance-warning-labels.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { createCombinationChart } from "../../shared/components/combination-chart.js";
import { createCostCurveChart } from "../../shared/components/cost-curve-chart.js";
import { buildCostCurve } from "../../shared/charts/cost-curve.js";
import {
  buildMonthlyTrend,
  TREND_MODES,
} from "../../shared/reports/monthly-trend.js";
import { buildValueTicks } from "../../shared/charts/value-ticks.js";
import { buildOverviewComparisons } from "../../shared/reports/report-presentation.js";
import { createBreakdownChart } from "../../shared/components/breakdown-chart.js";
import { createTomanDisplay } from "../../shared/components/money-display.js";
import { SURFACES, homeRouteFor } from "../../core/config/routes.js";
import { canAccessSurface } from "../../core/auth/permissions.js";
import { createReportBuilderSection } from "../report-builder/report-builder-section.js";
import { reportIcon } from "../report-builder/report-icons.js";
import { createLevelOneSection } from "../level-one/level-one-section.js";
import { createPricesSummary } from "./prices-summary.js";
import { createInvoicesEntry } from "./invoices-entry.js";

/* The four the board shows, in the order it shows them. The rest of the
   catalogue is still what the report page and the builder draw on. */
const BOARD_FIGURE_KEYS = Object.freeze([
  "initialEstimateIrr",
  "actualCostIrr",
  "remainingPhysicalCostIrr",
  "actualCostPerSquareMeterIrr",
]);

const SUMMARY_ITEMS = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه", "مبنای اولیه برآورد پروژه"],
  ["actualCostIrr", "هزینه واقعی ثبت‌شده", "فقط اسناد مالی تأییدشده"],
  [
    "actualCostPerSquareMeterIrr",
    "هزینه واقعی هر مترمربع",
    "براساس زیربنای کل پروژه",
  ],
  [
    "currentExecutedValueIrr",
    "ارزش روز کار انجام‌شده",
    "مقدار اجراشده با قیمت روز",
  ],
  [
    "remainingPhysicalCostIrr",
    "هزینه کار باقی‌مانده",
    "کار باقیمانده با قیمت روز",
  ],
  [
    "forecastFinalCostIrr",
    "پیش‌بینی هزینه نهایی",
    "هزینه واقعی به‌اضافه پول ادامه",
  ],
  [
    "forecastPerSquareMeterIrr",
    "پیش‌بینی هزینه هر مترمربع",
    "پیش‌بینی نهایی تقسیم بر زیربنا",
  ],
  [
    "moneyRequiredToContinueIrr",
    "بودجه موردنیاز تا تکمیل",
    "با لحاظ خرید ثبت‌شده مصالح",
  ],
]);

const PRIMARY_SUMMARY_KEYS = new Set([
  "initialEstimateIrr",
  "actualCostIrr",
  "remainingPhysicalCostIrr",
  "forecastFinalCostIrr",
]);
const RELATED_SUMMARY_KEYS = new Set([
  "actualCostPerSquareMeterIrr",
  "forecastPerSquareMeterIrr",
]);

/* The destinations of the گزارش مالی surface, in the order a reader wants them:
   the current report, the same report over a chosen period, the documents the
   figures are built from, and how the amounts are displayed. */

function createSummaryCard(key, label, description, data) {
  const card = document.createElement("article");
  const unavailable = data?.[key] === null || data?.[key] === undefined;
  const hierarchy = PRIMARY_SUMMARY_KEYS.has(key)
    ? "primary"
    : RELATED_SUMMARY_KEYS.has(key)
      ? "primary"
      : "support";
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

const ANALYSIS_CHARTS = Object.freeze({
  managerial: {
    label: "تجمیعی",
    title: "تصویر مدیریتی هزینه پروژه",
    description: "مقایسه هزینه‌های پروژه با خط مرجع برآورد اولیه",
  },
  monthly: {
    label: "روند ماهانه",
    title: "روند ماهانه هزینه پروژه",
    description: "هزینه واقعی هر ماه در برابر برآورد همان ماه",
  },
});

/**
 * Holds both cost charts and shows exactly one at a time. The managerial
 * comparison is the default; the monthly trend is revealed by the switch in
 * this card's heading.
 */
function createManagerialComparisonPanel(
  metrics,
  entries,
  monthly = null,
  { activeChart = "managerial", onChartChange = () => {} } = {},
) {
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
  chart.setAttribute(
    "aria-label",
    "مقایسه برآورد اولیه، هزینه واقعی، هزینه باقی‌مانده و پیش‌بینی نهایی",
  );
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
  valuesBand.className =
    "managerial-combo-chart__band managerial-combo-chart__band--values";
  const barsBand = document.createElement("div");
  barsBand.className =
    "managerial-combo-chart__band managerial-combo-chart__band--bars";
  const labelsBand = document.createElement("div");
  labelsBand.className =
    "managerial-combo-chart__band managerial-combo-chart__band--labels";

  entries.forEach((entry) => {
    // Each cell is its own inline-size container, which is what lets the money
    // inside it size itself against the width of its own column.
    const valueCell = document.createElement("div");
    valueCell.className =
      "managerial-combo-chart__cell managerial-combo-chart__cell--value";
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
    const value = /^-?\d+$/.test(String(entry.value ?? ""))
      ? BigInt(entry.value)
      : 0n;
    const magnitude = value < 0n ? -value : value;
    return magnitude > largest ? magnitude : largest;
  }, 0n);
  const ticks = buildValueTicks(largestIrr);
  const tickScale = ticks.length
    ? compactMoneyScale(largestIrr.toString())
    : null;

  if (tickScale) {
    const guide = element("div", "managerial-combo-chart__scale");
    guide.setAttribute("aria-hidden", "true");
    guide.append(
      element("span", "managerial-combo-chart__scale-unit", tickScale.unit),
    );
    ticks.forEach((tick) => {
      const row = element("div", "managerial-combo-chart__scale-row");
      row.style.setProperty("--scale-size", `${tick.magnitude}%`);
      row.append(
        element(
          "span",
          "managerial-combo-chart__scale-value",
          tickScale.format(tick.valueIrr) ?? "",
        ),
      );
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
  baselineLabel.append(
    element("span", "", "خط مرجع"),
    element("strong", "", "برآورد اولیه"),
  );
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
  const exact = (value) =>
    /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
  const initial = exact(metrics.initialEstimateIrr);
  const forecast = exact(metrics.forecastFinalCostIrr);
  const deviation =
    initial === null || forecast === null ? null : forecast - initial;
  const tone =
    deviation === null
      ? "unknown"
      : deviation > 0n
        ? "increase"
        : deviation < 0n
          ? "decrease"
          : "stable";
  const label =
    deviation === null
      ? "قابل محاسبه نیست"
      : deviation > 0n
        ? "بیشتر از برآورد اولیه"
        : deviation < 0n
          ? "کمتر از برآورد اولیه"
          : "برابر با برآورد اولیه";
  const summary = document.createElement("div");
  summary.className = `managerial-deviation managerial-deviation--${tone}`;
  const title = document.createElement("span");
  title.textContent = "انحراف پیش‌بینی نهایی";
  const value = document.createElement("strong");
  value.className = "numeric";
  value.textContent =
    deviation === null || deviation === 0n
      ? label
      : `${formatCompactMoneyFromIrr((deviation < 0n ? -deviation : deviation).toString())} ${label}`;
  if (deviation !== null && deviation !== 0n)
    value.title = formatTomanFromIrr(
      (deviation < 0n ? -deviation : deviation).toString(),
    );
  if (deviation === null)
    value.title =
      "پیش‌بینی هزینه نهایی یا برآورد اولیه در این گزارش محاسبه نشده است.";
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
    headingDescription.textContent =
      key === "monthly"
        ? monthly.description
        : ANALYSIS_CHARTS[key].description;
    // The monthly chart measures zero while its panel is hidden, so it is
    // redrawn once the panel actually has a width.
    if (key === "monthly") monthly.chart?.resize();
  }

  const switcher = element("div", "analysis-chart-switch");
  switcher.setAttribute("role", "group");
  switcher.setAttribute("aria-label", "انتخاب نمودار هزینه");
  Object.entries(ANALYSIS_CHARTS)
    .filter(([key]) => panels[key])
    .forEach(([key, meta]) => {
      const button = element(
        "button",
        "button button--small button--ghost",
        meta.label,
      );
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

const SNAPSHOT_STATUS_LABELS = Object.freeze({
  ready: "آماده",
  superseded: "جایگزین‌شده",
});

/**
 * Where the snapshot came from. The Backend records this rather than letting a
 * filename extension stand in for it, and answers null for rows imported before
 * it started recording — so a missing source is shown as unrecorded, never
 * guessed from the `.mpp` on the end of a name.
 */
const SNAPSHOT_SOURCE_LABELS = Object.freeze({
  microsoft_project: "Microsoft Project",
  primavera: "Primavera",
  manual: "ثبت دستی",
  other: "منبع دیگر",
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
function createSnapshotProvenance({
  snapshots = [],
  selected,
  report,
  onSelect,
}) {
  if (!selected) return null;
  const section = element("section", "finance-snapshot-provenance");
  section.setAttribute("aria-label", "نسخه پیشرفت مبنای این محاسبه");
  section.append(
    element("span", "finance-snapshot-provenance__lead", "مبنای محاسبه"),
  );

  /**
   * The strip stays on one line at every width, so each fact carries a short
   * label as well as a full one — the same long/narrow pairing the combination
   * chart uses for its category names — and the facts drop out in order of how
   * little they say as the room runs out. The file name is the only value with
   * no natural length, so it is the one that gives way with an ellipsis.
   */
  const facts = element("dl", "finance-snapshot-provenance__facts");
  [
    [
      "version",
      "نسخه",
      "نسخه",
      selected.version == null
        ? null
        : `${formatDisplayNumber(String(selected.version))}${selected.isLatest ? " (آخرین)" : ""}`,
    ],
    [
      "date",
      "تاریخ گزارش نسخه",
      "تاریخ",
      formatBusinessDate(selected.reportingDate),
    ],
    [
      "source",
      "منبع",
      "منبع",
      SNAPSHOT_SOURCE_LABELS[selected.sourceType] ??
        (selected.sourceType == null ? null : "منبع تعریف‌نشده"),
    ],
    [
      "status",
      "وضعیت",
      "وضعیت",
      SNAPSHOT_STATUS_LABELS[selected.status] ?? "نامشخص",
    ],
    ["file", "فایل مبدأ", "فایل", selected.sourceFileNameSafe ?? "—"],
    [
      "imported",
      "ورود به سیستم",
      "ورود",
      formatSystemDateTime(selected.importedAt),
    ],
  ]
    .filter(([, , , value]) => value != null)
    .forEach(([key, label, shortLabel, value]) => {
      const item = element(
        "div",
        `finance-snapshot-provenance__fact finance-snapshot-provenance__fact--${key}`,
      );
      const term = element("dt");
      term.append(
        element("span", "finance-snapshot-provenance__label--full", label),
        element(
          "span",
          "finance-snapshot-provenance__label--short",
          shortLabel,
        ),
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
  const selectable = snapshots.filter(
    (snapshot) => snapshot.status === "ready",
  );
  if (selectable.length > 1 && typeof onSelect === "function") {
    const picker = document.createElement("select");
    picker.className = "app-select finance-snapshot-provenance__picker";
    picker.setAttribute("aria-label", "انتخاب نسخه پیشرفت مبنای محاسبه");
    picker.title =
      "با تغییر نسخه، محاسبه از سمت سرویس مالی دوباره انجام می‌شود.";
    snapshots.forEach((snapshot) => {
      const option = document.createElement("option");
      option.value = snapshot.progressSnapshotId;
      const status =
        snapshot.status === "ready"
          ? ""
          : ` · ${SNAPSHOT_STATUS_LABELS[snapshot.status] ?? "نامشخص"}`;
      option.textContent = `${formatBusinessDate(snapshot.reportingDate)}${status}`;
      option.disabled = snapshot.status !== "ready";
      option.selected =
        snapshot.progressSnapshotId === selected.progressSnapshotId;
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

  const notice = element(
    "p",
    "inline-notice finance-snapshot-provenance__notice",
    "سرویس مالی این ارقام را بر پایه نسخه دیگری محاسبه کرده است؛ نسخه انتخابی برای این تاریخ گزارش قابل استفاده نبود.",
  );
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
  // The settings this surface owns are the display ones. The gross built area
  // and the conversion rules change what the figures come out as, and they are
  // authored on امور مالی.
  link.href = "#/report-settings";
  // The icon carries no text, so the name has to be spoken here — and shown on
  // hover, since a lone gear is only conventional, never self-explanatory.
  link.setAttribute("aria-label", "تنظیمات نمایش");
  link.title = "تنظیمات نمایش";
  link.append(createSettingsIcon());
  return link;
}

function renderFinanceHome(
  data,
  monthly = null,
  chartState = {},
  provenance = null,
  cumulative = null,
  levelOne = null,
  prices = null,
) {
  const board = element("div", "finance-board");

  // The board had a full-width header over it carrying the page's name and two
  // buttons. On a page whose whole promise is one screen, a band that says only
  // what the reader already knows is the most expensive thing on it — so the
  // two ways out move down into the basis bar beside the settings gear, as
  // text rather than buttons, and the name stays for anyone who cannot see the
  // page: the document still needs a heading, and a screen reader still reads
  // it first.
  const pageTitle = element("h1", "sr-only", "گزارش مالی پروژه");
  const toAreas = element("a", "finance-basis__link", "بخش‌های گزارش");
  toAreas.href = "#/work-areas";
  const toOperations = element("a", "finance-basis__link", "رفتن به امور مالی");
  toOperations.href = `#${homeRouteFor(SURFACES.OPERATIONS)?.path ?? "/finance"}`;

  const comparisons = buildOverviewComparisons(data.metrics);

  // ── row 0 — the basis of the figures, full width, settings inside it ────
  const basis = element("section", "finance-basis");
  if (provenance) basis.append(provenance);
  const basisMeta = element("div", "finance-basis__meta");
  basisMeta.append(toAreas, toOperations, createSettingsLink());
  basis.append(basisMeta);

  // ── row 1 — the main chart, the day prices, the cost mix ───────────────
  // The four figures a reader opens this page for, then the chart that puts
  // them against the estimate. Reading right to left: figures, then chart.
  const figures = element("section", "finance-figures");
  figures.setAttribute("aria-label", "شاخص‌های اصلی مالی پروژه");
  BOARD_FIGURE_KEYS.forEach((key) => {
    const item = SUMMARY_ITEMS.find(([itemKey]) => itemKey === key);
    if (item)
      figures.append(
        createSummaryCard(item[0], item[1], item[2], data.metrics),
      );
  });

  // The figures and the way into فاکتورها share one half of the row, so the
  // row itself splits at the same place rows two and three do and the gutter
  // reads as one line down the page. Their own split happens a level below it.
  const lead = element("div", "finance-lead");
  lead.append(figures, createInvoicesEntry());

  const rowMain = element("div", "finance-grid finance-grid--main");
  rowMain.append(
    lead,
    createManagerialComparisonPanel(
      data.metrics,
      comparisons.management,
      monthly,
      chartState,
    ),
  );

  // ── row 2 — the phase report beside the report builder ─────────────────
  const builder = createReportBuilderSection({
    onBuild: ({ selection, period }) => {
      const query = new URLSearchParams({ sections: selection.join(",") });
      if (period?.from && period?.to) {
        query.set("from", period.from);
        query.set("to", period.to);
      }
      window.location.hash = `#/report-builder?${query.toString()}`;
    },
  });
  const rowSecond = element("div", "finance-grid finance-grid--pair");
  rowSecond.append(createLevelOneSection(levelOne ?? {}), builder);

  // ── row 3 — the cumulative curve beside the three insight cards ────────
  const rowThird = element("div", "finance-grid finance-grid--insights");
  const curvePanel = element("section", "overview-card finance-curve-card");
  curvePanel.setAttribute("aria-label", "روند تجمعی هزینه پروژه");
  const curveHead = element("header", "overview-card__head");
  curveHead.append(element("h2", "overview-card__title", "روند تجمعی هزینه"));
  curvePanel.append(curveHead);
  if (cumulative?.panel) {
    cumulative.panel.hidden = false;
    curvePanel.append(cumulative.panel);
  }
  const insightCards = element("div", "finance-insight-cards");
  insightCards.append(
    createPricesSummary(prices ?? {}),
    buildWarningsCard(data),
  );
  rowThird.append(curvePanel, insightCards);

  board.append(pageTitle, basis, rowMain, rowSecond, rowThird);
  return board;
}

/**
 * One line of the host's smart summary: a glyph in a tinted disc, then the
 * sentence. Same class names it uses, so the two are one component once this
 * mounts rather than two that happen to agree.
 *
 * Two tones, not the host's three. A report warning arrives with a code and no
 * severity, so every one of them is a warning; `good` is the card with none.
 * Inventing a third tier would be reading a judgement out of data that does not
 * carry one.
 */
function summaryRow(tone, text) {
  const row = element("li", `smrow smrow--${tone}`);
  const mark = element("span", "smrow__icon");
  mark.append(reportIcon(tone === "good" ? "check" : "alert"));
  row.append(mark, element("p", "", text));
  return row;
}

/** هشدارهای کیفیت محاسبه, as one of the three equal insight cards. */
function buildWarningsCard(data) {
  const warnings = document.createElement("section");
  // It sits in a row with the two deviation cards, so it is one of them: the
  // same surface, border, radius, padding and heading come from the class they
  // already share rather than from a second set of rules kept in step by hand.
  warnings.className = "finance-analysis-card finance-warnings";
  warnings.setAttribute("aria-label", "هشدارهای محاسبات مالی");
  const reportWarnings = [...(data.warnings ?? [])];
  if (data.calculationStatus === "incomplete") {
    reportWarnings.unshift({
      code: "CALCULATION_INCOMPLETE",
      message: `محاسبات مالی کامل نیست؛ ${formatDisplayNumber(data.missingPriceCount ?? 0)} قیمت و ${formatDisplayNumber(data.excludedEstimateLineCount ?? 0)} ردیف برآورد در محاسبه نهایی لحاظ نشده است.`,
    });
  }
  const title = document.createElement("h2");
  title.textContent = "هشدارهای کیفیت محاسبه";
  warnings.append(title);
  if (reportWarnings.length) {
    const list = document.createElement("ul");
    reportWarnings.forEach((warning) => {
      list.append(summaryRow("warn", reportWarningText(warning)));
    });
    warnings.append(list);
  } else {
    warnings.classList.add("finance-warnings--clear");
    const list = document.createElement("ul");
    list.append(
      summaryRow("good", "برای محاسبات زنده فعلی هشداری ثبت نشده است."),
    );
    warnings.append(list);
  }
  return warnings;
}

const DIRECTION_LABELS = Object.freeze({
  over: "بیشتر از برآورد",
  under: "کمتر از برآورد",
  onTarget: "برابر برآورد",
});

function trendTooltip(point) {
  const panel = element("div", "combo-chart__tooltip-body");
  panel.append(
    element("strong", "combo-chart__tooltip-title", point.fullLabel),
  );
  const rows = element("dl", "combo-chart__tooltip-rows");
  const addRow = (label, value, valueClass = "numeric") => {
    const row = element("div");
    row.append(element("dt", "", label), element("dd", valueClass, value));
    rows.append(row);
  };
  addRow(
    "برآورد",
    point.estimateIrr === null
      ? "ثبت نشده"
      : formatCompactMoneyFromIrr(point.estimateIrr),
  );
  addRow("هزینه واقعی", formatCompactMoneyFromIrr(point.actualIrr));
  if (point.deviationIrr !== null) {
    const percent =
      point.deviationPercent === null
        ? ""
        : ` · ${formatDisplayNumber(point.deviationPercent)}٪`;
    addRow(
      "انحراف",
      `${formatCompactMoneyFromIrr(point.deviationIrr)}${percent}`,
      `numeric combo-chart__deviation combo-chart__deviation--${point.direction}`,
    );
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
    const deviation =
      point.deviationIrr === null
        ? "—"
        : `${formatCompactMoneyFromIrr(point.deviationIrr)}${point.deviationPercent === null ? "" : ` · ${formatDisplayNumber(point.deviationPercent)}٪`}`;
    row.append(
      element("td", "", point.fullLabel),
      element(
        "td",
        "numeric",
        point.estimateIrr === null
          ? "ثبت نشده"
          : formatCompactMoneyFromIrr(point.estimateIrr),
      ),
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
  [
    ["actual", "هزینه واقعی ثبت‌شده"],
    ["initial", "برآورد ماهانه"],
  ].forEach(([series, label]) => {
    const item = element("li", "", label);
    item.dataset.series = series;
    legend.append(item);
  });
  return legend;
}

/**
 * The cumulative curve: the money twin of the host platform's progress S-curve.
 *
 * Both series are running totals, so each period adds to the one before it and
 * the curve only climbs. The plan comes from the per-period estimates the host's
 * periodic files carry; until those arrive the panel draws the actual alone and
 * says why rather than quietly showing one curve as if it were the comparison.
 */
function createCostCurvePanel({ trend, trendError }) {
  const panel = element("div", "analysis-chart-panel finance-cost-curve");
  panel.dataset.chart = "cumulative";

  if (trendError) {
    panel.append(
      element(
        "p",
        "inline-notice",
        formatApiErrorMessage(trendError, "دریافت روند تجمعی هزینه انجام نشد."),
      ),
    );
    return { panel, chart: null };
  }

  const trendView = buildMonthlyTrend({
    months: trend?.months ?? [],
    mode: TREND_MODES.CUMULATIVE,
  });
  if (trendView.isEmpty) {
    panel.append(
      element(
        "p",
        "inline-notice",
        trend?.unavailableReason ??
          "هنوز فاکتور تأییدشده‌ای برای ساخت روند تجمعی ثبت نشده است.",
      ),
    );
    return { panel, chart: null };
  }

  const view = buildCostCurve({ points: trendView.points });
  const axisScale = compactMoneyScale(view.ceilingIrr);
  panel.append(curveLegend());

  const chart = createCostCurveChart({
    formatValue: (value) => axisScale?.format(value) ?? "",
    formatExactValue: (value) => formatTomanFromIrr(value),
    // Exact, never compacted. The guide's numbers are rounded because they are
    // a ruler; this one is a figure the reader takes away, and "۰٫۱۹ میلیارد"
    // hides everything between ۱۸۵ and ۱۹۴ میلیون behind one rounded digit.
    formatMarker: (value) => formatTomanFromIrr(value),
    unitLabel: axisScale?.unit ?? "",
    ariaLabel: "منحنی تجمعی هزینه واقعی در برابر برآورد تجمعی پروژه",
  });
  chart.setData(view);
  panel.append(chart.element);

  if (view.hasPlan && view.planPartial) {
    panel.append(
      element(
        "p",
        "inline-notice",
        "برای بخشی از دوره‌ها برآورد ثبت نشده و منحنی برنامه در آن بازه‌ها کامل نیست.",
      ),
    );
  }
  return { panel, chart };
}

/** Green fill for what was spent, dashed blue for what was planned. */
function curveLegend() {
  const legend = element("ul", "breakdown-legend cost-curve-legend");
  [
    ["actual", "واقعی"],
    ["plan", "برنامه (هدف)"],
  ].forEach(([series, label]) => {
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
    panel.append(
      element(
        "p",
        "inline-notice",
        formatApiErrorMessage(
          trendError,
          "دریافت روند ماهانه هزینه انجام نشد.",
        ),
      ),
    );
    return { panel, chart: null, description };
  }

  const view = buildMonthlyTrend({
    months: trend?.months ?? [],
    mode: TREND_MODES.PERIODIC,
  });
  if (view.isEmpty) {
    const reason =
      trend?.unavailableReason ??
      "هنوز فاکتور تأییدشده‌ای برای ساخت روند ماهانه ثبت نشده است.";
    panel.append(element("p", "inline-notice", reason));
    return { panel, chart: null, description };
  }

  const axisScale = compactMoneyScale(view.maximumIrr);
  panel.append(trendLegend());
  const chart = createCombinationChart({
    barSeries: { magnitudeKey: "actualMagnitude" },
    lineSeries: { magnitudeKey: "estimateMagnitude" },
    formatValue: (value) => axisScale?.format(value) ?? "",
    // The axis is compacted to stay readable, so the figure behind each of its
    // numbers is only a hover away rather than only in the table.
    formatExactValue: (value) => formatTomanFromIrr(value),
    renderTooltip: trendTooltip,
    ariaLabel: "نمودار ستونی هزینه واقعی و خط برآورد ماهانه",
  });
  chart.setData({ points: view.points, ticks: view.axisTicks });
  panel.append(chart.element);

  if (!view.hasEstimate) {
    panel.append(
      element(
        "p",
        "inline-notice",
        "برآورد ماهانه در دسترس نیست و فقط هزینه واقعی ثبت‌شده رسم شده است.",
      ),
    );
  } else if (view.estimatePartial) {
    panel.append(
      element(
        "p",
        "inline-notice",
        "برای بخشی از ماه‌ها برآورد ثبت نشده و خط برآورد در آن بازه‌ها پیوسته نیست.",
      ),
    );
  }
  // A bar that is simply absent is indistinguishable from a month with no
  // documents at all, so the one case where that happens says so.
  if (view.hasBelowBaseline) {
    const belowNotice = element(
      "p",
      "inline-notice",
      "در برخی ماه‌ها مجموع اسناد ابطالی از اسناد ثبت‌شده بیشتر است و ستونی رسم نشده؛ مقدار دقیق در جدول همین بخش آمده است.",
    );
    belowNotice.setAttribute("role", "status");
    panel.append(belowNotice);
  }
  panel.append(trendTable(view));
  return {
    panel,
    chart,
    description: axisScale
      ? `${description} ارقام محور بر حسب ${axisScale.unit} است.`
      : description,
  };
}

export function createFinanceHomePage({
  context = null,
  reportsAdapter,
  progressAdapter,
  pricesAdapter,
}) {
  // The deviation rows lead to this surface's own read-only tables now, so the
  // only thing left that crosses into امور مالی is the empty state's shortcut to
  // the progress versions — offered only to an account that may be there.
  const canOperate = canAccessSurface(context, SURFACES.OPERATIONS);
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let trend = null;
  let trendError = null;
  let wbsRollup = null;
  let wbsError = null;
  let priceWorkspace = null;
  let priceError = null;
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
      const reportable = snapshots.filter(
        (snapshot) => snapshot.status === "ready",
      );
      if (!reportable.length) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
      } else {
        const latest =
          reportable.find(
            (snapshot) => snapshot.progressSnapshotId === selectedSnapshotId,
          ) ?? reportable[0];
        selectedSnapshotId = latest.progressSnapshotId;
        // The trend is independent of the overview: a failure there must not
        // take the eight headline metrics down with it.
        const [report, monthly, rollup, workspace] = await Promise.all([
          reportsAdapter.getOverview({
            reportingDate: latest.reportingDate,
            progressSnapshotId: latest.progressSnapshotId,
          }),
          reportsAdapter
            .getMonthlyTrend({ reportingDate: latest.reportingDate })
            .then(
              (value) => {
                trendError = null;
                return value;
              },
              (error) => {
                trendError = error;
                return null;
              },
            ),
          // Independent too: the phase report is not built on the service yet,
          // and its absence must not take the headline metrics down with it.
          reportsAdapter
            .getWbsRollup({
              reportingDate: latest.reportingDate,
              progressSnapshotId: latest.progressSnapshotId,
            })
            .then(
              (value) => {
                wbsError = null;
                return value;
              },
              (error) => {
                wbsError = error;
                return null;
              },
            ),
          // The same workspace #/report-prices reads, through the same adapter.
          // The summary shows three of its rows; it computes nothing of its own.
          pricesAdapter.getPrices().then(
            (value) => {
              priceError = null;
              return value;
            },
            (error) => {
              priceError = error;
              return null;
            },
          ),
        ]);
        trend = monthly;
        wbsRollup = rollup;
        priceWorkspace = workspace;
        state = report
          ? createRequestState(REQUEST_STATUS.SUCCESS, report)
          : createRequestState(REQUEST_STATUS.EMPTY);
      }
    } catch (error) {
      state = createRequestState(
        error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR,
        null,
        error,
      );
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
    message.textContent =
      "برای محاسبه شاخص‌های مالی، حداقل یک نسخه پیشرفت پروژه لازم است. نسخه‌های پیشرفت در سربرگ امور مالی ثبت می‌شوند.";
    card.append(title, message);
    if (canOperate) {
      const link = document.createElement("a");
      link.className = "button button--primary";
      link.href = "#/progress";
      link.textContent = "مشاهده نسخه‌های پیشرفت";
      card.append(link);
    }
    return card;
  }

  function paint() {
    disposeChart();
    const renderContent = (data) => {
      const built = createMonthlyTrendPanel({ trend, trendError });
      const curve = createCostCurvePanel({ trend, trendError });
      const levelOne = { rollup: wbsRollup, error: wbsError };
      const prices = { workspace: priceWorkspace, error: priceError };
      chart = built.chart;
      const provenance = createSnapshotProvenance({
        snapshots,
        selected:
          snapshots.find(
            (snapshot) => snapshot.progressSnapshotId === selectedSnapshotId,
          ) ?? null,
        report: data,
        onSelect: selectSnapshot,
      });
      return renderFinanceHome(
        data,
        built,
        { activeChart, onChartChange: setActiveChart },
        provenance,
        curve,
        levelOne,
        prices,
      );
    };
    root.replaceChildren(
      renderPageState(state, { renderContent, renderEmpty, onRetry: load }),
    );
  }

  load();
  return root;
}
