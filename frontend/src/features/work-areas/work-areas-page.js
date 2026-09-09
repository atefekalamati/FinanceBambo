import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { element } from "../../shared/dom/elements.js";
import { WORK_AREAS, createWorkAreaCard } from "./work-areas.js";

/**
 * بخش‌های گزارش مالی — the destinations, on a page of their own.
 *
 * Nothing here is new. It is the list that used to close the overview, moved so
 * the overview can be a dashboard: the same cards, the same links, reached from
 * the bar at the top of the report surface.
 */
export function createWorkAreasPage() {
  const root = element("div", "work-areas-page");

  const header = createFinancePageHeader("گزارش‌ها و اسناد این پروژه");

  const areas = element("section", "work-area-grid");
  areas.setAttribute("aria-label", "بخش‌های گزارش مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  root.append(header, areas);
  return root;
}
