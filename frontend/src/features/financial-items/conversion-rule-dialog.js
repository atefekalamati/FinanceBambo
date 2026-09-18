import { element } from "../../shared/dom/elements.js";
import { formatUnitLabel } from "../../shared/formatters/display.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getUnitDefinition } from "../prices/unit-conversions-validation.js";

/* Defining the crossing between a price's unit and an item's unit, without leaving the
 * item.
 *
 * WHY THIS IS A DIALOG AND NOT A LINK
 * A person hits «نیازمند ضریب تبدیل» while choosing a product for one estimate line. Every
 * fact the rule needs is already on the screen they are looking at: which product, which
 * supplier, which category, and both units. Sending them to a settings page means asking
 * them to carry six values in their head and find their way back to the row they were on.
 *
 * WHAT IT DOES NOT DECIDE
 * The number. «۱ شاخه = ۲۲ کیلوگرم» is a weighing, and this dialog has no way to weigh
 * anything: it collects what a person measured, with their reason, and sends it to the
 * server to be stored and approved. There is no suggested factor and no arithmetic here.
 *
 * DIRECTION IS STATED, NEVER INFERRED
 * The rule reads «۱ <from> = factor <to>» and the sentence is on screen above the input,
 * built from the two real unit names. Read the other way round, «۱ شاخه = ۲۲ کیلوگرم»
 * becomes a claim that a kilogram weighs twenty-two branches, and the price that came out
 * of it would be wrong by a factor of 484 while looking entirely plausible.
 */

/* The scopes the server stores, widest last. `provider_category` is a precedence step the
   resolver applies, not something a person picks, so it is not offered here. */
const SCOPES = Object.freeze([
  { value: "provider_item", label: "فقط همین محصول",
    hint: "ایمن‌ترین حالت. وزن هر شاخه از این محصول اندازه‌گیری شده و برای محصول دیگری صادق نیست." },
  { value: "category", label: "همهٔ محصولات این دسته",
    hint: "برای همهٔ محصولات این دسته، از هر تأمین‌کننده." },
  { value: "provider", label: "همهٔ محصولات این تأمین‌کننده",
    hint: "برای هرچه این تأمین‌کننده می‌فروشد." },
  { value: "project", label: "کل این پروژه",
    hint: "فقط در این پروژه اعمال می‌شود." },
  { value: "organization", label: "کل سازمان",
    hint: "برای همهٔ پروژه‌های این سازمان." },
  { value: "global", label: "کل بامبو",
    hint: "برای همهٔ سازمان‌ها و همهٔ پروژه‌ها." },
]);

/* Which identifier each scope must carry. A `category` rule with no category is a rule
   about every category, which is not what the person choosing «این دسته» meant. */
const SCOPE_NEEDS = Object.freeze({
  provider_item: "providerItemId",
  category: "category",
  provider: "providerId",
});

/* Whether these two units measure different KINDS of thing.
 *
 * The same question `crosses_dimensions` asks on the server, asked here only to decide
 * whether to SHOW the acknowledgement -- never to decide whether the rule is allowed. That
 * remains the server's judgement, and this dialog has always refused to predict it.
 *
 * The registry is the one the items page already loaded from `/unit-registry`, so this is
 * not a second source of truth. A unit it does not know counts as crossing, exactly as the
 * server counts it: an unknown unit is not evidence that two things measure alike.
 */
function crossesDimensions(fromUnit, toUnit) {
  const from = getUnitDefinition(fromUnit);
  const to = getUnitDefinition(toUnit);
  if (!from || !to) return true;
  return from.dimension !== to.dimension;
}

function field(labelText, control, hint = null) {
  const wrapper = element("div", "form-field");
  const id = `conversion-${Math.random().toString(36).slice(2, 9)}`;
  control.id = id;
  const label = element("label", "form-label", labelText);
  label.htmlFor = id;
  wrapper.append(label, control);
  if (hint) wrapper.append(element("p", "table-note", hint));
  return wrapper;
}

/**
 * @param context.fromUnit      the unit the market price is quoted in
 * @param context.toUnit        the unit this estimate line is measured in
 * @param context.providerItemId, providerId, category  what the chosen listing is
 * @param context.productName, providerName, categoryLabel  what to show a person
 * @param onSaved  called after the server accepts the rule, so the caller can recalculate
 */
