import { element } from "../../shared/dom/elements.js";
import {
  formatDisplayNumber,
  formatUnitLabel,
} from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";

/**
 * A compact, read-only window into the same estimate-line workspace used by
 * #finance/report-items. Like the day-price summary beside it, this component selects
 * three service rows and performs no financial roll-up of its own.
 *
 * WHICH THREE, AND WHAT THEY SHOW -- revised 2026-09-27.
 *
 * The card used to take the three OLDEST lines and print each one's quantity beside its
 * unit. Measured on this project that was three seed rows worth 100,000 toman apiece,
 * and on a real project it would have been three of 426 equipment lines that state no
 * quantity at all -- a unit printed beside a dash. Neither told a reader anything.
 *
 * Now: the three lines with the LARGEST estimate, each with its stage code, its
 * quantity in its own unit, and what it was estimated at. The estimate is the line's own
 * two factors multiplied exactly -- quantity × the unit rate the estimate was fixed at,
 * or the stated amount for a general cost -- which is the same product «ریز برآورد»
 * shows per line, not a new rule. A line missing either factor has no estimate and
 * ranks last, shown as a dash rather than as zero.
 */
const ROW_COUNT = 3;

/** How many WBS segments a row shows: «1.4.1», the stage, not the leaf activity. */
const WBS_SEGMENTS = 3;

/** Scale at which quantities are stored: four decimals, so × 10⁴ is an integer. */
const QUANTITY_SCALE = 10_000n;

/** A decimal string (up to four decimals) as an integer scaled by QUANTITY_SCALE. */
function scaledQuantity(value) {
  const matched = /^(-?)(\d+)(?:\.(\d{1,4}))?$/.exec(String(value ?? "").trim());
  if (!matched) return null;
  const [, sign, whole, fraction = ""] = matched;
  const magnitude = BigInt(whole) * QUANTITY_SCALE + BigInt(fraction.padEnd(4, "0"));
  return sign ? -magnitude : magnitude;
}

/**
 * The line's estimate in rials, as an exact integer string, or null when the line does
 * not state both factors. Rounded half away from zero at the last step, once, exactly
 * as the service rounds a line: no float touches money.
 */
export function estimateAmountIrr(line, resource) {
  if (resource?.type === "general_cost") {
    const amount = line?.revisedAmount ?? line?.originalAmount;
    return /^-?\d+$/.test(String(amount ?? "")) ? String(BigInt(amount)) : null;
  }
  const quantity = scaledQuantity(line?.revisedQuantity ?? line?.originalQuantity);
  const rate = line?.originalUnitPriceIRR;
  if (quantity === null || !/^-?\d+$/.test(String(rate ?? ""))) return null;
  const product = quantity * BigInt(rate);
  const negative = product < 0n;
  const magnitude = negative ? -product : product;
  const rounded = (magnitude + QUANTITY_SCALE / 2n) / QUANTITY_SCALE;
  return String(negative ? -rounded : rounded);
}

/** «1.9.4.2» → «1.9.4»; a shorter code is returned as it is; nothing → null. */
export function stageCode(line) {
  const code = line?.wbsCode || line?.activityExternalId || "";
  const segments = String(code).split(".").map((part) => part.trim()).filter(Boolean);
  return segments.length ? segments.slice(0, WBS_SEGMENTS).join(".") : null;
}

/**
 * The rows the card shows: every line with its catalogue item, ranked by estimate, the
 * lines without one last, cut to ROW_COUNT. Exported so the ranking can be tested
 * without a DOM.
 */
export function selectSummaryRows(workspace, count = ROW_COUNT) {
  const resources = new Map(
    (workspace?.resources ?? []).map((resource) => [resource.resourceId, resource]),
  );
  return (workspace?.estimateLines ?? [])
    .map((line) => ({ line, resource: resources.get(line.resourceId) }))
    // An estimate line without its catalogue item cannot be named faithfully.
    .filter(({ resource }) => Boolean(resource))
    .map((row) => ({ ...row, amountIrr: estimateAmountIrr(row.line, row.resource) }))
    .sort((a, b) => {
      if (a.amountIrr === null || b.amountIrr === null) {
        return (a.amountIrr === null) - (b.amountIrr === null);
      }
      const difference = BigInt(b.amountIrr) - BigInt(a.amountIrr);
      return difference > 0n ? 1 : difference < 0n ? -1 : 0;
    })
    .slice(0, count);
}

function quantityText(line, resource) {
  if (resource.type === "general_cost") return "—";
  const quantity = line.revisedQuantity ?? line.originalQuantity;
  // No quantity means no unit either: a unit beside a dash is a claim about nothing.
  if (quantity === null || quantity === undefined || quantity === "") return "—";
  return `${formatDisplayNumber(quantity)} ${formatUnitLabel(resource.baseUnit)}`;
}

export function createItemsSummary({ workspace = null, error = null } = {}) {
  // `prices-summary` is also the compact overview-table pattern. Keeping that
  // class here makes both cards obey one set of dimensions and breakpoints.
  const section = element("section", "overview-card prices-summary items-summary");
  section.setAttribute("aria-label", "اقلام و برآورد پروژه");

  const head = element("header", "overview-card__head");
  head.append(element("h2", "overview-card__title", "اقلام و برآورد"));
  const all = element("a", "overview-card__link", "مشاهده همه");
  all.href = "#finance/report-items";
  head.append(all);
  section.append(head);

  if (error) {
    section.append(
      element(
        "p",
        "inline-notice",
        formatApiErrorMessage(error, "دریافت اقلام و برآورد انجام نشد."),
      ),
    );
    return section;
  }

  const rows = selectSummaryRows(workspace);

  if (!rows.length) {
    section.append(
      element("p", "inline-notice", "هنوز قلم برآوردی برای این پروژه ثبت نشده است."),
    );
    return section;
  }

  const table = element("table", "prices-summary__table items-summary__table");
  const caption = element("caption", "sr-only", "سه قلم با بزرگ‌ترین مبلغ برآورد");
  const tableHead = document.createElement("thead");
  const header = document.createElement("tr");
  ["قلم هزینه", "مقدار", `مبلغ برآورد (${getDisplayCurrencyLabel()})`].forEach((label) =>
    header.append(element("th", "", label)),
  );
  tableHead.append(header);
  const body = document.createElement("tbody");

  rows.forEach(({ line, resource, amountIrr }) => {
    const record = document.createElement("tr");
    const name = element("td", "prices-summary__name items-summary__name");
    const title = resource.title || "قلم بدون عنوان";
    const stage = stageCode(line);
    // The column clips rather than wraps, so the whole of it stays in the title.
    name.title = stage ? `${stage} · ${title}` : title;
    if (stage) name.append(element("span", "items-summary__stage", stage));
    name.append(element("span", "", title));
    const quantity = element(
      "td",
      "numeric prices-summary__price items-summary__quantity",
      quantityText(line, resource),
    );
    const estimate = element(
      "td",
      "numeric prices-summary__trend items-summary__estimate",
      formatTomanFromIrr(amountIrr, { withCurrency: false }),
    );
    record.append(name, quantity, estimate);
    body.append(record);
  });

  table.append(caption, tableHead, body);
  section.append(table);
  return section;
}
