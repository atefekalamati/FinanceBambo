import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";

const SUMMARY_ITEMS = Object.freeze([
  ["originalEstimate", "برآورد اولیه"],
  ["actualRegisteredCost", "هزینه واقعی ثبت‌شده"],
  ["moneyRequiredToContinue", "پول موردنیاز برای ادامه"],
  ["forecastFinalCost", "پیش‌بینی هزینه نهایی"],
]);

const WORK_AREAS = Object.freeze([
  { key: "financial-items", title: "اقلام و متره", description: "مدیریت اقلام مالی، خطوط فعالیت و مقدارهای اولیه و اصلاح‌شده", meta: "اقلام · برآورد · بازنگری", href: "#/financial-items" },
  { key: "prices", title: "قیمت‌ها و تبدیل واحد", description: "ثبت قیمت پایه، جایگزینی پروژه و مشاهده تاریخچه تغییرات", meta: "قیمت روز · تاریخچه · واحد", href: "#/prices" },
  { key: "progress", title: "پیشرفت و مقادیر اجرا", description: "مشاهده نسخه ثبت‌شده پیشرفت، کیفیت داده و جایگزینی ممیزی‌شده", meta: "نسخه ثبت‌شده · اجرا · هشدار", href: "#/progress" },
  { key: "invoices", title: "فاکتورها", description: "مشاهده فهرست، وضعیت، منبع، فروشنده، مبلغ و جزئیات خطوط", meta: "فهرست · جزئیات · وضعیت", href: "#/invoices" },
  { key: "settings", title: "تنظیمات مالی", description: "زیربنای کل، واحد پول نمایشی و تنظیمات سطح پروژه", meta: "زیربنا · تومان · دسترسی", href: "#/settings" },
  { key: "audit", title: "تاریخچه و ممیزی", description: "ردیابی بازنگری، جایگزینی، تأییدها و عملیات حساس مالی", meta: "کاربر · زمان · دلیل" },
]);

function createSummaryCard(key, label, data) {
  const card = document.createElement("article");
  card.className = "summary-card";
  const title = document.createElement("h2");
  title.textContent = label;
  const value = document.createElement("p");
  value.className = "summary-card__value numeric";
  value.textContent = data?.[key] ?? "—";
  const unit = document.createElement("span");
  unit.className = "summary-card__unit";
  unit.textContent = "در انتظار اتصال API";
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
  summaryHeader.innerHTML = "<div><span>نمای سریع</span><h2>وضعیت مالی در یک نگاه</h2></div><small>مبالغ پس از اتصال Backend نمایش داده می‌شوند</small>";
  const summary = document.createElement("section");
  summary.className = "summary-grid";
  summary.setAttribute("aria-label", "خلاصه وضعیت مالی");
  SUMMARY_ITEMS.forEach(([key, label]) => summary.append(createSummaryCard(key, label, data)));

  const areasHeader = document.createElement("div");
  areasHeader.className = "section-heading";
  areasHeader.innerHTML = "<div><span>فضای کاری</span><h2>عملیات مالی پروژه</h2></div>";
  const areas = document.createElement("section");
  areas.className = "work-area-grid";
  areas.setAttribute("aria-label", "بخش‌های امور مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  fragment.append(intro, summaryHeader, summary, areasHeader, areas);
  return fragment;
}

export function createFinanceHomePage() {
  const state = createRequestState(REQUEST_STATUS.SUCCESS, Object.freeze({}));
  const root = document.createElement("div");
  root.replaceChildren(renderPageState(state, { renderContent: renderFinanceHome }));
  return root;
}
