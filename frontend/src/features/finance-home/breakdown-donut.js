import { element } from "../../shared/dom/elements.js";
import { formatCompactMoneyFromIrr, formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";

/**
 * ترکیب هزینه as a summary — a ring of the actual cost per kind of item, and a
 * way into the full comparison.
 *
 * It draws only what `buildBulletPresentation` already worked out for the full
 * chart; there is no second arithmetic here and no second source. The ring is a
 * proportion of a total, so the segments are shares of the sum of the same
 * actual figures the full section lists.
 *
 * Parked: the overview does not show it while the owner decides what belongs on
 * the board. Wiring it back is one import and one append.
 *
 * The whole card is one link. A donut that only responds to a click on the ring
 * leaves the legend, the centre figure and the heading inert, and none of that
 * is reachable from a keyboard.
 */

/* Four segments, all from tokens the platform already defines. The last two
   named --chart-amber and --chart-violet, which are declared nowhere: they only
   ever drew their own fallbacks, so the ring's first half followed the theme and
   its second half did not. */
const SEGMENT_COLORS = Object.freeze([
  "var(--dash-actual)",
  "var(--dash-plan)",
  "var(--dash-sev-med)",
  "var(--dash-sev-high)",
]);

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

/** Exact share as a string percentage — no float touches money. */
function sharePercent(part, whole) {
  if (whole <= 0n) return null;
  const scaled = (part * 1000n) / whole;
  const units = scaled / 10n;
  const tenths = scaled % 10n;
  return tenths === 0n ? String(units) : `${units}.${tenths}`;
}

export function createBreakdownDonut({ view, href = "#/reports" }) {
  const card = element("a", "overview-card breakdown-donut");
  card.href = href;

  const head = element("header", "overview-card__head");
  head.append(element("h2", "overview-card__title", "ترکیب هزینه"));
  head.append(element("span", "overview-card__link", "جزئیات"));
  card.append(head);

  const segments = (view?.rows ?? [])
    .map((row) => ({ label: row.label, amount: exactInteger(row.actualCostIrr) ?? 0n }))
    .filter((row) => row.amount > 0n)
    .sort((left, right) => (right.amount > left.amount ? 1 : right.amount < left.amount ? -1 : 0));
  const total = segments.reduce((result, row) => result + row.amount, 0n);

  card.setAttribute("aria-label", total > 0n
    ? `ترکیب هزینه، مجموع ${formatTomanFromIrr(String(total))} — رفتن به جزئیات`
    : "ترکیب هزینه — رفتن به جزئیات");

  if (!segments.length || total === 0n) {
    card.append(element("p", "inline-notice", "هنوز هزینه‌ای برای ترکیب هزینه ثبت نشده است."));
    return card;
  }

  const figure = element("div", "breakdown-donut__figure");
  const ring = element("div", "breakdown-donut__ring");
  // One conic gradient built from running shares: the ring is a proportion, and
  // a stack of arcs would need the same numbers computed twice.
  let cursor = 0;
  const stops = segments.map((row, index) => {
    const share = Number((row.amount * 10000n) / total) / 100;
    const from = cursor;
    cursor = index === segments.length - 1 ? 100 : cursor + share;
    return `${SEGMENT_COLORS[index % SEGMENT_COLORS.length]} ${from}% ${cursor}%`;
  });
  // The arc carries the mask that cuts the hole. A mask applies to an element's
  // children too, so the figure in the middle is its sibling, not its child —
  // inside it, it would be cut away along with the centre of the ring.
  const arc = element("div", "breakdown-donut__arc");
  arc.style.setProperty("--ring", `conic-gradient(${stops.join(", ")})`);
  ring.append(arc);
  const centre = element("div", "breakdown-donut__centre");
  centre.append(
    element("strong", "numeric", formatCompactMoneyFromIrr(String(total))),
    element("span", "", "هزینه واقعی"),
  );
  ring.append(centre);
  figure.append(ring);

  const legend = element("ul", "breakdown-donut__legend");
  segments.forEach((row, index) => {
    const item = document.createElement("li");
    const swatch = element("i", "breakdown-donut__swatch");
    swatch.style.setProperty("--swatch", SEGMENT_COLORS[index % SEGMENT_COLORS.length]);
    item.append(
      swatch,
      element("span", "breakdown-donut__label", row.label),
      element("span", "breakdown-donut__share numeric", `${formatDisplayNumber(sharePercent(row.amount, total))}٪`),
    );
    legend.append(item);
  });

  figure.append(legend);
  card.append(figure);
  return card;
}
