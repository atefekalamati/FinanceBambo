import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { compactMoneyScale, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { PERSIAN_MONTHS } from "../../shared/reports/monthly-trend.js";
import { reportWarningText } from "../../shared/warnings/finance-warning-labels.js";
import { reportComparisonChart, reportFigures, reportTable } from "./report-document.js";

const integer = (value) => /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
const money = (value) => integer(value) === null ? "قابل محاسبه نیست" : formatTomanFromIrr(String(value));
const count = (value) => value == null ? "اعلام نشده" : formatDisplayNumber(String(value));
const note = (text) => element("p", "report-doc__note", text);
const status = (value) => ({ complete: "کامل", incomplete: "ناقص" }[value] ?? "اعلام نشده");

/** Exact window totals, not lifetime costs. Missing periods poison later totals. */
export function buildCumulativeSeries(months = []) {
  let actual = 0n;
  let planned = 0n;
  let previous = null;
  const rows = [...months].sort((a, b) => a.persianYear - b.persianYear || a.persianMonth - b.persianMonth)
    .map((month) => {
      const serial = month.persianYear * 12 + month.persianMonth;
      const validDate = Number.isInteger(month.persianYear) && Number.isInteger(month.persianMonth)
        && month.persianMonth >= 1 && month.persianMonth <= 12;
      if (!validDate || (previous !== null && serial !== previous + 1)) actual = planned = null;
      previous = serial;
      const amount = integer(month.actualCostIrr);
      const baseline = integer(month.estimateIrr);
      actual = actual !== null && amount !== null ? actual + amount : null;
      planned = planned !== null && baseline !== null ? planned + baseline : null;
      return {
        ...month,
        label: `${PERSIAN_MONTHS[month.persianMonth - 1]?.label ?? "ماه نامشخص"} ${count(month.persianYear)}`,
        actualCumulativeIrr: actual === null ? null : String(actual),
        plannedCumulativeIrr: planned === null ? null : String(planned),
      };
    });
  const hasPlan = rows.length > 0 && rows.every((row) => row.plannedCumulativeIrr !== null);
  return { rows, hasPlan, incompleteActual: rows.some((row) => row.actualCumulativeIrr === null) };
}

function svgNode(tag, attrs = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text;
  return node;
}

function cumulativeChart(view) {
  const figure = element("figure", "report-doc__curve");
  const svg = svgNode("svg", { viewBox: "0 0 760 290", role: "img", "aria-label": "منحنی هزینه تجمعی؛ مقادیر دقیق در جدول زیر نمودار", class: "report-doc__curve-svg" });
  const values = view.rows.flatMap((row) => [integer(row.actualCumulativeIrr), view.hasPlan ? integer(row.plannedCumulativeIrr) : null]).filter((value) => value !== null);
  const max = values.reduce((a, b) => a > b ? a : b, 0n);
  const min = values.reduce((a, b) => a < b ? a : b, 0n);
  const span = max - min || 1n;
  const scale = compactMoneyScale(String(max > -min ? max : -min));
  figure.append(element("figcaption", "", `هزینه تجمعی در بازه داده‌های دریافتی (${scale.unit})`));
  const x = (index) => 105 + index * 625 / Math.max(1, view.rows.length - 1);
  const y = (value) => 226 - Number(((value - min) * 19000n) / span) / 100;
  for (let step = 0; step <= 4; step += 1) {
    const value = min + (span * BigInt(step)) / 4n;
    const pos = y(value);
    svg.append(svgNode("line", { x1: 105, x2: 730, y1: pos, y2: pos, class: "report-doc__curve-grid" }));
    svg.append(svgNode("text", { x: 94, y: pos + 4, "text-anchor": "end", direction: "ltr" }, scale.format(String(value))));
  }
  const stride = Math.max(1, Math.ceil(view.rows.length / 5));
  view.rows.forEach((row, index) => {
    if (index % stride === 0 || index === view.rows.length - 1) {
      const edge = index === 0 || index === view.rows.length - 1;
      svg.append(svgNode("text", {
        x: x(index), y: 260, "text-anchor": index === 0 ? "end" : index === view.rows.length - 1 ? "start" : "middle", direction: "rtl",
        class: "report-doc__curve-month", "data-edge": edge,
      }, row.label));
    }
  });
  ["actual", ...(view.hasPlan ? ["planned"] : [])].forEach((series) => {
    let path = "";
    let connected = false;
    view.rows.forEach((row, index) => {
      const value = integer(row[`${series}CumulativeIrr`]);
      if (value === null) { connected = false; return; }
      path += `${connected ? "L" : "M"}${x(index)},${y(value)} `;
      connected = true;
      const point = svgNode("circle", { cx: x(index), cy: y(value), r: 3, class: `report-doc__curve-point report-doc__curve-point--${series}` });
      point.append(svgNode("title", {}, `${row.label} · ${money(String(value))}`));
      svg.append(point);
    });
    svg.append(svgNode("path", { d: path, class: `report-doc__curve-line report-doc__curve-line--${series}`, fill: "none" }));
  });
  figure.append(svg, note(view.hasPlan ? "خط پیوسته: هزینه واقعی · خط‌چین: برنامه مالی" : "خط پیوسته: هزینه واقعی؛ برنامه مالی در دسترس نیست یا کامل نیست."));
  return figure;
}

export function renderSCurve(data) {
  const view = buildCumulativeSeries(data.monthly?.months);
  if (!view.rows.length) return [note("برای رسم منحنی، داده ماهانه‌ای از سرویس مالی دریافت نشده است.")];
  const nodes = [note("مبدأ تجمع، ابتدای بازه داده‌های دریافتی است؛ این ارقام لزوماً جمع از آغاز پروژه نیستند. مبالغ برگشت و اصلاحات می‌توانند منحنی را کاهش دهند. این نمودار مالی است، نه درصد پیشرفت فیزیکی.")];
  if (!view.hasPlan) nodes.push(note("برنامه مالی ماهانه کامل در دسترس نیست؛ خط برنامه و انحراف از برنامه رسم یا محاسبه نشده است. برآورد کل پروژه جایگزین برنامه زمان‌بندی هزینه نیست."));
  if (view.incompleteActual) nodes.push(note("بخشی از داده ماهانه ناقص است؛ جمع‌های وابسته به آن نامشخص باقی مانده‌اند، نه صفر."));
  nodes.push(cumulativeChart(view), reportTable({
    caption: "جزئیات ماهانه و تجمعی منحنی S مالی",
    columns: ["ماه", "واقعی ماه", "واقعی تجمعی", "برنامه تجمعی", "انحراف تجمعی"].map((label, index) => ({ label, numeric: index > 0 })),
    rows: view.rows.map((row) => [row.label, money(row.actualCostIrr), money(row.actualCumulativeIrr),
      view.hasPlan ? money(row.plannedCumulativeIrr) : "مبنای کامل ندارد",
      view.hasPlan && row.actualCumulativeIrr !== null ? money(String(BigInt(row.actualCumulativeIrr) - BigInt(row.plannedCumulativeIrr))) : "قابل مقایسه نیست"]),
  }));
  (data.monthly?.warnings ?? []).filter((warning) => warning.code !== "MONTHLY_ESTIMATE_UNAVAILABLE")
    .forEach((warning) => nodes.push(note(reportWarningText(warning))));
  return nodes;
}

export function renderLevelOne(data) {
  const wbs = data.wbs;
  if (!wbs?.available) return [note("سرویس گزارش مالی سطح ۱ در این محیط در دسترس نیست؛ داده نمایشی جایگزین نشده است.")];
  const rows = wbs.nodes ?? [];
  if (!rows.length) return [note("مرحله‌ای در سطح ۱ ساختار شکست کار ثبت نشده است."), ...allocationNotes(wbs)];
  const ceiling = rows.flatMap((row) => [integer(row.initialEstimateIrr), integer(row.actualCostIrr)])
    .reduce((max, value) => value !== null && value > max ? value : max, 0n);
  const magnitude = (value) => integer(value) === null || integer(value) < 0n ? null
    : ceiling ? Number(integer(value) * 10000n / ceiling) / 100 : 0;
  const label = (row) => `${row.wbsCode} · ${row.title ?? "مرحله بدون عنوان"}`;
  return [
    note("هر مرحله شامل کل زیرشاخه‌های همان مرحله است؛ جمع سطح ۱ را با جمع زیرشاخه‌ها دوباره جمع نکنید. آبی: برآورد اولیه، سبز: هزینه واقعی. مقدار منفی در جدول حفظ می‌شود و میله افزایشی ندارد."),
    reportComparisonChart({ ariaLabel: "برآورد اولیه و هزینه واقعی مراحل سطح ۱", rows: rows.map((row) => ({ label: label(row), planMagnitude: magnitude(row.initialEstimateIrr), actualMagnitude: magnitude(row.actualCostIrr), valueText: money(row.actualCostIrr) })) }),
    reportTable({
      caption: "برآورد و هزینه واقعی مراحل سطح ۱",
      columns: ["مرحله", "برآورد اولیه", "برآورد اصلاح‌شده", "هزینه واقعی", "پیش‌بینی نهایی"].map((title, i) => ({ label: title, numeric: i > 0 })),
      rows: rows.map((row) => [label(row), money(row.initialEstimateIrr), money(row.revisedEstimateIrr), money(row.actualCostIrr), money(row.forecastFinalIrr)]),
    }),
    reportTable({
      caption: "باقیمانده و انحراف مراحل سطح ۱",
      columns: [{ label: "مرحله" }, { label: "هزینه کار باقی‌مانده", numeric: true }, { label: "بودجه تا تکمیل", numeric: true }, { label: "انحراف نهایی از اولیه", numeric: true }, { label: "محاسبه" }],
      rows: rows.map((row) => [label(row), money(row.remainingPhysicalCostIrr), money(row.moneyRequiredIrr),
        integer(row.forecastFinalIrr) !== null && integer(row.initialEstimateIrr) !== null ? money(String(BigInt(row.forecastFinalIrr) - BigInt(row.initialEstimateIrr))) : "قابل محاسبه نیست", status(row.calculationStatus)]),
    }),
    reportTable({
      caption: "تعداد فعالیت‌ها و ردیف‌های هر مرحله",
      columns: [{ label: "مرحله" }, { label: "فعالیت", numeric: true }, { label: "زیرمرحله", numeric: true }, { label: "ردیف برآورد", numeric: true }],
      rows: rows.map((row) => [label(row), count(row.activityCount), count(row.childCount), count(row.estimateLineCount)]),
    }),
    reportTable({
      caption: "تفکیک هزینه واقعی هر مرحله به نوع قلم",
      columns: ["مرحله", "مصالح", "نیروی انسانی", "تجهیزات", "هزینه عمومی"].map((title, i) => ({ label: title, numeric: i > 0 })),
      rows: rows.map((row) => [label(row), ...["material", "labor", "equipment", "general_cost"].map((type) => money(row.breakdown?.[type]))]),
    }),
    ...allocationNotes(wbs),
    ...(wbs.warnings ?? []).map((warning) => note(reportWarningText(warning))),
  ];
}

function allocationNotes(wbs) {
  return [reportTable({
    caption: "کنترل تخصیص هزینه‌های پروژه به مراحل",
    columns: [{ label: "مورد" }, { label: "مقدار", numeric: true }],
    rows: [
      ["هزینه واقعی کل پروژه طبق سرویس", money(wbs.totals?.actualCostIrr)],
      ["هزینه بدون اتصال به ردیف برآورد", money(wbs.unattributedActualIrr)],
      ["هزینه ردیف‌های فاقد نگاشت معتبر WBS", money(wbs.unmappedWbsActualIrr)],
      ["تعداد ردیف‌های فاقد نگاشت WBS", count(wbs.unmappedEstimateLineCount)],
      ["وضعیت کلی محاسبه", status(wbs.calculationStatus)],
    ],
  }), note("هزینه‌های بدون تخصیص در مراحل پنهان یا سرشکن نشده‌اند؛ برای تطبیق با کل پروژه باید جداگانه لحاظ شوند.")];
}

export function renderQuality(data) {
  const overview = data.overview ?? {};
  const quality = overview.progressQuality;
  const warnings = overview.warnings ?? [];
  const metricLabels = {
    currentExecutedValueIrr: "ارزش روز کار انجام‌شده", remainingPhysicalCostIrr: "هزینه کار باقی‌مانده",
    moneyRequiredToContinueIrr: "بودجه موردنیاز تا تکمیل", forecastFinalCostIrr: "پیش‌بینی هزینه نهایی",
    forecastPerSquareMeterIrr: "پیش‌بینی هزینه هر مترمربع",
  };
  const qualityLabels = [
    ["mappedLineCount", "ردیف‌های دارای نگاشت پیشرفت"], ["unmappedLineCount", "ردیف‌های فاقد نگاشت پیشرفت"],
    ["missingCount", "نگاشت موجود، مقدار انجام‌شده ناموجود"], ["manualOverrideCount", "اصلاح دستی مقدار انجام‌شده"],
    ["assignmentActualCount", "مقدار واقعی تخصیص"], ["assignmentPercentFallbackCount", "مقدار مبتنی بر درصد تخصیص"],
    ["taskFallbackCount", "مقدار مبتنی بر پیشرفت فعالیت"], ["workAsQuantityCount", "ساعت کار به‌جای مقدار اندازه‌گیری‌شده"],
    ["unmappedAssignmentCount", "تخصیص نامعتبر"], ["unmappedActivityCount", "فعالیت نامعتبر"],
    ["generalCostLineCount", "ردیف هزینه عمومی؛ بدون نیاز به پیشرفت"],
  ];
  return [reportFigures([
    { label: "وضعیت محاسبات مالی", value: status(overview.calculationStatus) },
    { label: "کیفیت مبنای پیشرفت", value: quality?.complete === true ? "کامل" : quality?.complete === false ? "نیازمند بررسی" : "اعلام نشده" },
    { label: "قیمت روز ناموجود", value: count(overview.missingPriceCount) },
    { label: "ردیف کنارگذاشته‌شده", value: count(overview.excludedEstimateLineCount) },
  ]), note("نبود هشدار به‌تنهایی تضمین صحت همه داده‌ها نیست. شمارنده‌های زیر بعضاً زیرمجموعه یکدیگرند و نباید با هم جمع شوند."),
  ...((overview.incompleteMetricKeys ?? []).length ? [note(`شاخص‌های ناقص: ${overview.incompleteMetricKeys.map((key) => metricLabels[key] ?? key).join("، ")}`)] : []), reportTable({
    caption: "کیفیت و منشأ مقادیر انجام‌شده",
    columns: [{ label: "کنترل" }, { label: "تعداد", numeric: true }],
    rows: quality ? qualityLabels.map(([key, label]) => [label, count(quality[key])]) : [],
    empty: "جزئیات کیفیت پیشرفت از سرویس دریافت نشده است.",
  }), ...warningTables(warnings)];
}

/**
 * The identity a warning is grouped by: its own fields, never its rendered sentence.
 *
 * Two records that read identically but differ in cause, severity or scope are two
 * findings and stay apart. Two that agree on all of these are the same finding about the
 * same thing, seen on more than one estimate line -- which is what the count is for.
 */
function warningIdentity(warning) {
  return JSON.stringify([
    warning.code ?? null,
    warning.severity ?? null,
    warning.progressStatus ?? null,
    warning.excludedFromCalculation ?? null,
    [...(warning.affectedMetricKeys ?? [])].sort(),
    warning.resourceCode ?? warning.resourceId ?? null,
  ]);
}

/**
 * The warnings chapter: one row per finding, with how many records carry it and which.
 *
 * The service sends one warning per estimate line, which is right -- a line either has a
 * current price or it does not. Printing one ROW per line was not: 1,828 rows carried 161
 * distinct pairs of (sentence, resource), so the document repeated itself while leaving
 * out the only field that differed.
 *
 * Grouping is done here, in the document, and nowhere else. The service's list is the
 * record; this is a reading of it.
 */
function groupWarnings(warnings) {
  const groups = new Map();
  warnings.forEach((warning) => {
    const identity = warningIdentity(warning);
    const group = groups.get(identity) ?? {
      warning,
      count: 0,
      activities: new Set(),
      lines: new Set(),
    };
    group.count += 1;
    if (warning.activityExternalId) group.activities.add(String(warning.activityExternalId));
    if (warning.estimateLineId) group.lines.add(String(warning.estimateLineId));
    groups.set(identity, group);
  });
  return [...groups.values()].sort((left, right) => right.count - left.count);
}

/**
 * Where a group's affected records are named.
 *
 * (code, resource, activity) is unique per record on this dataset, so the activity list is
 * the complete set of records in the group and not a sample of it. When a record carries
 * no activity id there is nothing to name it by, and the row says so rather than implying
 * the list is complete when it is not.
 */
function affectedList(group) {
  const activities = [...group.activities].sort((left, right) =>
    left.localeCompare(right, "fa", { numeric: true }));
  if (!activities.length) return "بدون شناسه فعالیت";
  const unnamed = group.count - activities.length;
  return unnamed > 0
    ? `${activities.join("، ")} (و ${count(unnamed)} ردیف بدون شناسه فعالیت)`
    : activities.join("، ");
}

function warningTables(warnings) {
  const groups = groupWarnings(warnings);
  const grouped = groups.filter((group) => group.count > 1).reduce((sum, group) => sum + group.count, 0);
  const summary = groups.length && grouped
    ? [note(`${count(warnings.length)} هشدار از سرویس دریافت شد. هشدارهای هم‌کد، هم‌شدت و هم‌دامنه در یک سطر جمع شده‌اند: `
        + `${count(groups.length)} سطر، با تعداد ردیف‌های درگیر و شناسه فعالیت همه آن‌ها. هیچ هشداری حذف نشده است.`)]
    : [];
  return [...summary, reportTable({
    caption: "هشدارها و موارد نیازمند بررسی",
    columns: [{ label: "هشدار" }, { label: "قلم" }, { label: "ردیف درگیر", numeric: true },
              { label: "فعالیت‌های درگیر" }],
    rows: groups.map((group) => [
      reportWarningText(group.warning),
      group.warning.resourceCode ?? group.warning.resourceId ?? "کل پروژه",
      count(group.count),
      affectedList(group),
    ]),
    empty: "سرویس برای این محاسبه هشداری اعلام نکرده است.",
  })];
}
