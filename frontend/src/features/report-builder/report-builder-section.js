import { element } from "../../shared/dom/elements.js";
import { featuredReports } from "./report-catalog.js";
import { openReportBuilder } from "./report-builder-dialog.js";
import { reportIcon, sparkIcon } from "./report-icons.js";

/**
 * The report builder's place on the overview.
 *
 * A section of its own rather than a card among the work areas, because it is
 * not somewhere to go — it is something to do with what is already on the page.
 * The chips are the reports people reach for most; each opens the full chooser
 * with that one already ticked, so the common case is two clicks and the whole
 * catalogue is still one click away.
 */
export function createReportBuilderSection({ onBuild }) {
  const section = element("section", "report-builder-section");
  section.setAttribute("aria-labelledby", "report-builder-section-title");

  const head = element("div", "report-builder-section__head");
  const title = element("h2", "report-builder-section__title");
  title.id = "report-builder-section-title";
  const star = sparkIcon();
  star.setAttribute("class", "report-builder-panel__star");
  title.append(star, document.createTextNode(" گزارش‌ساز هوشمند"));
  const info = element("span", "report-builder-panel__info", "i");
  info.setAttribute("role", "img");
  info.setAttribute("aria-label", "راهنما");
  info.title = "هر بخشی که انتخاب کنید یک فصل شماره‌دار از سند نهایی می‌شود.";
  head.append(title, info);

  const lead = element("p", "maker-sub report-builder-section__lead", "گزارش اختصاصی خود را با انتخاب بخش‌های موردنیاز بسازید.");

  const grid = element("div", "chips report-builder-section__grid");
  featuredReports().forEach((report) => {
    const chip = element("button", "chip report-builder-chip");
    chip.type = "button";
    chip.title = report.summary;
    const icon = reportIcon(report.key);
    icon.setAttribute("class", "report-builder-chip__icon");
    chip.append(icon);
    chip.append(element("span", "report-builder-chip__label", report.title));
    chip.addEventListener("click", () => openReportBuilder({ preselected: [report.key], onBuild }));
    grid.append(chip);
  });

  const cta = element("button", "app-btn maker-btn button button--primary report-builder-section__cta");
  cta.type = "button";
  const ctaStar = sparkIcon();
  ctaStar.setAttribute("class", "report-builder-panel__star");
  cta.append(ctaStar, document.createTextNode(" ساخت گزارش اختصاصی"));
  cta.addEventListener("click", () => openReportBuilder({ preselected: [], onBuild }));

  /* The host's own nesting: a card body, and a compact block inside it holding
     the line of text, the chips and the button. Both wrappers are
     `display: contents` in CSS, so the three keep the section's own grid and
     nothing about the layout moved — the structure is here for when the body
     wants a box of its own, not instead of what is drawn today. */
  const body = element("div", "dash-card__body maker-body");
  const compact = element("div", "maker-body--compact");
  compact.append(lead, grid, cta);
  body.append(compact);

  section.append(head, body);
  return section;
}
