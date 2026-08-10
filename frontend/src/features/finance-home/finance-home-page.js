import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";

const SUMMARY_ITEMS = Object.freeze([
  ["initialEstimateIrr", "برآورد اولیه", "مبنای اولیه برآورد پروژه"],
  ["actualCostIrr", "هزینه واقعی", "فقط اسناد مالی تأییدشده"],
  ["currentExecutedValueIrr", "ارزش روز کار اجراشده", "مقدار اجراشده با قیمت روز"],
  ["remainingPhysicalCostIrr", "هزینه فیزیکی باقیمانده", "کار باقیمانده با قیمت روز"],
  ["moneyRequiredToContinueIrr", "پول موردنیاز برای ادامه", "با لحاظ خرید ثبت‌شده مصالح"],
  ["forecastFinalCostIrr", "پیش‌بینی هزینه نهایی", "هزینه واقعی به‌اضافه پول ادامه"],
  ["actualCostPerSquareMeterIrr", "هزینه واقعی هر مترمربع", "براساس زیربنای کل پروژه"],
  ["forecastPerSquareMeterIrr", "پیش‌بینی هر مترمربع", "پیش‌بینی نهایی تقسیم بر زیربنا"],
]);

const WARNING_LABELS = Object.freeze({
  UNIT_CONVERSION_MISSING: "تبدیل واحد لازم برای بخشی از مقدار خریداری‌شده تعریف نشده است.",
  PROGRESS_MISSING: "برای یکی از خطوط برآورد، مقدار معتبر پیشرفت موجود نیست.",
  QUANTITY_OVERRUN: "مقدار اجراشده یکی از خطوط از مقدار اصلاح‌شده بیشتر است.",
  CURRENT_PRICE_MISSING: "قیمت روز یکی از اقلام ثبت نشده و از محاسبات زنده آن خط کنار گذاشته شده است.",
  GENERAL_COST_OVERRUN: "هزینه عمومی واقعی از برآورد اصلاح‌شده هزینه عمومی بیشتر است.",
  GROSS_AREA_MISSING: "زیربنای کل ثبت نشده؛ شاخص‌های هر مترمربع قابل محاسبه نیستند.",
});

const WORK_AREAS = Object.freeze([
  { key: "financial-items", title: "اقلام و متره", description: "مدیریت اقلام مالی، خطوط فعالیت و مقدارهای اولیه و اصلاح‌شده", meta: "اقلام · برآورد · بازنگری", href: "#/financial-items" },
  { key: "prices", title: "قیمت‌ها و تبدیل واحد", description: "ثبت قیمت پایه، جایگزینی پروژه و مشاهده تاریخچه تغییرات", meta: "قیمت روز · تاریخچه · واحد", href: "#/prices" },
  { key: "progress", title: "پیشرفت و مقادیر اجرا", description: "مشاهده نسخه ثبت‌شده پیشرفت، کیفیت داده و جایگزینی ممیزی‌شده", meta: "نسخه ثبت‌شده · اجرا · هشدار", href: "#/progress" },
  { key: "invoices", title: "فاکتورها", description: "مشاهده فهرست، وضعیت، منبع، فروشنده، مبلغ و جزئیات خطوط", meta: "فهرست · جزئیات · وضعیت", href: "#/invoices" },
  { key: "settings", title: "تنظیمات مالی", description: "زیربنای کل، واحد پول نمایشی و تنظیمات سطح پروژه", meta: "زیربنا · تومان · دسترسی", href: "#/settings" },
  { key: "audit", title: "تاریخچه و ممیزی", description: "ردیابی بازنگری، جایگزینی، تأییدها و عملیات حساس مالی", meta: "کاربر · زمان · دلیل" },
]);

function formatTomanFromIrr(value) {
  if (!/^-?\d+$/.test(String(value ?? ""))) return "قابل محاسبه نیست";
  const amount = BigInt(value);
  const whole = amount / 10n;
  const remainder = amount < 0n ? -(amount % 10n) : amount % 10n;
  const display = remainder === 0n ? whole.toString() : `${amount < 0n && whole === 0n ? "-" : ""}${whole}.${remainder}`;
  return `${formatDisplayNumber(display)} تومان`;
}

