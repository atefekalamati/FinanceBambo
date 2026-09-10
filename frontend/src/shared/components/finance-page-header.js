import { element } from "../dom/elements.js";
import { SURFACES, homeRouteFor } from "../../core/config/routes.js";

/** A consistent two-child header for internal finance pages. */
export function createFinancePageHeader(title, className = "feature-header", surface = SURFACES.REPORT) {
  const header = element("header", `${className} finance-internal-header`);
  const heading = element("h1", "", title);
  const home = homeRouteFor(surface) ?? homeRouteFor(SURFACES.REPORT);
  const back = element("a", "button button--ghost finance-back-link", `بازگشت به ${home.label}`);
  back.href = `#${home.path}`;
  header.append(heading, back);
  return header;
}
