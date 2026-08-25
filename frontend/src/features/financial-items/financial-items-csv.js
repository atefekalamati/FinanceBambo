import { csvDocument, csvFileNamePart, csvRow } from "../../shared/exports/csv.js";

/**
 * The estimate as a spreadsheet.
 *
 * A general-cost line carries an amount and every other line carries a quantity,
 * and the two must never land in one column: summing a column of mixed rials and
 * square metres produces a number that means nothing. They get a column each,
 * and a «جنس قلم» column says which one a row filled in.
 *
 * Both the original and the latest revised value are written, because the
 * difference between them is the whole point of keeping revisions.
 */
const HEADER = Object.freeze([
  "کد فعالیت",
  "ساختار شکست کار",
  "عنوان فعالیت",
  "کد قلم",
  "عنوان قلم",
  "جنس قلم",
  "واحد",
  "مقدار برآورد اولیه",
  "آخرین مقدار برآورد",
  "مبلغ برآورد اولیه (ریال)",
  "آخرین مبلغ برآورد (ریال)",
  "اصلاح‌شده",
  "منبع",
]);

const SOURCE = Object.freeze({
  imported: "ورود از فایل",
  manual: "ثبت دستی",
  revised: "اصلاح‌شده",
});

export function buildEstimateLinesCsv({ lines = [], resources = [] } = {}) {
  const resourceMap = new Map(resources.map((resource) => [resource.resourceId, resource]));
  const rows = [csvRow(HEADER)];
  lines.forEach((line) => {
    const resource = resourceMap.get(line.resourceId) ?? null;
    const isGeneralCost = resource?.type === "general_cost";
    const original = isGeneralCost ? line.originalAmount : line.originalQuantity;
    const revised = isGeneralCost ? line.revisedAmount : line.revisedQuantity;
    rows.push(csvRow([
      line.activityExternalId,
      line.wbsCode,
      line.activityTitle,
      resource?.code,
      resource?.title,
      isGeneralCost ? "هزینه عمومی" : "قلم مقداری",
      isGeneralCost ? "ریال" : resource?.baseUnit,
      isGeneralCost ? "" : original,
      isGeneralCost ? "" : revised,
      isGeneralCost ? original : "",
      isGeneralCost ? revised : "",
      String(original) === String(revised) ? "خیر" : "بله",
      SOURCE[line.source] ?? line.source ?? "",
    ]));
  });
  return csvDocument(rows);
}

export function estimateLinesFileName({ projectCode } = {}) {
  return `finance-estimate-${csvFileNamePart(projectCode)}.csv`;
}