function createSummaryCard(key, label, description, data) {
  const card = document.createElement("article");
  const unavailable = data?.[key] === null || data?.[key] === undefined;
  card.className = `summary-card${unavailable ? " summary-card--unavailable" : ""}`;
  const title = document.createElement("h2");
  title.textContent = label;
  const value = document.createElement("p");
  value.className = "summary-card__value numeric";
  value.textContent = formatTomanFromIrr(data?.[key]);
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

function renderFinanceHome(data) {
  const fragment = document.createDocumentFragment();
  const intro = document.createElement("section");
  intro.className = "finance-intro";
  const logoSign = document.createElement("img");
  logoSign.className = "finance-intro__sign";
  logoSign.src = new URL("../../../public/assets/images/Logo%20Sign.svg", import.meta.url).href;
  logoSign.alt = "";
  logoSign.setAttribute("aria-hidden", "true");
  const eyebrow = document.createElement("span");
  eyebrow.className = "finance-intro__eyebrow";
  eyebrow.textContent = "مرکز کنترل مالی پروژه";
  const title = document.createElement("h1");
  title.textContent = "امور مالی پروژه";
  const description = document.createElement("p");
  description.textContent = "خلاصه وضعیت مالی و دسترسی مستقیم به عملیات موردنیاز پروژه، بدون داشبورد یا ناوبری داخلی جداگانه.";
  intro.append(logoSign, eyebrow, title, description);

  const summaryHeader = document.createElement("div");
  summaryHeader.className = "section-heading";
  const summaryHeading = document.createElement("div");
  const summaryEyebrow = document.createElement("span");
  summaryEyebrow.textContent = "نمای زنده";
  const summaryTitle = document.createElement("h2");
  summaryTitle.textContent = "وضعیت مالی در یک نگاه";
  summaryHeading.append(summaryEyebrow, summaryTitle);
  const reportMeta = document.createElement("small");
  reportMeta.textContent = `تاریخ گزارش ${formatBusinessDate(data.reportingDate)} · نسخه پیشرفت انتخاب‌شده`;
  summaryHeader.append(summaryHeading, reportMeta);
  const summary = document.createElement("section");
  summary.className = "summary-grid";
  summary.setAttribute("aria-label", "خلاصه وضعیت مالی");
  SUMMARY_ITEMS.forEach(([key, label, description]) => summary.append(createSummaryCard(key, label, description, data.metrics)));

  const warnings = document.createElement("section");
  warnings.className = "finance-warnings";
  warnings.setAttribute("aria-label", "هشدارهای محاسبات مالی");
  if (data.warnings.length) {
    const warningTitle = document.createElement("h2");
    warningTitle.textContent = "هشدارهای کیفیت محاسبه";
    const list = document.createElement("ul");
    data.warnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = WARNING_LABELS[warning.code] ?? "برای بخشی از محاسبات مالی هشدار ثبت شده است.";
      list.append(item);
    });
    warnings.append(warningTitle, list);
  } else {
    warnings.classList.add("finance-warnings--clear");
    warnings.textContent = "برای محاسبات زنده فعلی هشداری ثبت نشده است.";
  }

  const areasHeader = document.createElement("div");
  areasHeader.className = "section-heading";
  areasHeader.innerHTML = "<div><span>فضای کاری</span><h2>عملیات مالی پروژه</h2></div>";
  const areas = document.createElement("section");
  areas.className = "work-area-grid";
  areas.setAttribute("aria-label", "بخش‌های امور مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  fragment.append(intro, summaryHeader, summary, warnings, areasHeader, areas);
  return fragment;
}

export function createFinanceHomePage({ reportsAdapter, progressAdapter }) {
  let state = createRequestState(REQUEST_STATUS.LOADING);
  const root = document.createElement("div");

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const snapshots = await progressAdapter.getSnapshots();
      if (!snapshots.length) {
        state = createRequestState(REQUEST_STATUS.EMPTY);
      } else {
        const latest = snapshots[0].snapshot;
        const report = await reportsAdapter.getLiveReport({ reportingDate: latest.reportingDate, progressSnapshotId: latest.progressSnapshotId });
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
    message.textContent = "برای محاسبه شاخص‌های مالی، حداقل یک نسخه پیشرفت آماده لازم است.";
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
