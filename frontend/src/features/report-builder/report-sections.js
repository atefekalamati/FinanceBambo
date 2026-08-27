import { element } from "../../shared/dom/elements.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { compactMoneyScale, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { reportComparisonChart, reportFigures, reportTable } from "./report-document.js";
import { buildBulletPresentation } from "../../shared/reports/report-presentation.js";
import { buildMonthlyTrend, TREND_MODES } from "../../shared/reports/monthly-trend.js";
import { rollupPriceVariances, rollupQuantityVariances } from "../../shared/variances/variance-rollup.js";
import { reportWarningText } from "../../shared/warnings/finance-warning-labels.js";
import { isWithinPeriod } from "../../shared/dates/reporting-periods.js";

/**
 * One renderer per catalogue entry. Each is handed the datasets its entry asked
 * for and returns the nodes that go under its numbered heading.
 *
 * Nothing here computes money. Every figure is one the service already worked
 * out, or one of the presentations the screens already use — so a report and
 * the screen it came from cannot disagree, which is the only way a printed
 * document stays trustworthy after it leaves the browser.
 */

const money = (value) => (/^-?\d+$/.test(String(value ?? "")) ? formatTomanFromIrr(value) : "قابل محاسبه نیست");

const SUMMARY_FIGURES = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه", "مبنای اولیه برآورد پروژه"],
  ["actualCostIrr", "هزینه واقعی ثبت‌شده", "فقط اسناد مالی تأییدشده"],
  ["currentExecutedValueIrr", "ارزش روز کار انجام‌شده", "مقدار اجراشده با قیمت روز"],
  ["remainingPhysicalCostIrr", "هزینه کار باقی‌مانده", "کار باقی‌مانده با قیمت روز"],
  ["forecastFinalCostIrr", "پیش‌بینی هزینه نهایی", "هزینه واقعی به‌اضافه پول ادامه"],
  ["moneyRequiredToContinueIrr", "بودجه موردنیاز تا تکمیل", "با لحاظ خرید ثبت‌شده مصالح"],
  ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع", "براساس زیربنای کل پروژه"],
  ["forecastPerSquareMeterIrr", "پیش‌بینی هزینه هر مترمربع", "پیش‌بینی نهایی تقسیم بر زیربنا"],
]);

const INVOICE_STATUS_LABELS = Object.freeze({
  draft: "پیش‌نویس",
  awaitingConfirmation: "در انتظار تأیید",
  confirmed: "تأییدشده",
  voided: "باطل‌شده",
  corrected: "اصلاح‌شده",
});

const EVENT_LABELS = Object.freeze({
  "estimate.revised": "بازنگری برآورد",
  "price.created": "ثبت قیمت",
  "invoice.confirmed": "تأیید فاکتور",
  "invoice.voided": "ابطال فاکتور",
  "invoice.corrected": "سند اصلاحی",
  "settings.revised": "بازنگری تنظیمات",
  "attachment.viewed": "مشاهده پیوست مالی",
});

const SCOPE_LABELS = Object.freeze({ organization: "پایه سازمان", project: "اختصاصی پروژه" });

function metricsOf(data) {
  return data.overview?.metrics ?? {};
}

