import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";

/**
 * The shape of a produced report, copied from the control-project documents the
 * dashboard already issues: a cover band carrying the project and the snapshot
 * it was built from, numbered sections, and a footer that says when it was made.
 *
 * A reader who receives one of these next to one of those should not have to
 * work out that they are the same kind of document. Only the contents differ —
 * these are about money.
 */

export function reportCover({ title, project, snapshot, reportingDate, period }) {
  const cover = element("header", "report-doc__cover");
  const brand = element("div", "report-doc__brand");
  brand.append(element("strong", "", "بامبو"), element("small", "", "گزارش مالی پروژه"));

  const copy = element("div", "report-doc__cover-copy");
  copy.append(element("h1", "", title));
  const facts = element("dl", "report-doc__cover-facts");
  const add = (label, value) => {
    if (!value) return;
    const item = element("div");
    item.append(element("dt", "", label), element("dd", "", value));
    facts.append(item);
  };
  add("پروژه", project?.name ?? null);
  add("کد", project?.code ?? null);
  add("نسخه پیشرفت", snapshot?.label ?? null);
  add("تاریخ گزارش", reportingDate ? formatBusinessDate(reportingDate) : null);
  add("بازه", period ? `${formatBusinessDate(period.from)} تا ${formatBusinessDate(period.to)}` : null);
  copy.append(facts);

  cover.append(copy, brand);
  return cover;
}

/**
 * A numbered section, exactly as the documents number theirs. The number is the
 * position in this document, not an identity of the report — the same report
 * carries a different number when it is chosen alongside different ones.
 */
export function reportSection(index, title, description = "") {
  const section = element("section", "report-doc__section");
  const heading = element("h2", "report-doc__section-title");
  heading.append(
    element("span", "report-doc__section-number", `${formatDisplayNumber(String(index))} —`),
    document.createTextNode(` ${title}`),
  );
  section.append(heading);
  if (description) section.append(element("p", "report-doc__section-note", description));
  return section;
}

export function reportFooter(generatedAt) {
  const footer = element("footer", "report-doc__footer");
  footer.textContent = `بامبو — گزارش مالی پروژه · تولیدشده در ${formatSystemDateTime(generatedAt)}`;
  return footer;
}

/**
 * A table in the documents' own shape. `rows` are already-formatted cells: this
 * builds the frame, never the arithmetic, so no number is rounded on its way to
 * the page by a helper that does not know what it is looking at.
 */
export function reportTable({ caption, columns, rows, empty = "برای این بخش داده‌ای ثبت نشده است." }) {
  const wrapper = element("div", "table-scroll report-doc__table-wrapper");
  const table = element("table", "data-table report-doc__table");
  table.append(tableCaption(caption), tableHead(columns.map((column) => column.label)));
  const body = document.createElement("tbody");
  if (!rows.length) {
    const record = document.createElement("tr");
    const cell = element("td", "report-doc__table-empty", empty);
    cell.colSpan = columns.length;
    record.append(cell);
    body.append(record);
  }
  rows.forEach((row) => {
    const record = document.createElement("tr");
    columns.forEach((column, index) => {
      const value = row[index];
      const cell = element("td", column.numeric ? "numeric" : "");
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value ?? "—";
      record.append(cell);
    });
    body.append(record);
  });
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

/** The figure cards the documents open with. */
export function reportFigures(figures) {
  const grid = element("div", "report-doc__figures");
  figures.forEach(({ label, value, note }) => {
    const card = element("article", "report-doc__figure");
    card.append(element("strong", "report-doc__figure-value", value));
    card.append(element("span", "report-doc__figure-label", label));
    if (note) card.append(element("small", "report-doc__figure-note", note));
    grid.append(card);
  });
  return grid;
}

/**
 * A horizontal plan-against-actual bar, the shape the level-1 document uses.
 * Both series share one scale so the rows stay comparable, and a row whose
 * baseline is unknown says so instead of drawing a bar of nothing.
 */
export function reportComparisonChart({ rows, ariaLabel }) {
  const chart = element("div", "report-doc__chart");
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", ariaLabel);
  rows.forEach((row) => {
    const line = element("article", "report-doc__chart-row");
    line.append(element("h3", "", row.label));
    const bars = element("div", "report-doc__chart-bars");
    [["plan", row.planMagnitude], ["actual", row.actualMagnitude]].forEach(([series, magnitude]) => {
      const track = element("div", "report-doc__chart-track");
      if (magnitude !== null && magnitude !== undefined) {
        const bar = element("span", `report-doc__chart-bar report-doc__chart-bar--${series} chart-mark`);
        bar.style.setProperty("--bar-width", `${magnitude}%`);
        track.append(bar);
      }
      bars.append(track);
    });
    line.append(bars, element("span", "report-doc__chart-value numeric", row.valueText));
    chart.append(line);
  });
  return chart;
}
