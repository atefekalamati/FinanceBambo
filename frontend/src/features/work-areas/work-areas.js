import { element } from "../../shared/dom/elements.js";

/**
 * The report surface's destinations, and the card that opens one.
 *
 * They used to sit at the foot of the overview. The overview is now a dashboard
 * of figures, so the destinations moved to a page of their own reached from the
 * bar at the top — the same list, the same cards, somewhere they do not compete
 * with the charts for the reader's first screen.
 */

export const WORK_AREAS = Object.freeze([
  { key: "reports", title: "گزارش وضعیت مالی", description: "گزارش به‌روز پروژه، انحراف قیمت و مقدار، و ثبت گزارش تثبیت‌شده", meta: "گزارش به‌روز · انحرافات · چاپ", href: "#/reports" },
  { key: "period-report", title: "گزارش دوره‌ای", description: "ساخت گزارش برای یک بازه زمانی دلخواه با خروجی چاپ و CSV", meta: "بازه دلخواه · مقایسه · خروجی", href: "#/period-report" },
  { key: "level-one", title: "گزارش مالی سطح ۱", description: "هزینه هر مرحله از ساختار پروژه در برابر برآورد آن، با جزئیات سطح ۲ و اقلام", meta: "مراحل · سطح ۲ · اقلام", href: "#/level-one" },
  { key: "invoices", title: "ثبت و مشاهده فاکتورها", description: "ثبت فاکتور و مشاهده فهرست، وضعیت، فروشنده، مبلغ و جزئیات خطوط", meta: "ثبت · فهرست · وضعیت", href: "#/invoices" },
  { key: "report-prices", title: "جدول قیمت‌ها", description: "قیمت پایه سازمان، قیمت اختصاصی پروژه و قیمت روز هر قلم، با خروجی اکسل", meta: "فقط‌خواندنی · خروجی اکسل", href: "#/report-prices" },
  { key: "report-items", title: "جدول اقلام و برآورد", description: "ریز برآورد هر فعالیت، مقدار اولیه و آخرین مقدار اصلاح‌شده، با خروجی اکسل", meta: "فقط‌خواندنی · خروجی اکسل", href: "#/report-items" },
  { key: "report-settings", title: "تنظیمات نمایش", description: "واحد نمایش مبالغ و فهرست دسترسی‌های مالی این حساب", meta: "واحد مبلغ · دسترسی‌ها", href: "#/report-settings" },
]);

export function createWorkAreaCard(area) {
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
