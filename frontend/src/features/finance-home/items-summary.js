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
 * #/report-items. Like the day-price summary beside it, this component selects
 * three service rows and performs no financial roll-up of its own.
 */
const ROW_COUNT = 3;

function displayRow(line, resource) {
  const isGeneralCost = resource.type === "general_cost";
  const estimate = isGeneralCost
    ? line.revisedAmount ?? line.originalAmount
    : line.revisedQuantity ?? line.originalQuantity;

  return {
    name: resource.title || "قلم بدون عنوان",
    estimate: isGeneralCost
      ? formatTomanFromIrr(estimate, { withCurrency: false })
      : formatDisplayNumber(estimate),
    unit: isGeneralCost
      ? getDisplayCurrencyLabel()
      : formatUnitLabel(resource.baseUnit),
  };
}

export function createItemsSummary({ workspace = null, error = null } = {}) {
  // `prices-summary` is also the compact overview-table pattern. Keeping that
  // class here makes both cards obey one set of dimensions and breakpoints.
  const section = element("section", "overview-card prices-summary items-summary");
  section.setAttribute("aria-label", "اقلام و برآورد پروژه");

  const head = element("header", "overview-card__head");
  head.append(element("h2", "overview-card__title", "اقلام و برآورد"));
  const all = element("a", "overview-card__link", "مشاهده همه");
  all.href = "#/report-items";
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

  const resources = new Map(
    (workspace?.resources ?? []).map((resource) => [resource.resourceId, resource]),
  );
  const rows = (workspace?.estimateLines ?? [])
    .map((line) => ({ line, resource: resources.get(line.resourceId) }))
    // An estimate line without its catalogue item cannot be named faithfully.
    .filter(({ resource }) => Boolean(resource))
    .slice(0, ROW_COUNT);

  if (!rows.length) {
    section.append(
      element("p", "inline-notice", "هنوز قلم برآوردی برای این پروژه ثبت نشده است."),
    );
    return section;
  }

  const table = element("table", "prices-summary__table items-summary__table");
  const caption = element("caption", "sr-only", "سه ردیف نخست از اقلام و برآورد پروژه");
  const tableHead = document.createElement("thead");
  const header = document.createElement("tr");
  ["قلم هزینه", "مقدار برآورد", "واحد"].forEach((label) =>
    header.append(element("th", "", label)),
  );
  tableHead.append(header);
  const body = document.createElement("tbody");

  rows.forEach(({ line, resource }) => {
    const row = displayRow(line, resource);
    const record = document.createElement("tr");
    const name = element("td", "prices-summary__name items-summary__name");
    name.title = row.name;
    name.append(element("span", "", row.name));
    const estimate = element(
      "td",
      "numeric prices-summary__price items-summary__estimate",
      row.estimate,
    );
    const unit = element(
      "td",
      "numeric prices-summary__trend items-summary__unit",
      row.unit,
    );
    record.append(name, estimate, unit);
    body.append(record);
  });

  table.append(caption, tableHead, body);
  section.append(table);
  return section;
}
