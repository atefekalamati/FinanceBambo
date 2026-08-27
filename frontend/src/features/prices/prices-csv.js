import { csvDocument, csvFileNamePart, csvRow } from "../../shared/exports/csv.js";

/**
 * The price list as a spreadsheet.
 *
 * It is the same table that is on the screen, in the same order, with the same
 * filters already applied — a reader exports what they are looking at, not a
 * different set of rows that happens to be easier to build.
 *
 * Amounts are the exact integer rial the API returned. The screen shows toman
 * because that is what people read; a spreadsheet gets the stored unit, and the
 * header says which it is, so nobody has to guess whether a column was already
 * divided by ten.
 */
const HEADER = Object.freeze([
  "کد قلم",
  "عنوان قلم",
  "واحد پایه",
  "قیمت پایه سازمان (ریال)",
  "تاریخ اعتبار قیمت سازمان",
  "قیمت اختصاصی پروژه (ریال)",
  "تاریخ اعتبار قیمت پروژه",
  "قیمت روز (ریال)",
  "منبع قیمت روز",
  "تاریخ اعتبار قیمت روز",
]);

const SCOPE = Object.freeze({ organization: "پایه سازمان", project: "اختصاصی پروژه" });

export function buildPricesCsv(items = []) {
  const lines = [csvRow(HEADER)];
  items.forEach((item) => {
    lines.push(csvRow([
      item.resource?.code,
      item.resource?.title,
      item.resource?.baseUnit,
      item.organizationPrice?.unitPriceIRR,
      item.organizationPrice?.effectiveFrom,
      item.projectPrice?.unitPriceIRR,
      item.projectPrice?.effectiveFrom,
      item.currentPrice?.unitPriceIRR,
      item.currentPrice ? SCOPE[item.currentPrice.scope] ?? item.currentPrice.scope : "بدون قیمت",
      item.currentPrice?.effectiveFrom,
    ]));
  });
  return csvDocument(lines);
}

export function pricesFileName({ projectCode, asOfDate } = {}) {
  return `finance-prices-${csvFileNamePart(projectCode)}-${asOfDate ?? ""}.csv`;
}
