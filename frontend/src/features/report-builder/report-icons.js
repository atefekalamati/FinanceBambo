const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * One line icon per report, in the host platform's own drawing.
 *
 * Its report chips carry a 24×24 stroked glyph above the label — 1.7 wide,
 * round caps, no fill — and the chip was reading as a placeholder here with a
 * letter in a tinted square standing in for one. These are the same shapes:
 * a document for a summary, a rising bar for a trend, a clock for a period, a
 * receipt for invoices, a tag for prices, a warning triangle for the quality
 * notes.
 *
 * A key with no glyph gets the generic document rather than nothing, so adding
 * a report to the catalogue never leaves a chip empty.
 */

const PATHS = Object.freeze({
  /* خلاصه وضعیت مالی — a sheet with its corner turned */
  overview: ["M6 3h9l4 4v14H6z", "M15 3v4h4"],
  /* انحراف پیش‌بینی — a needle off centre */
  deviation: ["M12 3v4", "M12 17v4", "M3 12h4", "M17 12h4", "M15.5 8.5 9 15"],
  /* روند ماهانه — bars rising to a baseline */
  monthly: ["M4 20V10", "M10 20V4", "M16 20v-7", "M21 20H3"],
  /* انحراف قیمت — a price tag */
  priceVariance: ["M20.6 13.4 12 22l-9-9V3h10z", "M8 8h.01"],
  /* انحراف مقدار — stacked measures */
  quantityVariance: ["M3 6h18", "M3 12h12", "M3 18h7"],
  /* فهرست فاکتورها — a receipt */
  invoices: ["M6 2h12v20l-3-2-3 2-3-2-3 2z", "M9 7h6", "M9 11h6"],
  /* تاریخچه تغییرات — a clock turned back */
  auditEvents: ["M12 7v5l3 2", "M3.5 12a8.5 8.5 0 1 0 2.6-6.1", "M3 4v4h4"],
  /* هشدارهای کیفیت — a warning triangle */
  warnings: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"],
  /* جدول قیمت‌ها — a tag with rows */
  prices: ["M4 5h16v14H4z", "M4 10h16", "M9 5v14"],
  /* اقلام و برآورد — a checklist */
  estimateLines: ["M5 4h14v16H5z", "M8 8h8", "M8 12h8", "M8 16h5"],
  /* منحنی S — a curve climbing */
  sCurve: ["M3 19c4 0 5-14 9-14s6 10 9 10", "M3 21h18"],
  /* یک سطر خلاصه، بی‌ایراد — a tick */
  check: ["M4 12.5l5 5L20 6.5"],
  /* یک سطر خلاصه، هشدار — a bang */
  alert: ["M12 7.5v5.5", "M12 16.5h.01"],
  /* گزارش سطح ۱ — a hierarchy */
  levelOne: ["M12 3v4", "M6 21v-6", "M18 21v-6", "M6 15h12v-4H6z", "M12 7v4"],
  /* A measured square: the outline and two corner brackets. Deliberately not a
     line of any kind — on a page of charts, a stroke that rises or falls reads
     as data whatever it was drawn for. */
  area: ["M4 4h16v16H4z", "M4 14h6v6", "M14 4h6v6"],
});

const FALLBACK = PATHS.overview;

/* The overview's large watermarks have their own 64px drawings. They stay out
   of PATHS so replacing a summary-card icon cannot also replace the smaller
   report-builder or navigation version of the same concept. */
