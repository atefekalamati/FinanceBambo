import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { isWithinPeriod } from "../../shared/dates/reporting-periods.js";
import { reportTable } from "./report-document.js";

const money = (value) => /^-?\d+$/.test(String(value ?? "")) ? formatTomanFromIrr(value) : "قابل محاسبه نیست";
const note = (value) => element("p", "report-doc__note", value);
const statusLabels = { draft: "پیش‌نویس", awaitingConfirmation: "در انتظار تأیید", confirmed: "تأییدشده", voided: "باطل‌شده", corrected: "اصلاح‌شده" };
const sourceLabels = { manual: "دستی", image: "تصویر", voice: "صوت", reversal: "برگشت", corrective: "اصلاحی" };

export function supplierDocumentRows(items = [], period) {
  const groups = new Map();
  items.filter((item) => isWithinPeriod(item.invoiceDate, period)).forEach((item) => {
    const vendor = item.vendorName?.trim() || "فروشنده نامشخص";
    const key = JSON.stringify([vendor, item.invoiceStatus, item.source]);
    const group = groups.get(key) ?? { vendor, status: item.invoiceStatus, source: item.source, count: 0, amount: 0n };
    group.count += 1;
    const value = item.finalAmountIRR ?? item.finalAmountIrr;
    group.amount = group.amount !== null && /^-?\d+$/.test(String(value ?? "")) ? group.amount + BigInt(value) : null;
    groups.set(key, group);
  });
  return [...groups.values()].map((group) => ({ ...group, amount: group.amount === null ? null : String(group.amount) }));
}

function canonicalDecimal(value) {
  if (!/^\d+(?:\.\d+)?$/.test(String(value ?? ""))) return null;
  const [whole, fraction = ""] = String(value).split(".");
  return `${BigInt(whole)}.${fraction.replace(/0+$/, "")}`;
}

export function changedEstimateRows(workspace = {}) {
  const resources = new Map((workspace.resources ?? []).map((resource) => [resource.resourceId, resource]));
  return (workspace.estimateLines ?? []).flatMap((line) => {
    const resource = resources.get(line.resourceId);
    const general = resource?.type === "general_cost";
    const original = general ? line.originalAmount : line.originalQuantity;
    const revised = general ? line.revisedAmount : line.revisedQuantity;
    const known = canonicalDecimal(original) !== null && canonicalDecimal(revised) !== null;
    if (known && canonicalDecimal(original) === canonicalDecimal(revised)) return [];
    return [{ line, resource, general, original, revised, known }];
  });
}

function metricReport(data, metrics) {
  return [note("ارقام از سرویس مالی دریافت شده‌اند؛ مقدار ناموجود صفر نیست. بودجه تا تکمیل با هزینه فیزیکی کار باقی‌مانده یک مفهوم ندارد."),
    ...(data.overview?.calculationStatus === "incomplete" ? [note("محاسبات ناقص است؛ پیش از تصمیم‌گیری گزارش کیفیت داده را بررسی کنید.")] : []),
    reportTable({ caption: "شاخص‌ها و مبنای محاسبه", columns: [{ label: "شاخص" }, { label: "مبلغ", numeric: true }, { label: "مبنا" }],
      rows: metrics.map(([key, label, basis]) => [label, money(data.overview?.metrics?.[key]), basis]) })];
}

