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
 * The card is a plain container and the links inside it are the links. It was
 * one anchor around everything for a while, which made the whole surface react
 * to a pointer — and once there were two places to go rather than one, a single
 * target could no longer say which. The footer row carries both, and each
 * answers for itself.
 */
export function createInvoicesEntry({ href = "#finance/invoices" } = {}) {
  const card = element("div", "overview-card invoices-entry");

  const head = element("header", "overview-card__head invoices-entry__head");
  const mark = element("span", "invoices-entry__mark");
  const icon = reportIcon("invoices");
  icon.setAttribute("class", "invoices-entry__icon");
  mark.append(icon);
  head.append(mark, element("h2", "overview-card__title", "فاکتورها"));
  card.append(head);

  card.append(
    element(
      "p",
      "invoices-entry__lead",
      "ثبت فاکتور جدید و مشاهده فهرست فاکتورها با وضعیت، فروشنده، مبلغ و جزئیات هر خط.",
    ),
  );

  const tags = element("ul", "invoices-entry__tags");
  ["ثبت فاکتور", "فهرست و وضعیت", "تأیید و ابطال"].forEach((label) => {
    tags.append(element("li", "", label));
  });
  card.append(tags);

  const action_buttons = element("div", "action_buttons");
  card.append(action_buttons);

  // The card no longer carries the href, so this line is what goes to فاکتورها.
  const action = element("a", "invoices-entry__action");
  action.href = href;
  action.setAttribute(
    "aria-label",
    "ورود به بخش فاکتورها — ثبت و مشاهده فاکتورهای پروژه",
  );
  const actionChevron = chevronIcon("forward");
  actionChevron.setAttribute("class", "invoices-entry__chevron");
  action.append(document.createTextNode("ورود به بخش فاکتورها"), actionChevron);
  action_buttons.append(action);

  const invoice_registration = element(
    "a",
    "invoice_registration",
    "ثبت با تصویر یا صدا",
  );
  invoice_registration.href = "#finance/invoice-files";
  action_buttons.append(invoice_registration);

  return card;
}
