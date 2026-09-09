import { element } from "../dom/elements.js";

/** A consistent two-child header for internal finance pages. */
export function createFinancePageHeader(title, className = "feature-header") {
  const header = element("header", `${className} finance-internal-header`);
  const heading = element("h1", "", title);
  const back = element("a", "button button--ghost finance-back-link", "بازگشت به گزارش مالی");
  back.href = "#/finance-report";
  header.append(heading, back);
  return header;
}