const SUMMARY_ICONS = Object.freeze({
  estimateCalculator: [
    ["path", { d: "M12 7H35L44 16V35" }],
    ["path", { d: "M35 7V16H44" }],
    ["path", { d: "M12 7V51H30" }],
    ["path", { d: "M19 23H35" }],
    ["path", { d: "M19 30H32" }],
    ["path", { d: "M19 37H27" }],
    ["rect", { x: "31", y: "32", width: "22", height: "25", rx: "4" }],
    ["rect", { x: "36", y: "37", width: "12", height: "5", rx: "1" }],
    ["path", { d: "M37 47H39" }],
    ["path", { d: "M45 47H47" }],
    ["path", { d: "M37 52H39" }],
    ["path", { d: "M45 52H47" }],
  ],
  registeredCost: [
    ["rect", { x: "7", y: "14", width: "42", height: "29", rx: "5" }],
    ["path", { d: "M7 23H49" }],
    ["path", { d: "M14 34H24" }],
    ["circle", { cx: "47", cy: "44", r: "11", fill: "#12611d81", stroke: "none" }],
    ["circle", { cx: "47", cy: "44", r: "11" }],
    ["path", { d: "M42 44L46 48L53 40" }],
  ],
  /* هزینه کار باقی‌مانده: the climb still to be made, the flag at the top of it,
     and the stack of coins it will take.

     Drawn for a 64 viewBox like its neighbours. The source drawing carried a
     gradient, a glow filter and its own stroke weight; none of them came with
     it. The mark is one of four on a row of cards and has to read as their
     texture rather than as a picture: colour is the card's own
     `--summary-mark`, inherited through `currentColor` on the group, and the
     weight is the 2.8 every summary icon shares. The flag is the one filled
     shape, and it fills with the same currentColor at a third opacity rather
     than a literal, so it follows the theme with everything around it. */
  remainingWork: [
    ["path", { d: "M9 48H20C21.7 48 23 46.7 23 45V39C23 37.3 24.3 36 26 36H34C35.7 36 37 34.7 37 33V27C37 25.3 38.3 24 40 24H42" }],
    ["path", { d: "M42 32V11" }],
    ["path", { d: "M42 12L53 17L42 22V12Z", fill: "currentColor", "fill-opacity": "0.35" }],
    ["ellipse", { cx: "51", cy: "35", rx: "7.5", ry: "3.2" }],
    ["path", { d: "M43.5 35V44C43.5 45.8 46.9 47.3 51 47.3C55.1 47.3 58.5 45.8 58.5 44V35" }],
    ["path", { d: "M43.5 39.5C43.5 41.3 46.9 42.8 51 42.8C55.1 42.8 58.5 41.3 58.5 39.5" }],
  ],
});

function appendSummaryIcon(icon, nodes) {
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("stroke", "currentColor");
  group.setAttribute("stroke-width", "2.8");
  group.setAttribute("stroke-linecap", "round");
  group.setAttribute("stroke-linejoin", "round");
  nodes.forEach(([tag, attributes]) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    group.append(node);
  });
  icon.append(group);
}

export function reportIcon(key) {
  const icon = document.createElementNS(SVG_NS, "svg");
  const summaryIcon = SUMMARY_ICONS[key];
  icon.setAttribute("viewBox", summaryIcon ? "0 0 64 64" : "0 0 24 24");
  icon.setAttribute("fill", "none");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  if (summaryIcon) {
    appendSummaryIcon(icon, summaryIcon);
    return icon;
  }
  (PATHS[key] ?? FALLBACK).forEach((d) => {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    icon.append(path);
  });
  return icon;
}

/**
 * The chevrons the host draws beside a category row and on the way back.
 *
 * `forward` is the one on a tile — it points the way the reader is going, which
 * on an RTL page is to the left. `back` is its mirror. They are stroked glyphs
 * rather than the `‹` and `›` characters that stood here before: those are drawn
 * by whichever font answers for them, so their weight never matched the rest of
 * the icons and their direction was at the mercy of the bidi algorithm.
 */
export function chevronIcon(direction = "forward") {
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", direction === "back" ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6");
  icon.append(path);
  return icon;
}

/** The filled star the host puts before a «هوشمند» heading and on its build button. */
export function sparkIcon() {
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M12 2l1.8 4.9L19 8.7l-4 3.4 1.2 5.2L12 14.7 7.8 17.3 9 12.1 5 8.7l5.2-1.8z");
  icon.append(path);
  return icon;
}
