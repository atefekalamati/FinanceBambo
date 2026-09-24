import { element } from "../dom/elements.js";
import { formatBusinessDate } from "../formatters/display.js";
import { formatTomanFromIrr } from "../formatters/money.js";
import { showAccessibleDialog } from "./accessible-dialog.js";

/* The points behind a sparkline, read one at a time.
 *
 * A sparkline says «up» in the space of a thumbnail and that is its whole value — but it
 * is also the only place these figures appear, and a reader who wants to know WHEN a
 * price moved, or BY HOW MUCH, has nowhere to look. The shape of the line is not an
 * answer to either.
 *
 * WHY A CHART AND NOT A LIST
 * The first build of this put the points in a list. It was true and it was unreadable:
 * every row carried a date, an amount and a step, so five points filled a tall panel with
 * text and the SHAPE — the one thing the reader had just pressed — was nowhere in it. The
 * panel now shows the line itself and answers for exactly one point at a time: the date
 * above it, the amount below it. Three bands, each a fixed height, so the panel is the
 * same size for two points as for six and never scrolls.
 *
 * WHAT IT IS NOT
 * It is not a history view. It shows exactly the points the line was drawn from and
 * nothing else: the same array, the same order, no request of its own. A modal that
 * fetched its own data could disagree with the line above it, and the reader would have
 * no way to tell which was wrong.
 *
 * SEPARATE FROM THE DRAWING, DELIBERATELY
 * `trendRows` turns points into rows and knows nothing about the DOM; the dialog knows
 * nothing about where points come from. A resource price, a sheet observation and
 * whatever the next source turns out to be all arrive here as the same `{effectiveFrom,
 * unitPriceIrr}` pairs, so none of them needs its own version of this.
 */

