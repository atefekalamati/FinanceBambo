import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";
import { compactMoneyFromIrr, formatCompactMoneyFromIrr, formatTomanFromIrr, irrToDisplayValue } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
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

const WARNING_LABELS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از مقدار خریداری‌شده تعریف نشده است.",
  PROGRESS_MISSING: "برای یکی از خطوط برآورد، مقدار معتبر پیشرفت موجود نیست.",
  QUANTITY_OVERRUN: "مقدار انجام‌شده یکی از ردیف‌ها از آخرین مقدار برآورد بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و از محاسبات زنده آن خط کنار گذاشته شده است.",
  GENERAL_COST_OVERRUN: "هزینه واقعی ثبت‌شده عمومی پروژه از آخرین برآورد هزینه‌های عمومی بیشتر است.",
  GROSS_AREA_MISSING: "زیربنای کل ثبت نشده؛ شاخص‌های هر مترمربع قابل محاسبه نیستند.",
});

const WORK_AREAS = Object.freeze([
  { key: "financial-items", title: "اقلام و برآورد", description: "مدیریت اقلام پروژه، ریز برآورد و مقدارهای اولیه و اصلاح‌شده", meta: "اقلام · برآورد · اصلاحات", href: "#/financial-items" },
  { key: "prices", title: "قیمت روز و تبدیل واحد", description: "ثبت قیمت پایه سازمان، قیمت اختصاصی پروژه و مشاهده تاریخچه قیمت", meta: "قیمت روز · تاریخچه · واحد", href: "#/prices" },
  { key: "progress", title: "پیشرفت و مقادیر انجام‌شده", description: "مشاهده نسخه پیشرفت پروژه، کیفیت داده و اصلاح دستی مقدار", meta: "نسخه پیشرفت · مقدار انجام‌شده · هشدار", href: "#/progress" },
  { key: "invoices", title: "فاکتورها", description: "مشاهده فهرست، وضعیت، منبع، فروشنده، مبلغ و جزئیات خطوط", meta: "فهرست · جزئیات · وضعیت", href: "#/invoices" },
  { key: "reports", title: "گزارش مالی", description: "مشاهده گزارش به‌روز، ثبت گزارش دوره‌ای و دریافت خروجی", meta: "گزارش به‌روز · گزارش ثبت‌شده · چاپ", href: "#/reports" },
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
      bar.className = `breakdown-chart__bar breakdown-chart__bar--${series}`;
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

function createManagerialComparisonPanel(metrics, entries) {
  const section = document.createElement("section");
  section.className = "finance-analysis-card finance-managerial-comparison";
  const heading = document.createElement("div");
  heading.className = "finance-analysis-card__heading";
  const headingTitle = document.createElement("h2");
  headingTitle.textContent = "تصویر مدیریتی هزینه پروژه";
  const headingDescription = document.createElement("p");
  headingDescription.textContent = "مقایسه هزینه‌های پروژه با خط مرجع برآورد اولیه";
  heading.append(headingTitle, headingDescription);

  const chart = document.createElement("div");
  chart.className = "managerial-combo-chart";
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", "مقایسه برآورد اولیه، هزینه واقعی، هزینه باقی‌مانده و پیش‌بینی نهایی");
  const plot = document.createElement("div");
  plot.className = "managerial-combo-chart__plot";
  const baseline = document.createElement("div");
  baseline.className = "managerial-combo-chart__baseline";
  const baselineLabel = document.createElement("div");
  baselineLabel.className = "managerial-combo-chart__reference";
  const baselineSwatch = document.createElement("span");
  baselineSwatch.setAttribute("aria-hidden", "true");
  const baselineText = document.createElement("strong");
  baselineText.textContent = "خط مرجع برآورد اولیه";
  baselineLabel.append(baselineSwatch, baselineText);
  baseline.append(baselineLabel);
  plot.append(baseline);

  let initialColumn = null;
  entries.forEach((entry) => {
    const item = document.createElement("article");
    item.className = `managerial-combo-chart__item managerial-combo-chart__item--${entry.key}`;
    const column = document.createElement("div");
    column.className = "managerial-combo-chart__column";
    column.style.setProperty("--column-size", `${entry.magnitude}%`);
    if (entry.key === "initial") initialColumn = column;
    const value = createTomanDisplay(entry.value, { compact: true });
    value.classList.add("managerial-combo-chart__value");
    const label = document.createElement("h3");
    label.textContent = entry.label;
    item.append(value, column, label);
    plot.append(item);
  });
  chart.append(plot);
  const syncBaseline = () => {
    if (!initialColumn?.isConnected || !plot.isConnected) return;
    const plotRect = plot.getBoundingClientRect();
    const columnRect = initialColumn.getBoundingClientRect();
    baseline.style.setProperty("--baseline-top", `${columnRect.top - plotRect.top}px`);
  };
  const scheduleBaselineSync = typeof requestAnimationFrame === "function"
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 0);

  scheduleBaselineSync(() => {
    syncBaseline();
    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(syncBaseline);
      observer.observe(plot);
    }
  });
  const initial = /^-?\d+$/.test(String(metrics.initialEstimateIrr ?? "")) ? BigInt(metrics.initialEstimateIrr) : 0n;
  const forecast = /^-?\d+$/.test(String(metrics.forecastFinalCostIrr ?? "")) ? BigInt(metrics.forecastFinalCostIrr) : 0n;
  const deviation = forecast - initial;
  const tone = deviation > 0n ? "increase" : deviation < 0n ? "decrease" : "stable";
  const label = deviation > 0n ? "بیشتر از برآورد اولیه" : deviation < 0n ? "کمتر از برآورد اولیه" : "برابر با برآورد اولیه";
  const summary = document.createElement("div");
  summary.className = `managerial-deviation managerial-deviation--${tone}`;
  const title = document.createElement("span");
  title.textContent = "انحراف پیش‌بینی نهایی";
  const value = document.createElement("strong");
  value.className = "numeric";
  value.textContent = deviation === 0n ? label : `${formatCompactMoneyFromIrr((deviation < 0n ? -deviation : deviation).toString())} ${label}`;
  if (deviation !== 0n) value.title = formatTomanFromIrr((deviation < 0n ? -deviation : deviation).toString());
  summary.append(title, value);
  section.append(heading, chart, summary);
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

function renderFinanceHome(data) {
  const fragment = document.createDocumentFragment();
  const pageHeader = document.createElement("header");
  pageHeader.className = "finance-page-header";
  const pageTitle = document.createElement("h1");
  pageTitle.className = "finance-page-title";
  pageTitle.textContent = "نمای کلی مالی";
  const settingsLink = document.createElement("a");
  settingsLink.className = "finance-project-settings-link";
  settingsLink.href = "#/settings";
  settingsLink.textContent = "تنظیمات مالی پروژه";
  settingsLink.setAttribute("aria-label", "ورود به تنظیمات مالی پروژه جاری");
  pageHeader.append(pageTitle, settingsLink);

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
  summaryHeader.append(summaryHeading, reportMeta);
  const comparisons = buildOverviewComparisons(data.metrics);
  const overviewPanel = document.createElement("section");
  overviewPanel.className = "finance-overview-panel";
  const overviewLayout = document.createElement("div");
  overviewLayout.className = "finance-overview-layout";
  overviewLayout.append(
    createManagerialComparisonPanel(data.metrics, comparisons.management),
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
      item.textContent = WARNING_LABELS[warning.code] ?? warning.message ?? "برای بخشی از محاسبات مالی هشدار ثبت شده است.";
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
  areasHeader.innerHTML = "<div><span>فضای کاری</span><h2>عملیات مالی پروژه</h2></div>";
  const areas = document.createElement("section");
  areas.className = "work-area-grid";
  areas.setAttribute("aria-label", "بخش‌های امور مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  fragment.append(pageHeader, overviewPanel, insights, areasHeader, areas);
  return fragment;
}

export function createFinanceHomePage({ reportsAdapter, progressAdapter }) {
  let state = createRequestState(REQUEST_STATUS.LOADING);
  const root = document.createElement("div");
  root.className = "finance-home-page";

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const snapshots = await progressAdapter.getSnapshots();
      if (!snapshots.length) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
      } else {
        const latest = snapshots[0];
        const report = await reportsAdapter.getOverview({ reportingDate: latest.reportingDate, progressSnapshotId: latest.progressSnapshotId });
        state = report ? createRequestState(REQUEST_STATUS.SUCCESS, report) : createRequestState(REQUEST_STATUS.EMPTY);
      }
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
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
    root.replaceChildren(renderPageState(state, { renderContent: renderFinanceHome, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
