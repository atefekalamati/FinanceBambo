import { element } from "../dom/elements.js";
import { formatBusinessDate } from "../formatters/display.js";

/**
 * The letterhead every document this module produces is printed under.
 *
 * The project already issues control reports on a band like this one, and a
 * financial report handed over next to one of those has to look like it came
 * from the same place. So the band is written once, here, and the four things
 * that can be printed — the built report, the period report, the issued
 * financial report and an invoice — all wear it. What changes between them is
 * the title and the facts underneath; the band never does.
 *
 * The mark is drawn inline rather than linked. The module is mounted inside the
 * host as well as served on its own, and a relative asset path resolves against
 * whichever page is showing it — a letterhead with a missing logo is worse than
 * one that carries its own.
 */

const MARK_PATH = "M125.1,60.8l-30.44-15.37v-25.7c0-1.16-.62-2.24-1.62-2.83L65.12.46c-1.04-.61-2.31-.61-3.34,0l-27.92,16.45c-1.01.58-1.62,1.67-1.62,2.83v18.77s6.58-3.26,6.58-3.26v-13.63s21.82-12.86,21.82-12.86v22.81S1.83,60.79,1.83,60.79C.71,61.35,0,62.49,0,63.73s.71,2.39,1.83,2.95l30.42,15.12v25.94c0,1.16.61,2.24,1.62,2.83l27.92,16.45c.51.3,1.09.46,1.67.46s1.15-.16,1.67-.46l27.92-16.45c1-.59,1.62-1.67,1.62-2.83v-18.33s-6.58,3.32-6.58,3.32v13.12s-20.86,12.29-20.86,12.29v-22.25s20.86-10.53,20.86-10.53h0s6.58-3.32,6.58-3.32h0s30.44-15.37,30.44-15.37c1.11-.56,1.81-1.7,1.81-2.94s-.7-2.38-1.81-2.94ZM10.68,63.73l21.57-10.72v21.43s-21.57-10.72-21.57-10.72ZM63.92,90.19l-18.52-9.2v7.34s15.24,7.57,15.24,7.57v22.8s-21.82-12.85-21.82-12.85v-20.79s0-7.35,0-7.35v-27.97s25.1-12.47,25.1-12.47l17.58,8.87v-7.37s-14.28-7.21-14.28-7.21V9.32s20.86,12.29,20.86,12.29v20.49s0,7.37,0,7.37v28.52s-24.16,12.2-24.16,12.2ZM94.66,74.67v-21.88s21.66,10.94,21.66,10.94l-21.66,10.94Z";

function brandMark() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 126.91 127.47");
  svg.setAttribute("class", "report-header__mark");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", MARK_PATH);
  path.setAttribute("fill", "currentColor");
  svg.append(path);
  return svg;
}

/**
 * `facts` are `[label, value]` pairs. A pair whose value is missing is dropped
 * rather than printed empty: a letterhead that says «تاریخ گزارش —» has told the
 * reader nothing and taken a line to do it.
 */
export function createReportHeader({ title, facts = [] }) {
  const header = element("header", "report-header");

  const brand = element("div", "report-header__brand");
  const wordmark = element("div", "report-header__wordmark");
  wordmark.append(
    element("strong", "", "بـامبـو"),
    element("small", "", "پلتفرم هوشمند"),
    element("small", "", "پـایش پـروژه"),
  );
  brand.append(wordmark, brandMark());

  const copy = element("div", "report-header__copy");
  copy.append(element("h1", "report-header__title", title));
  const list = element("dl", "report-header__facts");
  facts
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .forEach(([label, value]) => {
      const item = element("div");
      item.append(element("dt", "", `${label}:`), element("dd", "", String(value)));
      list.append(item);
    });
  if (list.childElementCount) copy.append(list);

  header.append(brand, copy);
  return header;
}

/** The facts every document repeats, in the order the control reports use. */
export function projectFacts({ project, snapshot, reportingDate, period } = {}) {
  return [
    ["پروژه", project?.name ?? null],
    ["کد", project?.code ?? null],
    ["نسخه پیشرفت", snapshot ?? null],
    ["تاریخ گزارش", reportingDate ? formatBusinessDate(reportingDate) : null],
    ["بازه", period?.from && period?.to ? `${formatBusinessDate(period.from)} تا ${formatBusinessDate(period.to)}` : null],
  ];
}
