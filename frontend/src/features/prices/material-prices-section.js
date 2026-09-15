import { element } from "../../shared/dom/elements.js";
import { formatBusinessDate, formatDisplayNumber, formatUnitLabel } from "../../shared/formatters/display.js";
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

/* Why a price is not shown, in the reader's own language.
 *
 * Nine rather than five, and the extra four are not pedantry: each needs a different
 * person to do a different thing. `missing_factor` needs somebody to weigh the product.
 * `incompatible_unit` needs somebody to choose a different target unit. `invalid_source`
 * needs the sheet fixed. `unresolved_mapping` needs an approval. Collapsing them into
 * "no price" would tell every one of those people the same useless thing. */
const RESOLUTION_LABELS = Object.freeze({
  resolved: null,
  stale: "قیمت قدیمی است",
  unresolved_price: "قیمت خوانا نیست",
  unresolved_unit: "واحد اعلام نشده",
  incompatible_unit: "واحدها با هم سازگار نیستند",
  missing_factor: "ضریب تبدیل این کالا ثبت نشده",
  unresolved_mapping: "اتصال به قلم هزینه تأیید نشده",
  invalid_source: "ردیف منبع نامعتبر است",
  inactive: "غیرفعال",
});

const RESOLUTION_CLASS = Object.freeze({
  resolved: "material-price__status--ok",
  stale: "material-price__status--stale",
  unresolved_price: "material-price__status--missing",
  unresolved_unit: "material-price__status--missing",
  incompatible_unit: "material-price__status--missing",
  missing_factor: "material-price__status--action",
  unresolved_mapping: "material-price__status--action",
  invalid_source: "material-price__status--missing",
  inactive: "material-price__status--muted",
});

/* What the schedule says, against what the price is in. A verdict the backend reached;
   nothing here recomputes it. */
const ALIGNMENT_LABELS = Object.freeze({
  not_mapped: "وصل نشده",
  missing_finance_unit: "واحد قلم هزینه ثبت نشده",
  aligned: "هم‌واحد",
  convertible: "قابل تبدیل",
  needs_factor: "نیازمند ضریب",
  unresolved: "—",
});

/* The columns when no single category is chosen.
 *
 * A mixed table cannot show per-category measurements -- an angle's «تعداد شاخه» over a
 * brick row would be an empty cell pretending to be missing data -- so the all-categories
 * view shows only what every worksheet supplies, plus which category each row came from.
 * Choosing a category is what reveals that worksheet's own columns. */
const ALL_CATEGORIES_COLUMNS = Object.freeze([
  { key: "source", label: "منبع", kind: "base" },
  { key: "product", label: "محصول", kind: "base" },
  { key: "categoryLabel", label: "دسته", kind: "base" },
  { key: "price", label: "قیمت", kind: "base", numeric: true },
  { key: "workflowDate", label: "تاریخ آپدیت ورک فلو", kind: "base" },
  { key: "productId", label: "productId", kind: "base" },
]);

/**
 * The table this view should show, declared by the Backend for the chosen category.
 *
 * The page holds no per-category column list of its own, and that is the whole point: a
 * second copy would drift, and the first symptom would be a column from one worksheet
 * rendered over another worksheet's rows. `/material-prices/categories` publishes each
 * category's columns; this picks the one selected and falls back to the shared set only
 * when no category is chosen.
 */
export function columnsFor(selectedCategory, categories) {
  if (!selectedCategory) return [...ALL_CATEGORIES_COLUMNS];
  const declared = (categories ?? []).find((c) => c.category === selectedCategory);
  /* A category the Backend published no schema for shows the shared columns rather than
     nothing: the prices are real and worth seeing even before somebody declares which of
     that worksheet's columns are meaningful. */
  return declared?.columns?.length ? declared.columns : [...ALL_CATEGORIES_COLUMNS];
}

/** One cell's text, by where the column says its value lives. */
export function cellValue(column, row, categoryLabels = {}) {
  if (column.kind === "spec") {
    /* From the worksheet. A blank cell is an em dash, never a zero: the sheet said
       nothing, and nothing is not none. */
    const value = (row.specs ?? {})[column.key];
    if (value === null || value === undefined || value === "") return "—";
    /* `numeric` is the BACKEND saying a reader may treat this cell as a number, and it
       is the only thing that licenses reformatting it. Grouped and in Persian digits it
       reads as «۳۶۴٬۵۰۰» beside the price above it, instead of «364500.0» -- Latin
       digits and a float tail the sheet's own cell carried, sitting in an RTL table
       where every other figure is grouped.

       A column the backend does NOT call numeric travels verbatim, because «۶ متر» is a
       sentence and «۶۰*۶۰*۵» is a size, and formatting either would be reading them as
       quantities they are not. */
    return column.numeric ? formatDisplayNumber(value) : String(value);
  }
  switch (column.key) {
    case "source": return row.providerName ?? "—";
    /* The label a person wrote wins the name, because they wrote it precisely because the
       supplier's own name was not usable. What the sheet said stays in the row's title. */
    case "product": return row.labelDisplayName || row.label || row.name || "—";
    case "categoryLabel": return categoryLabels[row.category] ?? row.category ?? "—";
    case "price": return priceCell(row);
    case "workflowDate": return sheetDateLabel(row);
    case "productId": return row.externalId ?? "—";
    default: return "—";
  }
}

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

