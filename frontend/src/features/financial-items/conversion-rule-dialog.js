import { element } from "../../shared/dom/elements.js";
import { formatUnitLabel, formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getUnitDefinition } from "../prices/unit-conversions-validation.js";
import { convertedUnitPriceIRR, lineCostIRR, occupantsOf, rulesForCrossing }
  from "./conversion-rule-math.js";

/* Defining the crossing between a price's unit and an item's unit, without leaving the
 * item.
 *
 * WHY THIS IS A DIALOG AND NOT A LINK
 * A person hits «نیازمند ضریب تبدیل» while choosing a product for one estimate line. Every
 * fact the rule needs is already on the screen they are looking at: which product, which
 * supplier, which category, and both units. Sending them to a settings page means asking
 * them to carry six values in their head and find their way back to the row they were on.
 *
 * THREE QUESTIONS, IN THE ORDER A PERSON CAN ANSWER THEM
 *
 *   1. what already answers this crossing   — so nobody writes a rule that exists
 *   2. what do you know, and how widely      — the claim, and how far it reaches
 *   3. what will that do to the price        — the only way the claim can be checked
 *
 * The third is the point of the whole feature. A rule exists so a daily price appears, and
 * a person who cannot see the price a rule produces cannot tell a correct rule from one
 * that is wrong by the square of its factor. The arithmetic lives in
 * `conversion-rule-math.js`, exactly matching the server's own division.
 *
 * DIRECTION IS CHOSEN, NEVER INFERRED
 * The rule reads «۱ <from> = factor <to>», and WHICH unit is the one is the person's
 * choice, because only one of the two directions is a thing anybody knows. Somebody knows
 * that a branch of angle weighs twenty-two kilograms; nobody knows offhand that a kilogram
 * is 0.0454545… of a branch, and made to type that they would round it and bake the
 * rounding into every price the rule ever produces. So both questions are offered, the
 * answer is stored exactly as stated, and the server reads the rule from either side.
 *
 * Neither direction is preselected. Read the wrong way round, «۱ شاخه = ۲۲ کیلوگرم»
 * becomes a claim that a kilogram weighs twenty-two branches — a price wrong by a factor
 * of 484 while looking entirely plausible. A default would be right about half the time
 * and silently wrong the rest, so the sentence has to be one somebody actually picked.
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
    hint: "برای همهٔ پروژه‌های این سازمان، در هر پروژه‌ای که همین دو واحد به هم برسند." },
  { value: "global", label: "کل بامبو",
    hint: "برای همهٔ سازمان‌ها و همهٔ پروژه‌ها." },
]);

const SCOPE_LABELS = Object.fromEntries(SCOPES.map((scope) => [scope.value, scope.label]));

/* The scopes whose claim outlives this project. The service names the same two, and this
   is the only place the interface repeats them -- not to enforce anything, which is the
   server's job, but so a choice nobody here can make is not presented as available. */
const TENANT_WIDE_SCOPES = Object.freeze(new Set(["organization", "global"]));

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

function section(titleText, modifier) {
  const node = element("section",
    `conversion-rule-dialog__section conversion-rule-dialog__section--${modifier}`);
  node.append(element("h3", "conversion-rule-dialog__section-title", titleText));
  return node;
}

/** «۱ شاخه = ۲۲ کیلوگرم», from a rule as the server stores it. */
export function ruleSentence(rule) {
  const from = formatUnitLabel(rule?.fromUnit) ?? rule?.fromUnit ?? "—";
  const to = formatUnitLabel(rule?.toUnit) ?? rule?.toUnit ?? "—";
  const factor = rule?.factorValue == null ? "—" : formatDisplayNumber(rule.factorValue);
  return `۱ ${from} = ${factor} ${to}`;
}

/** What a stored rule is, in one line: its claim, how far it reaches, and whether it counts. */
export function ruleSummary(rule) {
  const scope = SCOPE_LABELS[rule?.scopeType] ?? rule?.scopeType ?? "—";
  const state = rule?.status === "approved" ? "در حال اعمال" : "پیش‌نویس، بدون اثر";
  return `${ruleSentence(rule)} — ${scope} · ${state}`;
}

