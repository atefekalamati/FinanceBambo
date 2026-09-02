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
 * `history` is only the fallback: when the service answers with trendPoints
 * they are used, and the argument is never read.
 */
export function createPriceTrend(item, history) {
  const fallbackVersions = history.filter((price) => price.resourceId === item.resource.resourceId).sort((left, right) => left.effectiveFrom.localeCompare(right.effectiveFrom) || left.sequence - right.sequence);
  const versions = (item.trend?.trendPoints ?? fallbackVersions.map((price) => ({ effectiveFrom: price.effectiveFrom, unitPriceIrr: price.unitPriceIRR })))
    .filter((price) => /^\d+$/.test(String(price?.unitPriceIrr ?? "")))
    .slice(-6);
  const container = element("div", "price-trend");
  const directionCode = item.trend?.trendDirection ?? (versions.length < 2 ? "none" : BigInt(versions.at(-1).unitPriceIrr) > BigInt(versions.at(-2).unitPriceIrr) ? "up" : BigInt(versions.at(-1).unitPriceIrr) < BigInt(versions.at(-2).unitPriceIrr) ? "down" : "flat");
  if (!versions.length || directionCode === "none") {
    container.append(element("span", "missing-value", "بدون سابقه"));
    return container;
  }
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
  return container;
}
