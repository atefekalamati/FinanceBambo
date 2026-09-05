import { element } from "../../shared/dom/elements.js";
import { chevronIcon, reportIcon } from "../report-builder/report-icons.js";

/**
 * The way into فاکتورها, on the board.
 *
 * It is an entry point, not a summary: the invoice list, the form and everything
 * that happens to a document live on their own page, and nothing about them is
 * rebuilt here. What this card owes the reader is a clear statement of what is
 * behind it and a target big enough to hit.
 *
 * The whole card is one anchor — the same shape the cost-mix card on this board
 * already uses — so the heading, the line under it and the footer are all part
 * of the link rather than decoration around a smaller one, and a keyboard
 * reaches it in a single stop.
 */
export function createInvoicesEntry({ href = "#/invoices" } = {}) {
  const card = element("a", "overview-card invoices-entry");
  card.href = href;
  card.setAttribute("aria-label", "ورود به بخش فاکتورها — ثبت و مشاهده فاکتورهای پروژه");

  const head = element("header", "overview-card__head invoices-entry__head");
  const mark = element("span", "invoices-entry__mark");
  const icon = reportIcon("invoices");
  icon.setAttribute("class", "invoices-entry__icon");
  mark.append(icon);
  head.append(mark, element("h2", "overview-card__title", "فاکتورها"));
  card.append(head);

  card.append(element("p", "invoices-entry__lead",
    "ثبت فاکتور جدید و مشاهده فهرست فاکتورها با وضعیت، فروشنده، مبلغ و جزئیات هر خط."));

  const tags = element("ul", "invoices-entry__tags");
  ["ثبت فاکتور", "فهرست و وضعیت", "تأیید و ابطال"].forEach((label) => {
    tags.append(element("li", "", label));
  });
  card.append(tags);

  const action = element("span", "invoices-entry__action");
  const actionChevron = chevronIcon("forward");
  actionChevron.setAttribute("class", "invoices-entry__chevron");
  action.append(document.createTextNode("ورود به بخش فاکتورها"), actionChevron);
  card.append(action);

  return card;
}