/**
 * @param context.fromUnit      the unit the market price is quoted in
 * @param context.toUnit        the unit this estimate line is measured in
 * @param context.sourcePriceIRR  today's price, per `fromUnit`, as a decimal string
 * @param context.quantity      this line's own quantity, for the cost preview
 * @param context.providerItemId, providerId, category  what the chosen listing is
 * @param context.productName, providerName, categoryLabel  what to show a person
 * @param onSaved  called after the server accepts the rule, so the caller can recalculate
 */
export function createConversionRuleDialog({ context, adapter, canManageSettings = true, onSaved, onClose }) {
  const dialog = element("dialog", "conversion-rule-dialog");
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
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

  // ------------------------------------------------------- 1. what already answers this

  /* Read before anything is typed, because the commonest correct action on a crossing that
     already has a rule is to leave it alone, and the second commonest is to replace it.
     Neither is possible for somebody who cannot see that the rule exists -- they write a
     second one, and either the database refuses it or the tenant ends up with two answers
     to one question. */
  let existingRules = [];
  const existingBody = element("div", "conversion-rule-dialog__existing");
  const existingSection = section("قانون‌هایی که همین حالا برای این دو واحد ثبت شده‌اند", "existing");
  existingSection.append(existingBody);
  existingBody.append(element("p", "table-note", "در حال خواندن…"));

  function renderExisting() {
    existingBody.replaceChildren();
    const live = rulesForCrossing(existingRules, {
      fromUnit: context.fromUnit, toUnit: context.toUnit });
    if (!live.length) {
      existingBody.append(element("p", "table-note",
        "هیچ قانونی برای این عبور ثبت نشده است. این اولین قانون خواهد بود."));
      return;
    }
    const list = element("ul", "conversion-rule-dialog__rules");
    live.forEach((rule) => {
      const item = element("li", "conversion-rule-dialog__rule");
      item.dataset.scope = rule.scopeType ?? "";
      item.dataset.status = rule.status ?? "";
      item.append(element("span", "", ruleSummary(rule)));
      list.append(item);
    });
    existingBody.append(list);
    /* Said once, plainly, rather than left for somebody to infer from six rows: the
       narrowest rule is the one that answers, and a broad rule they can see is not
       necessarily the one producing the number in front of them. */
    existingBody.append(element("p", "table-note",
      "وقتی چند قانون هست، باریک‌ترین آن‌ها اعمال می‌شود: محصول، بعد تأمین‌کننده و دسته، "
      + "بعد پروژه، بعد سازمان، و در آخر کل بامبو."));
  }

  // -------------------------------------------------------------- 2. stating the claim

  /* The two ways the same crossing can be stated. `forward` is the direction the pricing
     path asks in -- price unit to line unit -- and `reverse` is the same measurement read
     backwards. Both are stored as they are said: the row's own `from_unit`/`to_unit`
     ordering IS the direction, which is why neither needs converting before it is sent. */
  const DIRECTIONS = Object.freeze([
    { value: "forward", from: context.fromUnit, to: context.toUnit,
      fromLabel, toLabel },
    { value: "reverse", from: context.toUnit, to: context.fromUnit,
      fromLabel: toLabel, toLabel: fromLabel },
  ]);

  const scopeSelect = element("select", "app-select");
  scopeSelect.name = "scopeType";
  /* A scope beyond this project is refused in the SERVICE, never at the route, so nothing
     about the request reveals it in advance -- the route takes `finance.edit` and only the
     wider claim is turned down, at the end of a form somebody has already filled in. The
     capability is asked for instead, and the choices this account cannot make are offered
     disabled with the reason attached rather than removed: a person who needs «کل سازمان»
     has to be able to see that it exists and that it is somebody else's to grant. */
  SCOPES.forEach((scope) => {
    const option = element("option", "", scope.label);
    option.value = scope.value;
    if (TENANT_WIDE_SCOPES.has(scope.value) && !canManageSettings) {
      option.disabled = true;
      option.textContent = `${scope.label} — نیازمند دسترسی «مدیریت تنظیمات مالی»`;
    }
    scopeSelect.append(option);
  });
  const scopeHint = element("p", "table-note", SCOPES[0].hint);

  const factorInput = element("input", "app-input");
  factorInput.type = "text";
  factorInput.name = "factorValue";
  factorInput.inputMode = "decimal";
  factorInput.autocomplete = "off";
  factorInput.id = `conversion-factor-${Math.random().toString(36).slice(2, 9)}`;

  /* Nothing is preselected, and `chosen` stays null until somebody picks. Read from here
     rather than from the inputs' `checked`, so the answer does not depend on the browser
     enforcing radio-group exclusivity. */
  let chosen = null;
  const directionInputs = new Map();
  const directionGroup = element("fieldset", "conversion-rule-dialog__direction");
  directionGroup.append(element("legend", "form-label", "کدام طرف را می‌دانید؟"));
  const groupName = `conversion-direction-${Math.random().toString(36).slice(2, 9)}`;
  DIRECTIONS.forEach((direction) => {
    const input = element("input", "");
    input.type = "radio";
    input.name = groupName;
    input.value = direction.value;
    const row = element("label", "conversion-rule-dialog__direction-row");
    row.append(input, element("span", "",
      `۱ ${direction.fromLabel} چند ${direction.toLabel} است؟`));
    input.addEventListener("change", () => {
      if (!input.checked) return;
      chosen = direction;
      /* Unchecked explicitly rather than left to the group: the same line then behaves in
         the test DOM, which has no notion of a radio group, as it does in a browser. */
      directionInputs.forEach((other, value) => {
        if (value !== direction.value) other.checked = false;
      });
      feedback.textContent = "";
      renderEffect();
    });
    directionInputs.set(direction.value, input);
    directionGroup.append(row);
  });

  const factorField = element("div", "form-field");
  const factorLabel = element("label", "form-label", "");
  factorLabel.htmlFor = factorInput.id;
  factorField.append(factorLabel, factorInput);

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

  /* Every live rule this scope already holds. Set by `syncReplacement`, read by the save
     handler, and the reason the button sometimes says «جایگزینی».

     A list rather than one rule, because the live project has a listing holding an approved
     `kg→branch` AND an approved `branch→kg` at the same scope -- both written before the
     server started refusing the pair. Closing one of them would leave the other in force
     and the new rule would then be refused by the unique index. */
  let replacing = [];
  const replaceNote = element("p", "conversion-rule-dialog__replacing", "");
  replaceNote.hidden = true;

  function syncReplacement() {
    replacing = occupantsOf(existingRules, {
      scopeType: scopeSelect.value,
      fromUnit: context.fromUnit,
      toUnit: context.toUnit,
      providerItemId: context.providerItemId,
      providerId: context.providerId,
      category: context.category,
    });
    replaceNote.hidden = replacing.length === 0;
    if (replacing.length) {
      /* Named with its number and its direction, because «قانونی وجود دارد» tells somebody
         nothing about whether the one that exists is the one they were about to write. And
         when there are several, all of them: a person about to close two rules has to see
         both, or the one they did not read disappears without their noticing. */
      const named = replacing.map((rule) => `${ruleSentence(rule)}`
        + `${rule.version ? ` (نسخهٔ ${formatDisplayNumber(rule.version)})` : ""}`
        + `${rule.status === "approved" ? "" : " — پیش‌نویس"}`).join(" و ");
      replaceNote.textContent = replacing.length === 1
        ? `این دامنه قانون دارد: ${named}. اگر ذخیره کنید، این قانون بسته می‌شود و قانون شما جای آن را می‌گیرد.`
        : `این دامنه ${formatDisplayNumber(replacing.length)} قانون فعال دارد: ${named}. `
          + "اگر ذخیره کنید، همهٔ آن‌ها بسته می‌شوند و قانون شما جای آن‌ها را می‌گیرد.";
    }
    save.textContent = saved ? "تأیید و اعمال قانون"
      : replacing.length ? "جایگزینی قانون" : "ثبت و اعمال قانون";
  }

  // ---------------------------------------------------------- 3. what it does to the price

  /* The sentence the number completes, written out with the real unit names so nobody has
     to work out which way round it goes -- and, before a direction is picked, saying that
     there is nothing to read yet rather than showing one of the two and inviting the
     number to be typed against it. */
  const sentence = element("p", "conversion-rule-dialog__sentence", "");
  const effect = element("dl", "conversion-rule-dialog__effect");
  const effectNote = element("p", "table-note", "");

  function renderEffect() {
    effect.replaceChildren();
    effectNote.textContent = "";
    if (!chosen) {
      factorLabel.textContent = "ضریب تبدیل";
      factorInput.disabled = true;
      sentence.textContent = "ابتدا مشخص کنید کدام طرف را می‌دانید.";
      return;
    }
    factorLabel.textContent =
      `ضریب تبدیل — یک ${chosen.fromLabel} چند ${chosen.toLabel} است؟`;
    factorInput.disabled = false;
    const value = factorInput.value.trim();
    sentence.textContent =
      `۱ ${chosen.fromLabel} = ${value === "" ? "…" : value} ${chosen.toLabel}`;

    /* The price this rule would produce, worked out here and now. Without a sheet price
       there is nothing to show and the dialog says so rather than drawing an empty row --
       a listing with no validated observation is a normal state, not a fault. */
    if (!context.sourcePriceIRR) {
      effectNote.textContent =
        "قیمت روزی برای این محصول ثبت نشده، پس نتیجهٔ این ضریب اینجا قابل نمایش نیست.";
      return;
    }
    const unitPrice = convertedUnitPriceIRR({
      priceIRR: context.sourcePriceIRR,
      sourceUnit: context.fromUnit,
      selectedUnit: context.toUnit,
      statedFrom: chosen.from,
      statedTo: chosen.to,
      factor: value,
    });
    if (unitPrice === null) {
      effectNote.textContent = "عدد ضریب را وارد کنید تا نتیجه‌اش را ببینید.";
      return;
    }
    effect.append(
      element("dt", "", `قیمت برگه، بابت هر ${fromLabel}`),
      element("dd", "numeric", formatTomanFromIrr(context.sourcePriceIRR)),
      element("dt", "", `قیمت روز این قلم، بابت هر ${toLabel}`),
      element("dd", "numeric conversion-rule-dialog__result",
              formatTomanFromIrr(unitPrice)));
    const cost = lineCostIRR({ unitPriceIRR: unitPrice, quantity: context.quantity });
    if (cost !== null) {
      effect.append(
        element("dt", "", `هزینهٔ این ردیف (${formatDisplayNumber(context.quantity)} ${toLabel})`),
        element("dd", "numeric", formatTomanFromIrr(cost)));
    }
    /* The one check nobody else can do for them. The units and the number can both be
       right and the rule still be backwards, and the resulting price is where that shows. */
    effectNote.textContent = "اگر این عدد با آنچه انتظار دارید نمی‌خواند، جهت یا ضریب را عوض کنید.";
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

  const claim = section("قانون شما", "claim");
  claim.append(
    field("دامنهٔ اعمال", scopeSelect),
    scopeHint,
    replaceNote,
    directionGroup,
    factorField,
    field("دلیل و مبنا", reason),
    acknowledgeRow);

  const result = section("پیش از ذخیره، نتیجه را ببینید", "effect");
  result.append(sentence, effect, effectNote);

  const form = element("form", "conversion-rule-dialog__form");
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(existingSection, claim, result, actions, feedback, note);

  dialog.append(head, facts, form);

  scopeSelect.addEventListener("change", () => {
    scopeHint.textContent = SCOPES.find((s) => s.value === scopeSelect.value)?.hint ?? "";
    feedback.textContent = "";
    syncAcknowledge();
    syncReplacement();
  });
  syncAcknowledge();
  syncReplacement();
  renderExisting();
  renderEffect();
  factorInput.addEventListener("input", renderEffect);

  /* Fetched, not required. A host that has not wired the settings endpoint still gets a
     working dialog -- it simply cannot show what already exists, and says so rather than
     claiming there is nothing. */
  async function loadExisting() {
    if (typeof adapter?.conversionRules !== "function") {
      existingBody.replaceChildren(element("p", "table-note",
        "فهرست قانون‌های موجود در این نسخه در دسترس نیست."));
      return;
    }
    try {
      /* Both spellings, because a rule stating «۱ شاخه = ۲۲ کیلوگرم» answers this crossing
         and is stored the other way round from the way this row asks about it. */
      const [direct, reverse] = await Promise.all([
        adapter.conversionRules({ fromUnit: context.fromUnit, toUnit: context.toUnit }),
        adapter.conversionRules({ fromUnit: context.toUnit, toUnit: context.fromUnit }),
      ]);
      const byId = new Map();
      [...(direct?.items ?? []), ...(reverse?.items ?? [])]
        .filter(Boolean).forEach((rule) => byId.set(rule.id, rule));
      existingRules = [...byId.values()];
      renderExisting();
      syncReplacement();
    } catch (error) {
      existingBody.replaceChildren(element("p", "table-note",
        error?.message ?? "خواندن قانون‌های موجود انجام نشد."));
    }
  }

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    const scopeType = scopeSelect.value;
    const factor = factorInput.value.trim();

    /* Before the number, because a number with no direction is not half an answer -- it is
       an answer to a question nobody asked. */
    if (!chosen) {
      feedback.textContent = "مشخص کنید کدام طرف را می‌دانید."; return;
    }

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
      /* THREE CALLS, ONE ACT, AND THE ORDER IS THE WHOLE SAFETY OF IT.
         A rule arrives as a DRAFT, and a draft changes no number anywhere: both resolution
         queries filter `status='approved'` in SQL and the domain resolver filters again. So
         a dialog that only created one would let somebody write «۱ شاخه = ۲۲ کیلوگرم»,
         watch it save, and find the row still saying «نیازمند ضریب تبدیل» — the feature
         working perfectly and doing nothing.

         When a rule already holds this scope it has to be CLOSED between the two, and in
         that order. The database's partial unique index permits one approved, open rule per
         scope and unit pair, so approving first would be refused outright; and closing
         first, before the replacement exists, would leave the crossing unanswered if the
         write then failed. Create, close, approve: at every moment either the old rule or
         the new one is the answer, and the only gap is one a second press closes.

         Approving is not a second decision here. Creating and approving pass through the
         same permission gate, including the extra one the tenant-wide scopes carry, so a
         person who could write it can put it in force. What the steps buy is a record: the
         rule says who stated it and who let it count, even when that is one person. */
      const created = saved ?? await adapter.createConversionRule({
        scopeType,
        /* The direction the person chose, sent as they said it. Inverting here would put a
           number nobody can check against the seller's sheet into the audit record, and
           would round once and for all -- the resolver inverts at full precision instead,
           at the moment of calculation. */
        fromUnit: chosen.from,
        toUnit: chosen.to,
        conversionMethod: "factor",
        factorValue: factor,
        reason: reason.value.trim(),
        /* Coerced, and always sent. An absent key and a false one are the same JSON, so
           omitting it would make «I did not admit this» indistinguishable from «this client
           is too old to know about admissions» -- and the server would be right to read the
           second as the first only by luck. */
        productDependentAcknowledged: Boolean(acknowledge.checked),
        /* Recorded on the new rule so the chain is readable. It does NOT close the old one
           -- the server only stores the link -- which is why the call below exists. */
        ...(replacing.length ? { supersedesRuleId: replacing[0].id } : {}),
        ...(needs ? { [needs]: context[needs] } : {}),
      });
      /* Remembered BEFORE anything else is attempted. If a later step fails the rule
         exists, and pressing the button again must finish that rule rather than write a
         second one — two identical rules differing only in which is approved is a worse
         state than the draft we are recovering from. */
      saved = created;
      if (replacing.length && typeof adapter.supersedeConversionRule === "function") {
        /* One at a time and in order, emptying the list as each closes. A second press
           after a failure then finishes what is left rather than closing a rule twice --
           the server answers «این قانون پیش‌تر بسته شده است» to that, which would read as
           the whole replacement having failed. */
        while (replacing.length) {
          await adapter.supersedeConversionRule(replacing[0].id, {
            reason: reason.value.trim() });
          replacing = replacing.slice(1);
        }
      }
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
      loadExisting();
    },
    /* Exposed for the page's own tests and for a caller that wants the list ready before
       the dialog is on screen. Never required: `open` does it. */
    loadExisting,
  };
}
