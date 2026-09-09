import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { element } from "../../shared/dom/elements.js";
import { WORK_AREAS, createWorkAreaCard } from "./work-areas.js";

/**
 * بخش‌های گزارش مالی — the destinations, on a page of their own.
 *
 * The destinations that have no contextual entry point on the report overview.
 * It stays reachable from the bar at the top of that surface.
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
