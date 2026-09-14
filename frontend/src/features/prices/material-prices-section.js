import { element } from "../../shared/dom/elements.js";
import { formatBusinessDate, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";

/* «قیمت روز بازار» — the market prices imported from the material sheet.
 *
 * A separate section on the prices page rather than a page of its own, and separate from
 * «قیمت روز اقلام» above it for a reason that matters: those are Finance prices, which a
 * person decided and which invoices and reports are measured against. These are
 * OBSERVATIONS — what a supplier was quoting on a day. Showing them in the same column
 * would make an observation look like a decision, and the module would have no way back.
 *
 * WHAT THIS FILE REFUSES TO DO
 *
 *   * It never renders a zero for a missing price. Each of the four ways a price can be
 *     unusable gets its own Persian sentence, because "—" with no explanation sends the
 *     reader to ask somebody, and a zero sends them to the wrong conclusion.
 *   * It never computes a price. Conversion happens in the backend, where the factor and
 *     its provenance live; this only reports what was applied.
 *   * It fetches nothing from Google. Everything on screen came from the database.
 */

/** Why a price is not shown, in the reader's own language. */
const RESOLUTION_LABELS = Object.freeze({
  resolved: null,
  stale: "قیمت قدیمی است",
  unresolved_price: "قیمت خوانا نیست",
  unresolved_unit: "واحد تبدیل نشده",
  unmapped: "به قلم هزینه وصل نشده",
});

const RESOLUTION_CLASS = Object.freeze({
  resolved: "material-price__status--ok",
  stale: "material-price__status--stale",
  unresolved_price: "material-price__status--missing",
  unresolved_unit: "material-price__status--missing",
  unmapped: "material-price__status--missing",
});

const COLUMNS = Object.freeze([
  "نام محصول",
  "دسته",
  "منبع",
  "قیمت روز",
  "واحد",
  "تاریخ برگه",
  "وضعیت",
]);

/** The date a reader recognises: the sheet's own Jalali text when it stated one. */
export function sheetDateLabel(row) {
  if (row.workflowDateJalali) return row.workflowDateJalali;
  if (row.workflowDate) return formatBusinessDate(row.workflowDate);
  /* The cell was there and could not be read. Saying so is more useful than a blank,
     and far more useful than substituting today. */
  return row.workflowDateRaw ? `خوانا نشد: ${row.workflowDateRaw}` : "بدون تاریخ";
}

/** What to write in the price cell, and whether it is a real price at all. */
export function priceCell(row) {
  if (row.currentPriceIRR === null || row.currentPriceIRR === undefined) {
    /* No number, ever. The status column carries the reason. */
    return "—";
  }
  return formatTomanFromIrr(row.currentPriceIRR, { withCurrency: false });
}

/** The unit a price is quoted in, and what it was converted from if it was. */
export function unitCell(row) {
  const shown = row.displayUnit ?? row.sourceUnit;
  if (!shown) return "واحد اعلام نشده";
  if (!row.conversionFactor) return formatUnitLabel(shown);
  return `${formatUnitLabel(shown)} (تبدیل‌شده)`;
}

/** The status sentence, or an empty string when the price stands on its own. */
export function statusText(row) {
  /* `??` would be wrong here: RESOLUTION_LABELS.resolved is deliberately null, meaning
     "this price needs no explanation", and `??` treats that as "no entry" and falls back
     to the raw status -- which is how a healthy row came to be labelled "resolved" in
     Persian copy. `in` asks the question actually being asked: is this status known? */
  const known = Object.prototype.hasOwnProperty.call(RESOLUTION_LABELS, row.resolutionStatus);
  const label = known ? RESOLUTION_LABELS[row.resolutionStatus] : row.resolutionStatus;
  if (!label) return "";
  /* The backend's reason is appended when it has one: "واحد تبدیل نشده" tells the reader
     what kind of problem it is, and the reason tells them which two units. */
  return row.resolutionReason ? `${label} — ${row.resolutionReason}` : label;
}

function renderRow(row) {
  const tr = element("tr", "material-price__row");
  tr.append(
    element("td", "material-price__name", row.name),
    element("td", "", row.category),
    element("td", "", row.providerName),
    element("td", "numeric", priceCell(row)),
    element("td", "", unitCell(row)),
    element("td", "", sheetDateLabel(row)),
  );

  const status = element("td", "material-price__status");
  const text = statusText(row);
  if (text) {
    const badge = element("span", `material-price__badge ${RESOLUTION_CLASS[row.resolutionStatus] ?? ""}`, text);
    status.append(badge);
  } else {
    status.append(element("span", "material-price__badge material-price__status--ok", "به‌روز"));
  }
  tr.append(status);

  if (row.conversionNote) {
    /* A converted price that cannot be checked is a number nobody should trust. The note
       says exactly which factor was applied and in which direction. */
    tr.title = row.conversionNote;
  }
  return tr;
}

/**
 * The section, given rows the adapter already fetched.
 *
 * `rows` is whatever the database returned — possibly empty, possibly all unresolved.
 * There is no branch here that invents one.
 */
export function renderMaterialPrices(rows, { categories = [], selectedCategory = null,
                                             onSelectCategory = null } = {}) {
  const section = element("section", "prices-section material-prices");
  const heading = element("header", "prices-section__header");
  heading.append(element("h2", "", "قیمت روز بازار (برگه مصالح)"));
  heading.append(element("p", "prices-section__hint",
    "این قیمت‌ها مشاهده‌های وارد‌شده از برگه مصالح‌اند، نه قیمت رسمی مالی پروژه. "
    + "قیمت رسمی را یک نفر ثبت می‌کند و فاکتورها و گزارش‌ها با آن سنجیده می‌شوند."));
  section.append(heading);

  if (categories.length && onSelectCategory) {
    const filter = element("div", "material-prices__filters");
    const all = element("button", "app-chip" + (selectedCategory ? "" : " app-chip--active"), "همه");
    all.type = "button";
    all.addEventListener("click", () => onSelectCategory(null));
    filter.append(all);
    categories.forEach((category) => {
      const active = category.category === selectedCategory;
      const chip = element("button", "app-chip" + (active ? " app-chip--active" : ""),
        `${category.category} (${category.activeCount})`);
      chip.type = "button";
      chip.addEventListener("click", () => onSelectCategory(category.category));
      filter.append(chip);
    });
    section.append(filter);
  }

  if (!rows.length) {
    /* Empty is a real answer and says so. It is never filled with an example row. */
    section.append(element("p", "inline-notice",
      "هنوز هیچ قیمتی از برگه مصالح وارد نشده است. پس از اجرای درون‌ریزی، قیمت‌ها اینجا دیده می‌شوند."));
    return section;
  }

  const wrapper = element("div", "app-table-scroll");
  const table = element("table", "app-table material-prices__table");
  const caption = element("caption", "sr-only", "قیمت روز بازار به تفکیک محصول");
  const thead = element("thead", "");
  const headRow = element("tr", "");
  COLUMNS.forEach((label) => {
    const th = element("th", "", label);
    th.scope = "col";
    headRow.append(th);
  });
  thead.append(headRow);
  const tbody = element("tbody", "");
  rows.forEach((row) => tbody.append(renderRow(row)));
  table.append(caption, thead, tbody);
  wrapper.append(table);
  section.append(wrapper);

  const unresolved = rows.filter((row) => row.resolutionStatus !== "resolved").length;
  if (unresolved) {
    section.append(element("p", "prices-section__hint",
      `${unresolved} قلم از ${rows.length} قلم قیمت قابل استفاده ندارد. دلیل هر کدام در ستون وضعیت آمده است.`));
  }
  return section;
}
