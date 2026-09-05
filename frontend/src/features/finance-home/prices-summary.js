import { element } from "../../shared/dom/elements.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { createPriceTrend } from "../../shared/components/price-trend.js";

/**
 * قیمت‌های روز — three rows of the price table, on the overview.
 *
 * It reads the same workspace `#/report-prices` reads, through the same adapter,
 * and shows the first three items that actually carry a day price. Nothing here
 * computes: the amount is the one the service already answered with, and the
 * trend direction is the one it already decided.
 *
 * Three rows is the whole point — the summary exists to say what the table is
 * about and hand the reader to it, not to be a smaller copy of it.
 */

const ROW_COUNT = 3;

export function createPricesSummary({ workspace = null, error = null } = {}) {
  const section = element("section", "overview-card prices-summary");
  section.setAttribute("aria-label", "قیمت‌های روز");

  const head = element("header", "overview-card__head");
  head.append(element("h2", "overview-card__title", "قیمت‌های روز"));
  const all = element("a", "overview-card__link", "مشاهده همه");
  all.href = "#/report-prices";
  head.append(all);
  section.append(head);

  if (error) {
    section.append(element("p", "inline-notice", formatApiErrorMessage(error, "دریافت قیمت‌های روز انجام نشد.")));
    return section;
  }

  // `currentPrices` is what the workspace calls its rows — the same array the
  // full table on #/report-prices renders.
  const rows = (workspace?.currentPrices ?? [])
    .filter((item) => item?.currentPrice?.unitPriceIRR)
    .slice(0, ROW_COUNT);

  if (!rows.length) {
    section.append(element("p", "inline-notice", "هنوز قیمت روزی برای اقلام این پروژه ثبت نشده است."));
    return section;
  }

  const table = element("table", "prices-summary__table");
  const caption = element("caption", "sr-only", "سه قلم از فهرست قیمت روز پروژه");
  const head_ = document.createElement("thead");
  const header = document.createElement("tr");
  ["نام قلم", "قیمت روز", "روند"].forEach((label) => header.append(element("th", "", label)));
  head_.append(header);
  const body = document.createElement("tbody");

  rows.forEach((item) => {
    const record = document.createElement("tr");
    const name = element("td", "prices-summary__name");
    // The column is a fixed share of the card and the cell clips rather than
    // wrapping, so a name longer than its column is cut on screen. The title is
    // where the whole of it stays.
    const nameText = item.resource?.title ?? "قلم بدون عنوان";
    name.title = nameText;
    name.append(element("span", "", nameText));
    const price = element("td", "numeric prices-summary__price",
      formatTomanFromIrr(item.currentPrice.unitPriceIRR, { withCurrency: false }));
    // The table's own trend, not a second reading of it: same function, same
    // item, same history — so the line here is the line there.
    const trend = element("td", "prices-summary__trend");
    trend.append(createPriceTrend(item, workspace?.history ?? []));
    record.append(name, price, trend);
    body.append(record);
  });

  table.append(caption, head_, body);
  section.append(table);
  return section;
}
