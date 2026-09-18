import { element } from "../../shared/dom/elements.js";
import { formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";

/* Entering a daily price by hand, for the items the market sheet will never price.
 *
 * WHY THIS EXISTS
 * «برچیدن جدول» is 3,538 metres of demolition. No supplier quotes it, no worksheet will
 * ever carry it, and no conversion rule will conjure one — yet it is a real cost that has
 * to appear in the customer's financial report. Waiting for the sheet to cover it would
 * leave that row, and the report total above it, permanently blank.
 *
 * WHAT IT WRITES, AND WHAT THAT MEANS
 * A price VERSION against the cost item — `POST /resources/{id}/prices` — not a figure
 * stored on this one row. That is the module's existing mechanism for "a person decided
 * this price", it is versioned, and it carries a reason and an author.
 *
 * It follows that the price applies to EVERY line that uses this item, not only the row
 * the button was pressed on. That is said plainly in the dialog rather than discovered
 * afterwards: a person entering a rate for «برچیدن جدول» is entering the rate for
 * demolishing a metre of kerb, which is the same rate wherever it is demolished. What
 * differs per row is the quantity, and the row's cost follows from it.
 *
 * SCOPE IS A CHOICE AND HAS NO DEFAULT BEYOND THE SAFE ONE
 * `project` affects this project alone; `organization` affects every project the tenant
 * runs. The dialog opens on `project`, because the narrower claim is the one somebody can
 * make from what is in front of them.
 */

function field(labelText, control, hint = null) {
  const wrapper = element("div", "form-field");
  const id = `manual-price-${Math.random().toString(36).slice(2, 9)}`;
  control.id = id;
  const label = element("label", "form-label", labelText);
  label.htmlFor = id;
  wrapper.append(label, control);
  if (hint) wrapper.append(element("p", "table-note", hint));
  return wrapper;
}

/**
 * @param line      the estimate line the button was pressed on — for its quantity
 * @param resource  the cost item the price is actually written against
 * @param current   the unit price in force now, or null
 * @param adapter   anything with `createPriceVersion({ resourceId, scope, unitPriceIRR, effectiveFrom, reason })`
 */
export function createManualPriceDialog({ line, resource, current = null, adapter, onSaved, onClose }) {
  const dialog = element("dialog", "manual-price-dialog");
  dialog.setAttribute("aria-label", "ثبت دستی قیمت روز");

  const unitLabel = formatUnitLabel(resource?.baseUnit ?? line?.mppUnit) ?? "واحد";
  const quantity = line?.revisedQuantity ?? line?.originalQuantity ?? null;

  const head = element("header", "manual-price-dialog__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { dialog.close(); onClose?.(); });
  head.append(
    element("h2", "", current ? "ویرایش قیمت روز" : "ثبت دستی قیمت روز"),
    close);

  const facts = element("dl", "manual-price-dialog__facts");
  facts.append(
    element("dt", "", "قلم هزینه"), element("dd", "", resource?.title ?? "—"),
    element("dt", "", "واحد"), element("dd", "", unitLabel));
  if (current) {
    facts.append(element("dt", "", "قیمت فعلی"),
                 element("dd", "numeric", formatTomanFromIrr(current)));
  }

  const priceInput = element("input", "app-input");
  priceInput.type = "text";
  priceInput.name = "unitPrice";
  priceInput.inputMode = "decimal";
  priceInput.autocomplete = "off";

  const scopeSelect = element("select", "app-select");
  scopeSelect.name = "scope";
  /* Project first, and it is the one the dialog opens on: the narrower claim is the one
     somebody can make from the row in front of them. */
  [["project", "فقط این پروژه"], ["organization", "کل سازمان"]].forEach(([value, label]) => {
    const option = element("option", "", label);
    option.value = value;
    scopeSelect.append(option);
  });

  const effectiveFrom = element("input", "app-input");
  effectiveFrom.type = "date";
  effectiveFrom.name = "effectiveFrom";
  effectiveFrom.value = getTehranTodayIso();

  const reason = element("textarea", "app-textarea");
  reason.name = "reason";
  reason.rows = 2;
  reason.placeholder = "این قیمت از کجا آمده است؟";

  /* What the row will come to, recomputed as the number is typed. The price is per unit
     and the row is a quantity of them, and a person entering a rate is entitled to see
     the figure it produces before they commit to it. */
  const outcome = element("p", "manual-price-dialog__outcome", "");
  function renderOutcome() {
    const irr = tomanInputToIrr(priceInput.value);
    /* Both have to be exact integers before anything is multiplied. A quantity of
       «3538.1100» is a decimal string, and rounding it to feed a BigInt would quietly
       change the figure this line is about — so a fractional quantity produces no
       preview rather than a wrong one. The row's real cost is the server's to compute. */
    const whole = /^\d+$/.test(String(irr ?? "")) && /^\d+(\.0+)?$/.test(String(quantity ?? ""));
    if (!whole) { outcome.textContent = ""; return; }
    const total = BigInt(irr) * BigInt(String(quantity).split(".")[0]);
    outcome.replaceChildren(
      element("span", "", `${quantity} ${unitLabel}`),
      element("span", "manual-price-dialog__times", "×"),
      element("span", "", formatTomanFromIrr(irr, { withCurrency: false })),
      element("span", "manual-price-dialog__equals", "="),
      element("strong", "", formatTomanFromIrr(String(total), { withCurrency: false })));
  }

  const feedback = element("p", "form-feedback", "");
  const save = element("button", "button button--primary", "ثبت قیمت");
  save.type = "button";
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => { dialog.close(); onClose?.(); });
  const actions = element("div", "manual-price-dialog__actions");
  actions.append(save, cancel);

  const form = element("form", "manual-price-dialog__form");
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(
    field(`قیمت هر ${unitLabel}`, priceInput),
    outcome,
    field("دامنهٔ اعمال", scopeSelect,
          "این قیمت برای قلم هزینه ثبت می‌شود، پس روی همهٔ سطرهایی که از همین قلم استفاده می‌کنند اعمال می‌شود."),
    field("از تاریخ", effectiveFrom),
    field("دلیل", reason),
    actions,
    feedback);

  dialog.append(head, facts, form);
  priceInput.addEventListener("input", renderOutcome);

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    const irr = tomanInputToIrr(priceInput.value);
    if (!/^\d+$/.test(irr)) { feedback.textContent = "قیمت را وارد کنید."; return; }
    if (!reason.value.trim()) { feedback.textContent = "دلیل ثبت این قیمت الزامی است."; return; }
    if (!effectiveFrom.value) { feedback.textContent = "تاریخ شروع اعتبار را انتخاب کنید."; return; }

    save.disabled = true;
    try {
      await adapter.createPriceVersion({
        resourceId: resource.resourceId,
        scope: scopeSelect.value,
        unitPriceIRR: irr,
        effectiveFrom: effectiveFrom.value,
        reason: reason.value.trim(),
      });
      dialog.close();
      onSaved?.();
    } catch (error) {
      feedback.textContent = error?.message ?? "ثبت قیمت انجام نشد.";
      save.disabled = false;
    }
  });

  return {
    element: dialog,
    open() {
      document.body.append(dialog);
      showAccessibleDialog(dialog, { initialFocus: priceInput });
    },
  };
}