/** An exact integer-rial string, or null for anything that is not one. */
function exact(value) {
  return /^\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

/**
 * The points as rows, oldest first, each carrying its step from the one before it.
 *
 * The order is the line's own and is never re-sorted: the caller built that array to
 * draw with, and a panel that disagreed with the picture above it would be worse than no
 * panel. Points that state no usable amount are dropped rather than shown as zero — the
 * line drops them too, for the same reason.
 *
 * BigInt throughout. A change of «۱۲۳٬۴۵۶٬۷۸۹ → ۱۲۳٬۴۵۶٬۷۹۰» is one rial, and a float
 * would lose it.
 */
export function trendRows(points) {
  const usable = (points ?? []).filter((point) => exact(point?.unitPriceIrr) !== null);
  return usable.map((point, index) => {
    const value = exact(point.unitPriceIrr);
    const before = index === 0 ? null : exact(usable[index - 1].unitPriceIrr);
    const change = before === null ? null : value - before;
    return {
      effectiveFrom: point.effectiveFrom ?? null,
      unitPriceIrr: String(value),
      /* Absent on the first row, because «no change» and «nothing to compare with» are
         different facts and only one of them is about the price. */
      changeIrr: change === null ? null : String(change < 0n ? -change : change),
      direction: change === null ? null : change > 0n ? "up" : change < 0n ? "down" : "flat",
    };
  });
}

/** Where the whole run ended up: first point against last, not the final step alone. */
export function overallDirection(rows) {
  if (!rows || rows.length < 2) return "none";
  const first = exact(rows[0].unitPriceIrr);
  const last = exact(rows[rows.length - 1].unitPriceIrr);
  if (first === null || last === null) return "none";
  return last > first ? "up" : last < first ? "down" : "flat";
}

export const DIRECTION_LABELS = Object.freeze({
  up: "افزایشی", down: "کاهشی", flat: "بدون تغییر", none: "بدون تغییر",
});

/** «۲۳ شهریور ۱۴۰۵», through the module's own formatter. A year is not a quantity. */
function dateText(value) {
  return value ? formatBusinessDate(value) : "—";
}

function stepText(row) {
  if (row.direction === null) return "اولین قیمت ثبت‌شده";
  if (row.direction === "flat") return "بدون تغییر";
  return `${row.direction === "up" ? "▲" : "▼"} ${formatTomanFromIrr(row.changeIrr)}`;
}

/* ─────────────────────────────── the drawing ─────────────────────────────── */

const SVG_NS = "http://www.w3.org/2000/svg";

/* One fixed coordinate system. The CSS box carries the same ratio, so the drawing fills
   it at every width without letterboxing and a dot stays a circle. */
const VIEW = Object.freeze({ width: 240, height: 84, padX: 16, padTop: 12, padBottom: 12 });
const PLOT_WIDTH = VIEW.width - VIEW.padX * 2;
const PLOT_HEIGHT = VIEW.height - VIEW.padTop - VIEW.padBottom;

/* `className` on an SVG element is read-only, so it is never assigned — `classList` is
   the one route that works on a real SVGElement and on the test document alike. */
function svgNode(tag, className, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  if (className) node.classList.add(...className.split(" ").filter(Boolean));
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
  return node;
}

/** Where each row sits in the fixed coordinate system above. */
function placements(rows) {
  const values = rows.map((row) => BigInt(row.unitPriceIrr));
  const lowest = values.reduce((result, value) => (value < result ? value : result));
  const highest = values.reduce((result, value) => (value > result ? value : result));
  const span = highest - lowest;
  return values.map((value, index) => {
    /* A run of identical prices has no span to scale against; it is drawn as the flat
       line it is, down the middle, rather than divided by zero. */
    const ratio = span === 0n ? 0.5 : Number(((value - lowest) * 1000n) / span) / 1000;
    return {
      x: Number((rows.length === 1
        ? VIEW.width / 2
        : VIEW.padX + (PLOT_WIDTH * index) / (rows.length - 1)).toFixed(2)),
      y: Number((VIEW.padTop + PLOT_HEIGHT * (1 - ratio)).toFixed(2)),
    };
  });
}

/**
 * The line, its points, and the one selection they share.
 *
 * Hover, click, Tab and the arrow keys all do the same thing — choose a point — because
 * they are one question asked four ways. The dots carry a roving tabindex rather than a
 * tab stop each: six data points should not cost six presses of Tab to walk past.
 */
function createTrendChart(rows, onSelect) {
  const box = element("div", "trend-detail__chart");
  const svg = svgNode("svg", "trend-detail__plot", {
    viewBox: `0 0 ${VIEW.width} ${VIEW.height}`,
    preserveAspectRatio: "none",
    role: "group",
    "aria-label": "نمودار روند قیمت",
  });
  const spots = placements(rows);
  const line = spots.map((spot) => `${spot.x},${spot.y}`).join(" ");

  svg.append(
    svgNode("polygon", "trend-detail__area", {
      points: `${spots[0].x},${VIEW.height - VIEW.padBottom} ${line} `
        + `${spots[spots.length - 1].x},${VIEW.height - VIEW.padBottom}`,
    }),
    svgNode("polyline", "trend-detail__line", { points: line, fill: "none" }));

  const guide = svgNode("line", "trend-detail__guide", {
    x1: spots[0].x, x2: spots[0].x, y1: VIEW.padTop - 4, y2: VIEW.height - VIEW.padBottom + 4,
  });
  svg.append(guide);

  const dots = spots.map((spot, index) => {
    const dot = svgNode("circle", "trend-detail__dot", { cx: spot.x, cy: spot.y, r: 3 });
    /* A dot small enough to read is too small to hit. The reachable target is a second,
       invisible circle over it — never smaller than the gap between two points, so no
       point is unreachable and none steals its neighbour's press. */
    const hit = svgNode("circle", "trend-detail__hit", {
      cx: spot.x, cy: spot.y, r: 13, tabindex: -1, role: "button",
      "aria-label": `${dateText(rows[index].effectiveFrom)}، `
        + `${formatTomanFromIrr(rows[index].unitPriceIrr)}`,
    });
    ["mouseenter", "click", "focus"].forEach((type) =>
      hit.addEventListener(type, () => select(index)));
    hit.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1, Home: -rows.length, End: rows.length }[event?.key];
      if (step === undefined) return;
      event.preventDefault?.();
      const next = Math.min(rows.length - 1, Math.max(0, index + step));
      select(next);
      dots[next].hit.focus();
    });
    /* The hit circle goes in FIRST so the dot paints over it and can be reached by the
       sibling selector that draws the focus ring; the dot takes no pointer events of its
       own, so the target underneath stays the only thing being pointed at. */
    svg.append(hit, dot);
    return { dot, hit };
  });

  let chosen = -1;
  function select(index) {
    if (index === chosen) return;
    chosen = index;
    dots.forEach((entry, position) => {
      entry.dot.classList.toggle("trend-detail__dot--on", position === index);
      /* Roving: exactly one dot is in the tab order, and it is the one being read. */
      entry.hit.setAttribute("tabindex", position === index ? "0" : "-1");
    });
    guide.setAttribute("x1", String(spots[index].x));
    guide.setAttribute("x2", String(spots[index].x));
    onSelect(rows[index], index);
  }

  box.append(svg);
  /* The newest point is the one the table was asking about, so the panel opens on it. */
  select(rows.length - 1);
  return box;
}

