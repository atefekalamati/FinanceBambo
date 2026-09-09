import { element } from "../../shared/dom/elements.js";

/**
 * The report surface's destinations, and the card that opens one.
 *
 * This page only carries destinations that have no direct entry point on the
 * report overview. Level-one, invoices, prices and display settings already
 * have contextual links beside their own summaries there, so duplicating them
 * here creates two navigation choices without adding reachability.
 */

export const WORK_AREAS = Object.freeze([
  { key: "reports", title: "گزارش وضعیت مالی", description: "گزارش به‌روز پروژه، انحراف قیمت و مقدار، و ثبت گزارش تثبیت‌شده", meta: "گزارش به‌روز · انحرافات · چاپ", href: "#/reports" },
  { key: "period-report", title: "گزارش دوره‌ای", description: "ساخت گزارش برای یک بازه زمانی دلخواه با خروجی چاپ و CSV", meta: "بازه دلخواه · مقایسه · خروجی", href: "#/period-report" },
  { key: "report-items", title: "جدول اقلام و برآورد", description: "ریز برآورد هر فعالیت، مقدار اولیه و آخرین مقدار اصلاح‌شده، با خروجی اکسل", meta: "فقط‌خواندنی · خروجی اکسل", href: "#/report-items" },
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
