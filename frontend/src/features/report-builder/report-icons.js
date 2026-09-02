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
  /* ترکیب هزینه — a ring divided */
  breakdown: ["M12 3a9 9 0 1 0 9 9h-9z", "M14 3.3A9 9 0 0 1 20.7 10H14z"],
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
});

const FALLBACK = PATHS.overview;

export function reportIcon(key) {
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
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