export const REPORT_SECTIONS = Object.freeze({
  overview(data) {
    const metrics = metricsOf(data);
    return [
      reportFigures(SUMMARY_FIGURES.map(([key, label, note]) => ({
        label,
        note,
        value: money(metrics[key]),
      }))),
      reportTable({
        caption: "جدول شاخص‌های اصلی مالی پروژه",
        columns: [{ label: "شاخص" }, { label: "مقدار", numeric: true }, { label: "مبنا" }],
        rows: SUMMARY_FIGURES.map(([key, label, note]) => [label, money(metrics[key]), note]),
      }),
    ];
  },

  deviation(data) {
    const metrics = metricsOf(data);
    const initial = metrics.initialEstimateIrr;
    const forecast = metrics.forecastFinalCostIrr;
    if (!/^-?\d+$/.test(String(initial ?? "")) || !/^-?\d+$/.test(String(forecast ?? ""))) {
      return [element("p", "report-doc__note", "انحراف پیش‌بینی قابل محاسبه نیست: یکی از دو مبنا در سرویس مالی به دست نیامده است.")];
    }
    const change = BigInt(forecast) - BigInt(initial);
    const direction = change > 0n ? "بیشتر از برآورد اولیه" : change < 0n ? "کمتر از برآورد اولیه" : "برابر برآورد اولیه";
    const absolute = change < 0n ? -change : change;
    return [
      reportFigures([
        { label: "برآورد اولیه", value: money(initial) },
        { label: "پیش‌بینی هزینه نهایی", value: money(forecast) },
        { label: `انحراف — ${direction}`, value: money(String(absolute)) },
      ]),
      element("p", "report-doc__note", "انحراف، فاصله پیش‌بینی هزینه نهایی از برآورد اولیه است؛ نه هزینه‌ای که تا امروز خرج شده."),
    ];
  },

  breakdown(data) {
    const view = buildBulletPresentation(data.overview?.breakdown ?? []);
    return [
      reportComparisonChart({
        ariaLabel: "نمودار هزینه واقعی هر نوع قلم در برابر برآورد همان نوع",
        rows: view.rows.map((row) => ({
          label: row.label,
          planMagnitude: row.estimateMagnitude,
          actualMagnitude: row.actualBelowZero ? null : row.actualMagnitude,
          valueText: money(row.actualCostIrr),
        })),
      }),
      reportTable({
        caption: "جدول ترکیب هزینه به تفکیک نوع قلم هزینه",
        columns: [
          { label: "نوع قلم" },
          { label: "برآورد اولیه", numeric: true },
          { label: "هزینه واقعی", numeric: true },
          { label: "نسبت به برآورد", numeric: true },
          { label: "پیش‌بینی نهایی", numeric: true },
        ],
        rows: view.rows.map((row) => [
          row.label,
          money(row.initialEstimateIrr),
          money(row.actualCostIrr),
          row.consumedPercent === null
            ? (row.actualCostIrr === "0" ? "—" : "برآورد ثبت نشده")
            : `${formatDisplayNumber(String(Math.round(row.consumedPercent)))}٪`,
          money(row.forecastFinalIrr),
        ]),
      }),
    ];
  },

  monthly(data) {
    const view = buildMonthlyTrend({ months: data.monthly?.months ?? [], mode: TREND_MODES.PERIODIC });
    const scale = compactMoneyScale(view.maximumIrr);
    const nodes = [
      reportComparisonChart({
        ariaLabel: "نمودار هزینه واقعی ثبت‌شده در هر ماه شمسی",
        rows: view.points.map((point) => ({
          label: point.fullLabel,
          planMagnitude: point.estimateMagnitude,
          actualMagnitude: point.belowBaseline ? null : point.actualMagnitude,
          valueText: scale?.format(point.actualIrr) ? `${scale.format(point.actualIrr)} ${scale.unit}` : money(point.actualIrr),
        })),
      }),
      reportTable({
        caption: "جدول روند ماهانه هزینه واقعی پروژه",
        columns: [
          { label: "ماه" },
          { label: "برآورد ماهانه", numeric: true },
          { label: "هزینه واقعی", numeric: true },
          { label: "اسناد", numeric: true },
          { label: "ابطال", numeric: true },
        ],
        rows: view.points.map((point) => [
          point.fullLabel,
          point.estimateIrr === null ? "ثبت نشده" : money(point.estimateIrr),
          money(point.actualIrr),
          formatDisplayNumber(String(point.invoiceCount ?? 0)),
          formatDisplayNumber(String(point.reversalCount ?? 0)),
        ]),
      }),
    ];
    if (!view.hasEstimate) {
      nodes.unshift(element("p", "report-doc__note", "برآورد ماهانه در دسترس نیست و فقط هزینه واقعی ثبت‌شده رسم شده است."));
    }
    return nodes;
  },

  priceVariance(data) {
    const rows = rollupPriceVariances(data.overview?.topPriceVariances ?? []);
    return [reportTable({
      caption: "جدول بیشترین اثر تغییر قیمت بر برآورد پروژه",
      columns: [
        { label: "قلم هزینه" },
        { label: "کد" },
        { label: "اثر بر برآورد", numeric: true },
        { label: "جهت" },
        { label: "ردیف برآورد", numeric: true },
      ],
      rows: rows.map((row) => [
        row.resourceTitle ?? "قلم بدون عنوان",
        row.resourceCode ?? "—",
        money(row.varianceIrr),
        BigInt(row.varianceIrr ?? "0") > 0n ? "افزایش هزینه" : "کاهش هزینه",
        formatDisplayNumber(String(row.lineCount ?? 1)),
      ]),
      empty: "انحراف قیمت معتبری برای این تاریخ گزارش ثبت نشده است.",
    })];
  },

  quantityVariance(data) {
    const rows = rollupQuantityVariances(data.overview?.topQuantityVariances ?? []);
    return [reportTable({
      caption: "جدول بیشترین انحراف مقدار ردیف‌های برآورد",
      columns: [
        { label: "قلم هزینه" },
        { label: "کد" },
        { label: "واحد" },
        { label: "مقدار اولیه", numeric: true },
        { label: "آخرین مقدار", numeric: true },
        { label: "انحراف", numeric: true },
      ],
      rows: rows.map((row) => [
        row.resourceTitle ?? "قلم بدون عنوان",
        row.resourceCode ?? "—",
        row.baseUnit ?? "—",
        formatDisplayNumber(row.initialQuantity ?? "—"),
        formatDisplayNumber(row.revisedQuantity ?? "—"),
        formatDisplayNumber(row.varianceQuantity ?? "—"),
      ]),
      empty: "انحراف مقداری برای این تاریخ گزارش ثبت نشده است.",
    })];
  },

  invoices(data) {
    const rows = (data.invoices?.items ?? [])
      .filter((invoice) => isWithinPeriod(invoice.invoiceDate, data.period))
      .sort((left, right) => String(right.invoiceDate).localeCompare(String(left.invoiceDate)));
    return [reportTable({
      caption: "جدول فاکتورهای ثبت‌شده در بازه گزارش",
      columns: [
        { label: "شماره" },
        { label: "تاریخ" },
        { label: "فروشنده" },
        { label: "وضعیت" },
        { label: "مبلغ نهایی", numeric: true },
      ],
      rows: rows.map((invoice) => [
        invoice.invoiceNumber ?? "—",
        formatBusinessDate(invoice.invoiceDate),
        invoice.vendorName ?? "—",
        INVOICE_STATUS_LABELS[invoice.invoiceStatus] ?? invoice.invoiceStatus ?? "—",
        money(invoice.finalAmountIRR ?? invoice.finalAmountIrr),
      ]),
      empty: "در این بازه فاکتوری ثبت نشده است.",
    })];
  },

  auditEvents(data) {
    const rows = (data.audit?.items ?? [])
      .slice()
      .sort((left, right) => String(right.occurredAt).localeCompare(String(left.occurredAt)));
    return [reportTable({
      caption: "جدول رویدادهای مالی ثبت‌شده در بازه گزارش",
      columns: [{ label: "زمان" }, { label: "رویداد" }, { label: "موجودیت" }, { label: "دلیل" }],
      rows: rows.map((event) => [
        event.occurredAt ? formatSystemDateTime(event.occurredAt) : "—",
        EVENT_LABELS[event.action] ?? event.action ?? "—",
        event.entityType ?? "—",
        event.reason ?? "—",
      ]),
      empty: "در این بازه رویداد مالی ثبت نشده است.",
    })];
  },

  warnings(data) {
    const rows = data.overview?.warnings ?? [];
    return [reportTable({
      caption: "جدول هشدارهای کیفیت محاسبه در این گزارش",
      columns: [{ label: "هشدار" }, { label: "ردیف برآورد" }],
      rows: rows.map((warning) => [reportWarningText(warning), warning.resourceCode ?? warning.estimateLineId ?? "کل پروژه"]),
      empty: "برای محاسبات این گزارش هشداری ثبت نشده است.",
    })];
  },

  prices(data) {
    const rows = data.prices?.currentPrices ?? [];
    return [reportTable({
      caption: "جدول قیمت روز اقلام پروژه",
      columns: [
        { label: "قلم هزینه" },
        { label: "کد" },
        { label: "واحد" },
        { label: "قیمت روز", numeric: true },
        { label: "منبع قیمت" },
        { label: "تاریخ اعتبار" },
      ],
      rows: rows.map((item) => [
        item.resource?.title ?? "—",
        item.resource?.code ?? "—",
        item.resource?.baseUnit ?? "—",
        item.currentPrice ? money(item.currentPrice.unitPriceIRR) : "ثبت نشده",
        item.currentPrice ? SCOPE_LABELS[item.currentPrice.scope] ?? item.currentPrice.scope : "—",
        item.currentPrice?.effectiveFrom ? formatBusinessDate(item.currentPrice.effectiveFrom) : "—",
      ]),
      empty: "برای اقلام این پروژه هنوز قیمتی ثبت نشده است.",
    })];
  },

  estimateLines(data) {
    const resources = new Map((data.financialItems?.resources ?? []).map((resource) => [resource.resourceId, resource]));
    const rows = data.financialItems?.estimateLines ?? [];
    return [reportTable({
      caption: "جدول ریز برآورد پروژه",
      columns: [
        { label: "فعالیت" },
        { label: "قلم هزینه" },
        { label: "واحد" },
        { label: "مقدار اولیه", numeric: true },
        { label: "آخرین مقدار", numeric: true },
        { label: "اصلاح‌شده" },
      ],
      rows: rows.map((line) => {
        const resource = resources.get(line.resourceId);
        const general = resource?.type === "general_cost";
        const original = general ? line.originalAmount : line.originalQuantity;
        const revised = general ? line.revisedAmount : line.revisedQuantity;
        return [
          line.activityTitle ?? line.activityExternalId ?? "—",
          resource?.title ?? "—",
          general ? "ریال" : resource?.baseUnit ?? "—",
          general ? money(original) : formatDisplayNumber(original ?? "—"),
          general ? money(revised) : formatDisplayNumber(revised ?? "—"),
          String(original) === String(revised) ? "خیر" : "بله",
        ];
      }),
      empty: "برای این پروژه هنوز ردیف برآوردی ثبت نشده است.",
    })];
  },
});
