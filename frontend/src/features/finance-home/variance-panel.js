import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";

/**
 * The deepest few deviations, and a way to the table that holds them all.
 *
 * Parked: the overview does not show it while the owner decides what belongs on
 * the board. It is a whole component, not a fragment — wiring it back is one
 * import and one append, with `rollupPriceVariances` / `rollupQuantityVariances`
 * supplying the rows as they did before.
 */

export /**
 * The rows lead to this surface's own tables, which are read-only whoever opens
 * them. They used to lead into the price and item editors on امور مالی — a link
 * that worked for an administrator and was a way straight past the split for
 * everyone else.
 */
/**
 * The deepest few deviations, and a way to the table that holds them all.
 *
 * `limit` is how many the card has room for, not how many there are. The link
 * under it goes to the full table either way.
 */
function createVariancePanel(title, rows, valueKey, valueFormatter, baseHref, limit = 5) {
  const section = document.createElement("section");
  section.className = "finance-analysis-card finance-variance-card";
  const heading = document.createElement("h2");
  heading.textContent = title;
  section.append(heading);
  if (!rows?.length) {
    const empty = document.createElement("p");
    empty.className = "finance-analysis-card__empty";
    empty.textContent = "برای این تحلیل هنوز داده معتبری ثبت نشده است.";
    section.append(empty);
    return section;
  }
  const list = document.createElement("ol");
  rows.slice(0, limit).forEach((row) => {
    const item = document.createElement("li");
    const link = document.createElement(baseHref ? "a" : "div");
    link.className = "finance-variance-card__link";
    if (baseHref) {
      const target = new URLSearchParams();
      if (row.resourceId) target.set("resourceId", row.resourceId);
      if (row.estimateLineId) target.set("estimateLineId", row.estimateLineId);
      link.href = `${baseHref}${target.size ? `?${target.toString()}` : ""}`;
      link.setAttribute("aria-label", `${row.resourceTitle || row.resourceCode || "قلم هزینه بدون عنوان"}؛ مشاهده جزئیات ${title}`);
    }
    const identity = document.createElement("span");
    identity.textContent = row.resourceTitle || row.resourceCode || "قلم هزینه بدون عنوان";
    const value = document.createElement("strong");
    value.className = "numeric";
    value.textContent = valueFormatter(row[valueKey]);
    link.append(identity, value);
    // The chevron promises somewhere to go. A row that is not a link keeps the
    // column so the rows stay aligned, and keeps it empty.
    const indicator = document.createElement("span");
    indicator.className = "finance-variance-card__indicator";
    indicator.setAttribute("aria-hidden", "true");
    if (baseHref) indicator.textContent = "‹";
    link.append(indicator);
    item.append(link);
    list.append(item);
  });
  section.append(list);
  return section;
}