function emptyChart() {
  const box = element("div", "trend-detail__chart trend-detail__chart--empty");
  box.append(element("p", "trend-detail__empty",
    "برای این محصول هنوز قیمتی ثبت نشده که بتوان روندی از آن ساخت."));
  return box;
}

/* ─────────────────────────────── the panel ─────────────────────────────── */

/**
 * @param title   what this line is about, shown as the dialog's own heading
 * @param points  the exact array the sparkline was drawn from
 * @param onClose called after the dialog closes, whichever way it was closed
 */
export function createPriceTrendDetailDialog({ title, points, onClose }) {
  const dialog = element("dialog", "confirm-dialog trend-detail");
  dialog.setAttribute("aria-label", `جزئیات روند قیمت ${title ?? ""}`.trim());

  const rows = trendRows(points);
  const direction = overallDirection(rows);

  const close = element("button", "dialog-close trend-detail__close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن");
  close.addEventListener("click", () => dialog.close());
  const head = element("header", "trend-detail__head");
  head.append(
    element("h2", "trend-detail__title", title ?? "روند قیمت"),
    element("span", `trend-detail__overall trend-detail__overall--${direction}`,
            DIRECTION_LABELS[direction]),
    close);

  /* THE THREE BANDS. Each has a fixed height and is always present, so choosing a point
     changes the words in them and never the size of anything. */
  const dateBand = element("p", "trend-detail__date", "—");
  const amount = element("strong", "trend-detail__amount numeric", "—");
  const step = element("span", "trend-detail__step", "");
  const priceBand = element("p", "trend-detail__price");
  priceBand.append(amount, step);

  const chart = rows.length
    ? createTrendChart(rows, (row) => {
      dateBand.textContent = dateText(row.effectiveFrom);
      amount.textContent = formatTomanFromIrr(row.unitPriceIrr);
      step.textContent = stepText(row);
      step.className = `trend-detail__step trend-detail__step--${row.direction ?? "first"}`;
    })
    /* Reachable only if a caller opens this on a line with nothing to show. The trend
       cell does not offer the button in that state, so this is the second lock rather
       than the first. */
    : emptyChart();

  /* The content is one element so a click can tell the backdrop from the panel: a click
     landing on the dialog ITSELF only happens outside this wrapper. */
  const panel = element("div", "trend-detail__panel");
  panel.append(head, dateBand, chart, priceBand);
  dialog.append(panel);

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  /* Escape comes free from `showModal`, and the opener is refocused by
     `showAccessibleDialog`. Removal is ours: a dialog left in the document would
     accumulate one per open. */
  dialog.addEventListener("close", () => { dialog.remove(); onClose?.(); }, { once: true });

  return {
    element: dialog,
    open() {
      document.body.append(dialog);
      showAccessibleDialog(dialog, { initialFocus: close });
    },
  };
}