export const FOLLOWUP_SECTIONS = Object.freeze({
  completionBudget(data) {
    return metricReport(data, [
      ["actualCostIrr", "هزینه واقعی", "اسناد مالی مؤثر تا تاریخ گزارش"],
      ["remainingPhysicalCostIrr", "هزینه کار باقی‌مانده", "کار فیزیکی باقی‌مانده با قیمت معتبر"],
      ["moneyRequiredToContinueIrr", "بودجه موردنیاز تا تکمیل", "بودجه ادامه طبق قواعد محاسبات مالی"],
      ["forecastFinalCostIrr", "پیش‌بینی نهایی", "هزینه واقعی به‌اضافه بودجه موردنیاز"],
    ]);
  },
  areaCosts(data) {
    return metricReport(data, [
      ["actualCostIrr", "هزینه واقعی کل", "مبلغ کل متناظر با شاخص واقعی هر مترمربع"],
      ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع", "بر مبنای زیربنای معتبر در محاسبه سرویس"],
      ["forecastFinalCostIrr", "پیش‌بینی نهایی کل", "مبلغ کل متناظر با شاخص پیش‌بینی هر مترمربع"],
      ["forecastPerSquareMeterIrr", "پیش‌بینی هر مترمربع", "بر مبنای زیربنای معتبر؛ مقدار ناموجود قابل محاسبه نیست"],
    ]);
  },
  unpricedItems(data) {
    const rows = (data.prices?.currentPrices ?? []).filter((item) => !item.currentPrice);
    return [note("این فهرست از وضعیت جاری قیمت‌هاست. نبود قیمت برای یک قلم، به‌تنهایی اندازه اثر آن بر Forecast را تعیین نمی‌کند؛ استفاده آن در برآورد نیز باید بررسی شود."), reportTable({
      caption: "اقلام فاقد قیمت جاری", columns: [{ label: "قلم" }, { label: "کد" }, { label: "واحد" }],
      rows: rows.map((item) => [item.resource?.title ?? "—", item.resource?.code ?? "—", item.resource?.baseUnit ?? "—"]),
      empty: "در فهرست دریافت‌شده، قلم فاقد قیمت جاری وجود ندارد.",
    })];
  },
  supplierDocuments(data) {
    return [note("گروه‌بندی بر اساس نام ثبت‌شده فروشنده است، نه شناسه یکتای تأمین‌کننده. مبلغ هر گروه جمع اسمی اسناد است؛ نه هزینه واقعی، بدهی یا پرداخت. وضعیت و منبع اسناد جدا نگه داشته شده‌اند."), reportTable({
      caption: "اسناد فروشندگان در بازه تاریخ فاکتور",
      columns: [{ label: "فروشنده" }, { label: "وضعیت" }, { label: "منبع" }, { label: "تعداد", numeric: true }, { label: "جمع مبلغ اسناد", numeric: true }],
      rows: supplierDocumentRows(data.invoices?.items, data.period).map((row) => [row.vendor, statusLabels[row.status] ?? row.status ?? "—", sourceLabels[row.source] ?? row.source ?? "—", formatDisplayNumber(String(row.count)), money(row.amount)]),
    })];
  },
  estimateChanges(data) {
    return [note("مقایسه مقدار اولیه با مقدار جاری است، نه تاریخچه رویدادها یا اثر ریالی تغییر مقدار. ردیف‌های ناقص برای بررسی باقی مانده‌اند و تغییر قطعی تلقی نمی‌شوند."), reportTable({
      caption: "ردیف‌های تغییرکرده یا دارای مبنای ناقص",
      columns: [{ label: "فعالیت / قلم" }, { label: "واحد" }, { label: "اولیه", numeric: true }, { label: "جاری", numeric: true }, { label: "وضعیت" }],
      rows: changedEstimateRows(data.financialItems).map(({ line, resource, general, original, revised, known }) => [
        `${line.activityTitle ?? line.activityExternalId ?? "—"} · ${resource?.title ?? line.resourceId ?? "—"}`,
        general ? getDisplayCurrencyLabel() : resource?.baseUnit ?? "—",
        general ? money(original) : formatDisplayNumber(original ?? "—"),
        general ? money(revised) : formatDisplayNumber(revised ?? "—"), known ? "تغییرکرده" : "مبنای ناقص",
      ]), empty: "در ردیف‌های دریافت‌شده، تغییری نسبت به مقدار اولیه یا مبنای ناقصی یافت نشد.",
    })];
  },
});
