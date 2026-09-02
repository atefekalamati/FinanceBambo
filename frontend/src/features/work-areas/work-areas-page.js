import { element } from "../../shared/dom/elements.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
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

  const header = element("header", "feature-header");
  const copy = element("div", "feature-header__copy");
  copy.append(
    element("span", "feature-header__eyebrow", "بخش‌های گزارش مالی"),
    element("h1", "", "گزارش‌ها و اسناد این پروژه"),
    element("p", "", "هر بخش، یک صفحه کامل با جدول‌ها و خروجی‌های خودش."),
  );
  const navigation = element("div", "feature-header__navigation");
  const back = element("a", "button button--ghost finance-back-link", `بازگشت به ${SURFACE_LABELS[SURFACES.REPORT]}`);
  back.href = `#${homeRouteFor(SURFACES.REPORT)?.path ?? "/finance-report"}`;
  navigation.append(back);
  header.append(copy, navigation);

  const areas = element("section", "work-area-grid");
  areas.setAttribute("aria-label", "بخش‌های گزارش مالی");
  WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

  root.append(header, areas);
  return root;
}
