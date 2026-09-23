import { element } from "../dom/elements.js";
import { formatDisplayNumber } from "../formatters/display.js";

/**
 * The trend a price is on, as the line and the word together.
 *
 * This lived inside the prices page, which meant the overview could only say
 * the direction in a chip and the two could drift — the table drawing a line
 * from the last six versions while the summary read a single field. It is one
 * function with two callers now, so whatever the table draws, the overview
 * draws.
 *
 * `history` is only the fallback, for a service that answers without
 * trendPoints. It is optional and read lazily, and both of those matter: the
 * prices page no longer fetches the history when it opens -- the list is
 * append-only and only grows, and this is the one thing that ever wanted it --
 * so it arrives as null until a reader asks to see it. This said as much
 * already while computing the fallback on every call regardless, which turned
 * that null into a TypeError and took the whole page down.
 */
function fallbackPoints(item, history) {
  return (history ?? [])
    .filter((price) => price.resourceId === item.resource.resourceId)
    .sort((left, right) => left.effectiveFrom.localeCompare(right.effectiveFrom) || left.sequence - right.sequence)
    .map((price) => ({ effectiveFrom: price.effectiveFrom, unitPriceIrr: price.unitPriceIRR }));
}

/**
 * @param onOpen  optional. When given AND the line has points to show, the whole cell
 *   becomes a real `<button>` that calls it with those points.
 *
 *   A BUTTON, not a handler on the SVG. A listener on the drawing is reachable by mouse
 *   and by nothing else: no tab stop, no Enter, no Space, nothing for a screen reader to
 *   announce. The element carries the same class and therefore the same grid, so the cell
 *   is laid out exactly as it was; only a cursor and a focus ring are added.
 *
 *   Callers that pass nothing get the div they always got, which is why the two other
 *   places drawing this sparkline are untouched.
 */
export function createPriceTrend(item, history, { onOpen = null } = {}) {
  const versions = (item.trend?.trendPoints ?? fallbackPoints(item, history))
    .filter((price) => /^\d+$/.test(String(price?.unitPriceIrr ?? "")))
    .slice(-6);
  const directionCode = item.trend?.trendDirection ?? (versions.length < 2 ? "none" : BigInt(versions.at(-1).unitPriceIrr) > BigInt(versions.at(-2).unitPriceIrr) ? "up" : BigInt(versions.at(-1).unitPriceIrr) < BigInt(versions.at(-2).unitPriceIrr) ? "down" : "flat");
  /* A cell with no line in it is not offered as a control, and the test is the same one
     that decides whether a line is drawn at all -- not merely whether any points arrived.
     Measured on this project when the two were allowed to differ: 50 cells became
     buttons and 49 of them drew «بدون سابقه», so a reader could tab to, focus and press
     forty-nine controls that did nothing at all. */
  if (!versions.length || directionCode === "none") {
    const empty = element("div", "price-trend");
    empty.append(element("span", "missing-value", "بدون سابقه"));
    return empty;
  }
  const interactive = typeof onOpen === "function";
  const container = interactive
    ? element("button", "price-trend price-trend--interactive")
    : element("div", "price-trend");
  const values = versions.map((price) => BigInt(price.unitPriceIrr));
  const minimum = values.reduce((result, value) => value < result ? value : result);
  const maximum = values.reduce((result, value) => value > result ? value : result);
  const range = maximum - minimum;
  const points = values.map((value, index) => {
    const x = versions.length === 1 ? 50 : Math.round((index * 100) / (versions.length - 1));
    const y = range === 0n ? 16 : 27 - Number(((value - minimum) * 22n) / range);
    return `${x},${y}`;
  }).join(" ");
  const direction = directionCode === "up" ? "افزایشی" : directionCode === "down" ? "کاهشی" : "بدون تغییر";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 32");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `روند ${direction} در ${formatDisplayNumber(String(versions.length))} نسخه قیمت`);
  const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  polyline.setAttribute("points", points);
  polyline.setAttribute("fill", "none");
  polyline.setAttribute("vector-effect", "non-scaling-stroke");
  svg.append(polyline);
  container.append(svg, element("small", `price-trend__label price-trend__label--${direction === "افزایشی" ? "up" : direction === "کاهشی" ? "down" : "flat"}`, direction));
  if (interactive) {
    container.type = "button";
    container.setAttribute("aria-haspopup", "dialog");
    /* The button says what pressing it does; the SVG inside keeps describing the shape.
       Both are needed: one is the control's name, the other the picture's. */
    container.setAttribute("aria-label",
      `نمایش جزئیات روند قیمت، ${direction}، ${formatDisplayNumber(String(versions.length))} نقطه`);
    container.title = "نمایش جزئیات روند قیمت";
    container.addEventListener("click", () => onOpen(versions));
  }
  return container;
}
