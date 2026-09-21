import { element } from "../../shared/dom/elements.js";
import { formatUnitLabel } from "../../shared/formatters/display.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getUnitOptions } from "../prices/unit-conversions-validation.js";

/* Saying what the sheet's price is a price OF.
 *
 * THE STEP BEFORE THE CONVERSION, WHICH HAD NO WAY IN
 * A conversion answers «۱ کیسه چند کیلوگرم است». It cannot answer «قیمت این محصول بابت
 * چیست», and without that there is nothing to convert FROM: «نامعلوم» to «کیلوگرم» is not
 * a crossing any factor bridges. Measured on this project, that is where the linked rows
 * actually stop — five of them read «واحد قیمت مبدأ مشخص نیست» and not one reads «نیازمند
 * ضریب تبدیل». The sheet states a unit for rebar and for nothing else.
 *
 * So the pricing panel used to offer, on those rows, a button that opened itself and then
 * showed no way forward at all.
 *
 * WHAT IT WRITES, AND HOW FAR IT REACHES
 * A LABEL on the listing — `POST /material-prices/{id}/labels` — which is the module's
 * existing record for «what a person says this listing is». The imported row is never
 * touched: a label sits beside it, is versioned, and carries a reason.
 *
 * It is scoped to this project, because `provider_item_labels` is, and that is the honest
 * shape: each project imports its own copy of the sheet, so this describes the copy in
 * front of you. The CONVERSION is the part that travels — «۱ کیسه = ۴ کیلوگرم» can be
 * stated for the organization or for all of BAMBO — and it is a separate dialog for
 * exactly that reason. Saying the unit and stating the crossing are two different claims
 * with two different reaches, and a form that did both at one scope would quietly narrow
 * the one that should be wide.
 */

function field(labelText, control, hint = null) {
  const wrapper = element("div", "form-field");
  const id = `source-unit-${Math.random().toString(36).slice(2, 9)}`;
  control.id = id;
  const label = element("label", "form-label", labelText);
  label.htmlFor = id;
  wrapper.append(label, control);
  if (hint) wrapper.append(element("p", "table-note", hint));
  return wrapper;
}

function option(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

/**
 * @param context.providerItemId  the listing whose price has no stated basis
 * @param context.productName, providerName, rawPrice  what to show, so the person can judge
 * @param context.selectedUnit    the unit this estimate line is measured in, as context
 * @param adapter                 needs `saveLabel(providerItemId, values)`
 * @param onSaved                 called after the service accepts it, so the caller recalculates
 */
export function createSourceUnitDialog({ context, adapter, onSaved, onClose }) {
  const dialog = element("dialog", "source-unit-dialog");
  dialog.setAttribute("aria-label", "مشخص‌کردن واحد قیمت");

  const head = element("header", "source-unit-dialog__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { dialog.close(); onClose?.(); });
  head.append(element("h2", "", "قیمت این محصول بابت چیست؟"), close);

  /* What is on screen already, restated so the person is judging the right row. The raw
     price is included deliberately: «۹۲۵٬۶۰۰» beside a product name is often the only clue
     to whether the sheet meant a kilogram or a whole branch. */
  const facts = element("dl", "source-unit-dialog__facts");
  const fact = (term, value) => {
    if (!value) return;
    facts.append(element("dt", "", term), element("dd", "", value));
  };
  fact("محصول", context.productName);
  fact("تأمین‌کننده", context.providerName);
  fact("قیمت اعلامی برگه", context.rawPrice);
  if (context.selectedUnit) {
    fact("واحد این ردیف برآورد", formatUnitLabel(context.selectedUnit));
  }

  const unitSelect = element("select", "app-select");
  unitSelect.name = "sourceUnit";
  unitSelect.append(option("", "انتخاب کنید"));
  /* The registry the rest of the module uses, and nothing else. A unit invented here would
     be one no conversion could ever bridge. */
  getUnitOptions().forEach((unit) => unitSelect.append(option(unit.value, unit.label)));

  const reason = element("textarea", "app-textarea");
  reason.name = "reason";
  reason.rows = 2;
  reason.maxLength = 500;
  reason.placeholder = "از کجا می‌دانید؟ مثلاً ستون واحد در برگه، یا تماس با تأمین‌کننده";

  const feedback = element("p", "form-feedback", "");
  const save = element("button", "button button--primary", "ثبت واحد قیمت");
  save.type = "button";
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => { dialog.close(); onClose?.(); });
  const actions = element("div", "source-unit-dialog__actions");
  actions.append(save, cancel);

  const form = element("form", "source-unit-dialog__form");
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(
    field("واحد قیمت این محصول", unitSelect,
          "این فقط می‌گوید قیمت برگه بابت چیست. اگر با واحد ردیف برآورد یکی نبود، مرحلهٔ بعد ضریب تبدیل است."),
    field("دلیل", reason),
    actions,
    feedback);

  dialog.append(head, facts, form);

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    if (!unitSelect.value) { feedback.textContent = "واحد قیمت را انتخاب کنید."; return; }
    if (!reason.value.trim()) { feedback.textContent = "دلیل ثبت این واحد الزامی است."; return; }

    save.disabled = true;
    try {
      await adapter.saveLabel(context.providerItemId, {
        sourceUnit: unitSelect.value,
        reason: reason.value.trim(),
      });
      dialog.close();
      onSaved?.();
    } catch (error) {
      /* The service's own sentence. It validates the unit against the registry and knows
         which listing it refused, which is more than this dialog does. */
      feedback.textContent = error?.message ?? "ثبت واحد قیمت انجام نشد.";
      save.disabled = false;
    }
  });

  return {
    element: dialog,
    open() {
      document.body.append(dialog);
      showAccessibleDialog(dialog, { initialFocus: unitSelect });
    },
  };
}
