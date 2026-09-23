import { element } from "../../shared/dom/elements.js";
import { createDataTable, createTablePagination } from "../../shared/components/data-table.js";
import { formatBusinessDate, formatDisplayNumber, formatJalaliBusinessDate, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { createPriceTrend } from "../../shared/components/price-trend.js";
import { createPriceTrendDetailDialog } from "../../shared/components/price-trend-detail.js";

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
  { key: "origin", label: "منشأ", kind: "base" },
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

/* The supplier, the worksheet's own product id, and whether a person typed this price.
   All three are how somebody MAINTAINING the sheet finds and judges a row, and all three
   are noise to somebody reading the financial report, who is asking what things cost
   rather than where the quote came from. «منشأ» belongs with them for a sharper reason
   than the other two: a reader who can see that half the prices were typed by hand is
   being invited to weigh the report's numbers against each other, which is not the
   question a cost report answers. Dropped on the report surface only; امور مالی keeps
   all three. */
const MAINTENANCE_ONLY_COLUMNS = Object.freeze(new Set(["source", "productId", "origin"]));

/* «تاریخ آپدیت ورک فلو» is the sheet's own phrase for it and it reads as jargon in a
   table of prices. The key is what everything else matches on, so only the label moves. */
const COLUMN_LABEL_OVERRIDES = Object.freeze({ workflowDate: "آخرین آپدیت" });

/* Trend is a property of every listing, not a worksheet column. It is added at the
   presentation boundary so a database capability never masquerades as source-sheet data. */
function withTrend(columns) {
  if (columns.some((column) => column.key === "trend")) return columns;
  const trend = { key: "trend", label: "روند", kind: "computed" };
  const priceIndex = columns.findIndex((column) => column.key === "price");
  if (priceIndex < 0) return [...columns, trend];
  const at = priceIndex + 1;
  return [...columns.slice(0, at), trend, ...columns.slice(at)];
}

/**
 * The columns as this surface presents them.
 *
 * Applied AFTER `columnsFor`, and that is deliberate: the per-category schema comes from
 * the Backend and carries these same columns, so filtering only the shared list would drop
 * them from the all-categories view and leave them in every category's own.
 */
export function presentedColumns(columns, { readOnly = false } = {}) {
  const shown = withTrend(withOrigin(columns, { readOnly }))
    .filter((column) => !(readOnly && MAINTENANCE_ONLY_COLUMNS.has(column.key)))
    .map((column) => (COLUMN_LABEL_OVERRIDES[column.key]
      ? { ...column, label: COLUMN_LABEL_OVERRIDES[column.key] }
      : column));
  return shown;
}

/** Adapt newest-first observations to the shared sparkline's oldest-first contract. */
export function materialPriceTrend(row, history = []) {
  const points = (history ?? [])
    .filter((observation) => (!observation?.validationStatus
      || observation.validationStatus === "valid")
      && /^\d+$/.test(String(observation?.priceIRR ?? "")))
    .slice(0, 5)
    .reverse()
    .map((observation) => ({
      effectiveFrom: observation.workflowDate ?? observation.observedAt ?? observation.fetchedAt,
      unitPriceIrr: String(observation.priceIRR),
    }));
  const previous = points.at(-2)?.unitPriceIrr;
  const current = points.at(-1)?.unitPriceIrr;
  const direction = previous === undefined || current === undefined
    ? "none"
    : BigInt(current) > BigInt(previous) ? "up"
      : BigInt(current) < BigInt(previous) ? "down" : "flat";
  return {
    resource: { resourceId: row.providerItemId },
    trend: { trendDirection: direction, trendPoints: points },
  };
}

/* «منشأ» is not a worksheet column, so no category declares it.
 *
 * Every other column here comes from the Backend's per-category schema, derived from the
 * keys that worksheet actually has — and that is the rule this page keeps, because a
 * hardcoded list is how one sheet's column ends up over another sheet's rows. But whether
 * a person TYPED this price is true of every row in every category and is stated by no
 * worksheet at all, so it would appear in the all-categories view and then vanish the
 * moment somebody picked a chip — exactly where it matters most, since a chip is how you
 * look at one kind of thing and compare its prices.
 *
 * Added once, here, where the surface's own presentation decisions already live. Never on
 * the report surface, and never twice if the schema ever does declare it.
 */
function withOrigin(columns, { readOnly }) {
  if (readOnly || columns.some((column) => column.key === "origin")) return columns;
  const origin = { key: "origin", label: "منشأ", kind: "base" };
  /* Before `productId`, which is the sheet's own key and reads as the end of the row. */
  const at = columns.findIndex((column) => column.key === "productId");
  if (at < 0) return [...columns, origin];
  return [...columns.slice(0, at), origin, ...columns.slice(at)];
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
    case "origin": return originLabel(row);
    case "productId": return row.externalId ?? "—";
    default: return "—";
  }
}