/** The unit the PRICE is in -- not the one somebody asked for, which may not be reachable.
 *
 * `targetUnit` is what the backend says the returned number is actually in. Falling back to
 * the chosen unit would be the one lie this column can tell: showing «متر» beside a price
 * that is still per branch. So when nothing converted, what the source said is shown. */
export function unitCell(row) {
  const shown = row.targetUnit ?? row.sourceUnitCode ?? row.sourceUnit;
  if (!shown) return "واحد اعلام نشده";
  if (!row.conversionFactor) return formatUnitLabel(shown);
  const how = row.factorOrigin === "dimension" ? "تبدیل‌شده" : "تبدیل با ضریب کالا";
  return `${formatUnitLabel(shown)} (${how})`;
}

/** The Finance/MSP unit and whether the price can be expressed in it. */
export function alignmentCell(row) {
  const verdict = ALIGNMENT_LABELS[row.unitAlignment] ?? row.unitAlignment;
  if (!row.financeResourceUnit) return verdict;
  return `${formatUnitLabel(row.financeResourceUnit)} — ${verdict}`;
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

function renderRow(row, columns, categoryLabels) {
  const tr = element("tr", "material-price__row");
  columns.forEach((column) => {
    const cell = element("td", column.numeric ? "numeric" : "", cellValue(column, row, categoryLabels));
    if (column.key === "product") {
      cell.className = "material-price__name";
      /* Status and unit are NOT columns of this table -- the worksheet has no such
         columns and adding them would be the generic shape returning by another door.
         They travel as a small badge under the name, where a reader who wants to judge
         the price can see them without the header row claiming the sheet states them. */
      const text = statusText(row);
      if (text) {
        cell.append(element("span",
          `material-price__badge ${RESOLUTION_CLASS[row.resolutionStatus] ?? ""}`, text));
      }
      /* The unit note, only when there IS a unit to state. Six of the seven worksheets
         declare none, so «واحد اعلام نشده» would repeat under every one of hundreds of
         rows and say nothing the status badge has not already said. */
      if (row.targetUnit || row.sourceUnitCode || row.sourceUnit) {
        cell.append(element("span", "material-price__unit-note", unitCell(row)));
      }
    }
    tr.append(cell);
  });

  /* Everything a reader might need to check this number, on the row itself: what was
     converted and how, what the supplier actually called the thing, and how it lines up
     with the Finance item. A converted price nobody can check is a number nobody should
     trust -- and none of these is a worksheet column, so none of them is one here. */
  const notes = [];
  if (row.conversionNote) notes.push(row.conversionNote);
  if ((row.labelDisplayName || row.label) && row.name) notes.push(`نام در برگه: ${row.name}`);
  if (row.labelSourceBasis) notes.push(`مبنای قیمت: ${row.labelSourceBasis}`);
  if (row.financeResourceUnit || row.unitAlignment) notes.push(`قلم هزینه: ${alignmentCell(row)}`);
  if (notes.length) tr.title = notes.join(" · ");
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
      /* The Persian name the Backend publishes, not the raw importer key. These tabs read
         «angle (12)» and «pipe_fitting (0)» to a Finance user who has no reason to know
         what the importer calls its worksheets. The code stays on the element, where a
         test and anyone inspecting the page can still find it. */
      const chip = element("button", "app-chip" + (active ? " app-chip--active" : ""),
        `${category.label ?? category.category} (${category.activeCount})`);
      chip.type = "button";
      chip.dataset.category = category.category;
      chip.setAttribute("aria-pressed", String(active));
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

  /* Built for the chosen category, from the schema the Backend published for it. Switching
     the category tab rebuilds this section, so the header row is rebuilt with it -- there
     is no path that keeps one category's headers over another's rows. */
  const columns = columnsFor(selectedCategory, categories);
  const categoryLabels = Object.fromEntries(
    (categories ?? []).map((c) => [c.category, c.label ?? c.category]));
  const chosen = (categories ?? []).find((c) => c.category === selectedCategory);

  const wrapper = element("div", "app-table-scroll");
  const table = element("table", "app-table material-prices__table");
  const caption = element("caption", "sr-only",
    chosen ? `قیمت روز بازار — ${chosen.label ?? chosen.category}` : "قیمت روز بازار به تفکیک محصول");
  const thead = element("thead", "");
  const headRow = element("tr", "");
  columns.forEach((column) => {
    const th = element("th", "", column.label);
    th.scope = "col";
    /* So a test -- and anyone inspecting the page -- can see which worksheet key a column
       came from, and that a spec column is the sheet's own rather than this page's. */
    th.dataset.columnKey = column.key;
    th.dataset.columnKind = column.kind ?? "base";
    headRow.append(th);
  });
  thead.append(headRow);
  const tbody = element("tbody", "");
  rows.forEach((row) => tbody.append(renderRow(row, columns, categoryLabels)));
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