export function createConversionRuleDialog({ context, adapter, onSaved, onClose }) {
  const dialog = element("dialog", "conversion-rule-dialog");
  dialog.setAttribute("aria-label", "تعریف قانون تبدیل واحد");

  const fromLabel = formatUnitLabel(context.fromUnit) ?? context.fromUnit ?? "—";
  const toLabel = formatUnitLabel(context.toUnit) ?? context.toUnit ?? "—";

  const head = element("header", "conversion-rule-dialog__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { dialog.close(); onClose?.(); });
  head.append(element("h2", "", "تعریف قانون تبدیل واحد"), close);

  /* What is being reconciled, in the person's own words rather than in unit codes. The
     product is named because the rule they are about to write may be about it alone. */
  const facts = element("dl", "conversion-rule-dialog__facts");
  facts.append(
    element("dt", "", "واحد قیمت روز"), element("dd", "", fromLabel),
    element("dt", "", "واحد این قلم"), element("dd", "", toLabel));
  if (context.productName) {
    facts.append(element("dt", "", "محصول"), element("dd", "", context.productName));
  }
  if (context.providerName) {
    facts.append(element("dt", "", "تأمین‌کننده"), element("dd", "", context.providerName));
  }
  if (context.categoryLabel) {
    facts.append(element("dt", "", "دسته"), element("dd", "", context.categoryLabel));
  }

  const scopeSelect = element("select", "app-select");
  scopeSelect.name = "scopeType";
  SCOPES.forEach((scope) => {
    const option = element("option", "", scope.label);
    option.value = scope.value;
    scopeSelect.append(option);
  });
  const scopeHint = element("p", "table-note", SCOPES[0].hint);

  const factorInput = element("input", "app-input");
  factorInput.type = "text";
  factorInput.name = "factorValue";
  factorInput.inputMode = "decimal";
  factorInput.autocomplete = "off";

  /* The sentence the number completes, written out with the real unit names so nobody has
     to work out which way round it goes. */
  const sentence = element("p", "conversion-rule-dialog__sentence", "");
  function renderSentence() {
    const value = factorInput.value.trim();
    sentence.textContent = `۱ ${fromLabel} = ${value === "" ? "…" : value} ${toLabel}`;
  }
  renderSentence();

  const reason = element("textarea", "app-textarea");
  reason.name = "reason";
  reason.rows = 2;
  reason.placeholder = "این عدد از کجا آمده است؟ مثلاً وزن یک شاخه از برگهٔ فروشنده";

  /* THE ESCAPE HATCH.
     A rule whose units measure different KINDS of thing — a count against a mass — is a
     fact about ONE product: «۱ شاخه = ۲۲ کیلوگرم» is a weighing, and the next size of angle
     weighs something else. So the server refuses it at any scope broader than that one
     listing, which is right — except that the narrow scope it points at cannot be written
     until a listing is attached to the line, and on this project 832 of 835 lines have
     none. The refusal sent people to a locked door.

     It is now an admission instead of a refusal: the claim may be made, with a name and a
     moment stamped on it server-side, and every price that comes out of it reports that a
     broad claim stands behind it.

     SHOWN ONLY WHERE IT MEANS SOMETHING. On a crossing the registry can already do — tonne
     to kilogram — there is nothing to admit, and the server stores the flag as false
     however it arrives. A checkbox about responsibility, offered where no responsibility is
     being taken, teaches people to tick it without reading. */
  const acknowledge = element("input", "");
  acknowledge.type = "checkbox";
  acknowledge.name = "productDependentAcknowledged";
  const acknowledgeRow = element("label", "conversion-rule-dialog__acknowledge");
  acknowledgeRow.append(acknowledge, element("span", "",
    `این تبدیل به خودِ محصول بستگی دارد و برای محصول دیگری صادق نیست. با مسئولیت خودم آن را برای دامنهٔ انتخاب‌شده ثبت می‌کنم.`));

  /* Recomputed on every scope change, because the answer depends on the scope as well as
     on the units: the same crossing needs no admission at `provider_item`, where it is a
     statement about exactly the thing it was measured on. */
  function syncAcknowledge() {
    const wanted = crossesDimensions(context.fromUnit, context.toUnit)
      && scopeSelect.value !== "provider_item";
    acknowledgeRow.hidden = !wanted;
    if (!wanted) acknowledge.checked = false;
  }

  const feedback = element("p", "form-feedback", "");
  /* Set only when a rule was written and not put in force. Kept beside the feedback line
     because the two say different things: one is why the attempt failed, the other is what
     now exists in the database because of it. */
  const note = element("p", "table-note", "");
  note.hidden = true;
  /* The rule this dialog has already written, if any. */
  let saved = null;
  const save = element("button", "button button--primary", "ثبت و اعمال قانون");
  save.type = "button";
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => { dialog.close(); onClose?.(); });

  const actions = element("div", "conversion-rule-dialog__actions");
  actions.append(save, cancel);

  const form = element("form", "conversion-rule-dialog__form");
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(
    field("دامنهٔ اعمال", scopeSelect),
    scopeHint,
    field(`ضریب تبدیل — یک ${fromLabel} چند ${toLabel} است؟`, factorInput),
    sentence,
    field("دلیل و مبنا", reason),
    acknowledgeRow,
    actions,
    feedback,
    note);

  dialog.append(head, facts, form);

  scopeSelect.addEventListener("change", () => {
    scopeHint.textContent = SCOPES.find((s) => s.value === scopeSelect.value)?.hint ?? "";
    feedback.textContent = "";
    syncAcknowledge();
  });
  syncAcknowledge();
  factorInput.addEventListener("input", renderSentence);

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    const scopeType = scopeSelect.value;
    const factor = factorInput.value.trim();

    /* Checked here only to keep a person from waiting on a round trip for an empty box.
       Whether the number is ALLOWED at this scope is the server's judgement, and this
       dialog does not try to predict it. */
    if (!/^\d+(\.\d+)?$/.test(factor) || Number(factor) <= 0) {
      feedback.textContent = "ضریب تبدیل باید عددی بزرگ‌تر از صفر باشد."; return;
    }
    if (!reason.value.trim()) {
      feedback.textContent = "دلیل و مبنای این ضریب الزامی است."; return;
    }
    const needs = SCOPE_NEEDS[scopeType];
    if (needs && !context[needs]) {
      feedback.textContent = "برای این دامنه، محصول یا دسته یا تأمین‌کننده مشخص نیست.";
      return;
    }

    save.disabled = true;
    try {
      /* TWO CALLS, ONE ACT.
         A rule arrives as a DRAFT, and a draft changes no number anywhere: both resolution
         queries filter `status='approved'` in SQL and the domain resolver filters again. So
         a dialog that only created one would let somebody write «۱ شاخه = ۲۲ کیلوگرم»,
         watch it save, and find the row still saying «نیازمند ضریب تبدیل» — the feature
         working perfectly and doing nothing.

         Approving is not a second decision here. Creating and approving pass through the
         same permission gate, including the extra one the tenant-wide scopes carry, so a
         person who could write it can put it in force. What the two steps buy is a record:
         the rule says who stated it and who let it count, even when that is one person. */
      const created = saved ?? await adapter.createConversionRule({
        scopeType,
        fromUnit: context.fromUnit,
        toUnit: context.toUnit,
        conversionMethod: "factor",
        factorValue: factor,
        reason: reason.value.trim(),
        /* Coerced, and always sent. An absent key and a false one are the same JSON, so
           omitting it would make «I did not admit this» indistinguishable from «this client
           is too old to know about admissions» -- and the server would be right to read the
           second as the first only by luck. */
        productDependentAcknowledged: Boolean(acknowledge.checked),
        ...(needs ? { [needs]: context[needs] } : {}),
      });
      /* Remembered BEFORE the approve is attempted. If approving fails the rule exists, and
         pressing the button again must finish that rule rather than write a second one —
         two identical rules differing only in which is approved is a worse state than the
         draft we are recovering from. */
      saved = created;
      await adapter.approveConversionRule(created.id, { reason: reason.value.trim() });
      dialog.close();
      onSaved?.();
    } catch (error) {
      /* The server's own sentence, verbatim. It is written in Persian for the person who
         can act on it, and it says which scope was too broad and what to do instead —
         which is more than this page knows. */
      feedback.textContent = error?.message
        ?? (saved ? "قانون ثبت شد اما اعمال نشد." : "ثبت قانون تبدیل انجام نشد.");
      /* Said plainly rather than left to be discovered: the rule is in the database and is
         changing nothing. The button then says what pressing it will do, which is finish
         the rule already written, not write another. */
      if (saved) {
        note.textContent = "این قانون به‌صورت پیش‌نویس ذخیره شد و تا تأیید نشدن، روی هیچ قیمتی اثر ندارد.";
        note.hidden = false;
        save.textContent = "تأیید و اعمال قانون";
      }
      save.disabled = false;
    }
  });

  return {
    element: dialog,
    open() {
      document.body.append(dialog);
      showAccessibleDialog(dialog, { initialFocus: scopeSelect });
    },
  };
}