/** Whether an import read this price off a worksheet, or a person typed it. */
export function originLabel(row) {
  /* `sheet` is the default in the adapter, so a service that sends nothing reads as the
     sheet -- which is what every row was before anybody could type one. A value this page
     has no word for is printed rather than swallowed: a blank would read as "from the
     sheet", which is the one thing it is not known to be. */
  if (row?.origin === "manual") return "ثبت دستی";
  if (!row?.origin || row.origin === "sheet") return "برگهٔ مصالح";
  return row.origin;
}

/** The date a reader recognises: the sheet's own Jalali text when it stated one. */
export function sheetDateLabel(row) {
  if (row.workflowDateJalali) {
    const formatted = formatJalaliBusinessDate(row.workflowDateJalali);
    return formatted === "—" ? row.workflowDateJalali : formatted;
  }
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

/* One cell per column, keyed the way the shared table wants them. The product cell is a
   fragment rather than a string: the status badge and the unit note hang under the name,
   which is where a reader judging a price looks, and neither is a column of the sheet. */
function cellsFor(row, columns, categoryLabels, priceHistories) {
  const built = {};
  columns.forEach((column) => {
    if (column.key === "trend") {
      /* The sparkline says «up» and nothing else. These are the only figures behind it,
         so pressing it opens the points it was drawn from -- the same array, in the same
         order, with no request of its own. Keyed on this row's own listing, so a modal
         can only ever show the product whose line was pressed. */
      built[column.key] = createPriceTrend(
        materialPriceTrend(row, priceHistories.get(row.providerItemId) ?? []), [],
        { onOpen: (points) => createPriceTrendDetailDialog({
            title: cellValue({ key: "product", kind: "base" }, row, categoryLabels),
            points,
          }).open() });
      return;
    }
    const value = cellValue(column, row, categoryLabels);
    if (column.key !== "product") { built[column.key] = value; return; }
    const cell = document.createDocumentFragment();
    cell.append(element("span", "material-price__name", value));
    /* Status and unit are NOT columns of this table -- the worksheet has no such columns
       and adding them would be the generic shape returning by another door. */
    const text = statusText(row);
    if (text) {
      cell.append(element("span",
        `material-price__badge ${RESOLUTION_CLASS[row.resolutionStatus] ?? ""}`, text));
    }
    /* The unit note, only when there IS a unit to state. Six of the seven worksheets
       declare none, so «واحد اعلام نشده» would repeat under every one of hundreds of rows
       and say nothing the status badge has not already said. */
    if (row.targetUnit || row.sourceUnitCode || row.sourceUnit) {
      cell.append(element("span", "material-price__unit-note", unitCell(row)));
    }
    built[column.key] = cell;
  });

  return built;
}

/* Everything a reader might need to check this number, on the row itself: what was
   converted and how, what the supplier actually called the thing, and how it lines up with
   the Finance item. A converted price nobody can check is a number nobody should trust --
   and none of these is a worksheet column, so none of them is one here. */
function rowNotes(row) {
  const notes = [];
  if (row.conversionNote) notes.push(row.conversionNote);
  if ((row.labelDisplayName || row.label) && row.name) notes.push(`نام در برگه: ${row.name}`);
  if (row.labelSourceBasis) notes.push(`مبنای قیمت: ${row.labelSourceBasis}`);
  if (row.financeResourceUnit || row.unitAlignment) notes.push(`قلم هزینه: ${alignmentCell(row)}`);
  return notes.length ? notes.join(" · ") : null;
}

/**
 * The section, given rows the adapter already fetched.
 *
 * `rows` is whatever the database returned — possibly empty, possibly all unresolved.
 * There is no branch here that invents one.
 */
/**
 * @param paging  `{ page, pageSize, totalItems, onChange }` — SERVER paging. The rows given
 *   are the page the server already sliced, so nothing here slices again: the sheet holds
 *   992 pipes and asking for all of them to show fifty is the request this avoids. Absent,
 *   the section renders the rows it was handed with no footer, as it always did.
 */
export function renderMaterialPrices(rows, { categories = [], selectedCategory = null,
                                             onSelectCategory = null, paging = null,
                                             readOnly = false,
                                             priceHistories = new Map() } = {}) {
  const section = element("section", "prices-section material-prices");
  const heading = element("header", "prices-section__header");
  heading.append(element("h2", "", "قیمت روز بازار (برگه مصالح)"));
  heading.append(element("p", "prices-section__hint",
    "این قیمت‌ها مشاهده‌های وارد‌شده از برگه مصالح‌اند، نه قیمت رسمی مالی پروژه. "
    + "قیمت رسمی را یک نفر ثبت می‌کند و فاکتورها و گزارش‌ها با آن سنجیده می‌شوند."));
  section.append(heading);

  if (categories.length && onSelectCategory) {
    const filter = element("div", "material-prices__filters");
    const byCode = new Map(categories.map((category) => [category.category, category]));
    /* The five that are always on screen whatever this project's sheet happens to carry:
       they are the trades every project has, and a chip that came and went with a missing
       worksheet would make the filter bar a different shape on every project.

       `تجهیزات` joins them ONLY once the service publishes the category. Machines are a
       kind of priced thing a reader looks for by name rather than hunting for in the
       overflow menu — but until the service answers `equipment`, an unconditional chip
       would render with no count and filter to an empty table. It appears the day the
       rows do, and nothing here needs changing then. */
    const fixedCategories = [
      { category: "brick", label: "آجر" },
      { category: "rebar", label: "میلگرد" },
      { category: "ibeam", label: "تیرآهن" },
      { category: "channel", label: "ناودانی" },
      { category: "pipe", label: "لوله" },
      ...(byCode.has("equipment") ? [{ category: "equipment", label: "تجهیزات" }] : []),
    ];
    const makeChip = (category, container = filter, dropdown = null) => {
      const active = category.category === selectedCategory;
      const count = category.activeCount == null ? "" : ` (${category.activeCount})`;
      const chip = element("button", "app-chip" + (active ? " app-chip--active" : ""),
        `${category.label ?? category.category}${count}`);
      chip.type = "button";
      chip.dataset.category = category.category;
      chip.setAttribute("aria-pressed", String(active));
      chip.addEventListener("click", () => {
        if (dropdown) dropdown.open = false;
        onSelectCategory(category.category);
      });
      container.append(chip);
    };

    const all = element("button", "app-chip" + (selectedCategory ? "" : " app-chip--active"), "همه");
    all.type = "button";
    all.setAttribute("aria-pressed", String(!selectedCategory));
    all.addEventListener("click", () => onSelectCategory(null));
    filter.append(all);
    fixedCategories.forEach((fixed) => makeChip({ ...byCode.get(fixed.category), ...fixed }));

    const fixedCodes = new Set(fixedCategories.map(({ category }) => category));
    const overflowCategories = categories.filter(({ category }) => !fixedCodes.has(category));
    if (overflowCategories.length) {
      const dropdown = element("details", "material-prices__more");
      const overflowActive = overflowCategories.some(({ category }) => category === selectedCategory);
      const summary = element("summary", "app-chip material-prices__more-trigger"
        + (overflowActive ? " app-chip--active" : ""), "…");
      summary.setAttribute("aria-label", "سایر دسته‌بندی‌ها");
      const menu = element("div", "material-prices__more-menu");
      overflowCategories.forEach((category) => makeChip(category, menu, dropdown));
      dropdown.append(summary, menu);
      filter.append(dropdown);
    }
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
  const columns = presentedColumns(columnsFor(selectedCategory, categories), { readOnly });
  const categoryLabels = Object.fromEntries(
    (categories ?? []).map((c) => [c.category, c.label ?? c.category]));
  const chosen = (categories ?? []).find((c) => c.category === selectedCategory);

  const caption = chosen
    ? `قیمت روز بازار — ${chosen.label ?? chosen.category}`
    : "قیمت روز بازار به تفکیک محصول";

  const table = createDataTable({
    caption,
    className: "material-prices__table",
    columns,
    rows,
    cells: (row) => cellsFor(row, columns, categoryLabels, priceHistories),
    rowAttributes: () => ({ className: "material-price__row" }),
    emptyMessage: "هیچ محصولی در این دسته نیست.",
  });
  /* Which worksheet key each column came from, and whether it is one of the sheet's own
     spec columns or part of the shared set. Stamped here rather than asked of the shared
     component: it is this table's fact -- no other table has a per-category schema -- and
     a parameter for it would put a worksheet concept into every table in the module. */
  [...table.querySelectorAll("th")].forEach((th, index) => {
    if (!columns[index]) return;
    th.dataset.columnKey = columns[index].key;
    th.dataset.columnKind = columns[index].kind ?? "base";
  });
  /* The row's own explanation, in its title. Stamped after the fact for the same reason
     as the header keys: the shared table carries `className` and `tabIndex` and nothing
     else, and widening that contract for one table would put a tooltip in every one. Rows
     are in the order they were given, which is the order this walks. */
  [...table.querySelectorAll("tbody tr")].forEach((tr, index) => {
    const title = rows[index] ? rowNotes(rows[index]) : null;
    if (title) tr.title = title;
  });
  section.append(table);

  if (paging) {
    section.append(createTablePagination({
      name: `material-prices-${selectedCategory ?? "all"}`,
      page: paging.page,
      total: paging.totalItems,
      pageSize: paging.pageSize,
      label: "صفحه‌بندی قیمت روز بازار",
      onPageChange: (next) => paging.onChange?.({ page: next, pageSize: paging.pageSize }),
      onPageSizeChange: (next) => paging.onChange?.({ page: 1, pageSize: next }),
    }));
  }

  /* Counted over THIS PAGE, and it says so. With the server slicing, «۱۲ قلم از ۵۰» is
     about the fifty on screen; claiming it was about the whole category would be a figure
     nobody could check against anything visible. */
  const unresolved = rows.filter((row) => row.resolutionStatus !== "resolved").length;
  if (unresolved) {
    section.append(element("p", "prices-section__hint",
      `${unresolved} قلم از ${rows.length} قلم این صفحه قیمت قابل استفاده ندارد. دلیل هر کدام زیر نام محصول آمده است.`));
  }
  return section;
}
