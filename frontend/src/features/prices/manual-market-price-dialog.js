import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { getUnitOptions } from "./unit-conversions-validation.js";

/* A price for something the worksheet will never carry.
 *
 * WHY IT GOES IN THE SAME TABLE
 * «قیمت روز بازار» answers one question — what does this cost today — and it was answering
 * it from one source. But a sheet covers what suppliers publish, and a project buys things
 * no supplier publishes a price for. Those purchases had nowhere to be, so the page showed
 * a market and called it the prices.
 *
 * What is entered here becomes a LISTING in the same world a sheet row lives in: same
 * table, same chips, same paging. What marks it apart is `origin`, not where it is kept —
 * and that column is shown on امور مالی and withheld from the report, because a reader
 * asking what things cost is not being asked to weigh the sources against each other.
 *
 * THE CATEGORY IS NOT OPTIONAL
 * The chips ARE the categories: a price with none would be filed under a chip that does not
 * exist and would be reachable only by scrolling the whole sheet. So the category is asked
 * for, and when none of them fits, one is made here rather than somewhere else — a person
 * holding a quote for scaffolding should not have to leave, find a settings page, and come
 * back to the form they abandoned.
 */

/** How widely a chip somebody makes is meant to apply. */
const SCOPES = Object.freeze([
  { value: "project", label: "فقط این پروژه",
    hint: "در پروژه‌های دیگر همین سازمان دیده نمی‌شود." },
  { value: "organization", label: "کل سازمان",
    hint: "در همهٔ پروژه‌های این سازمان قابل انتخاب می‌شود." },
  { value: "global", label: "کل بامبو",
    hint: "در همهٔ سازمان‌ها و همهٔ پروژه‌ها قابل انتخاب می‌شود." },
]);

/** The value the category select carries when somebody wants a chip that is not there. */
const NEW_CATEGORY = "__new__";

function field(labelText, control, hint = null) {
  const wrapper = element("div", "form-field");
  const id = `manual-market-${Math.random().toString(36).slice(2, 9)}`;
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
 * @param categories  what `listCategories()` returned — chips from the sheet and declared ones alike
 * @param adapter     needs `createManualPrice` and `createCategory`
 * @param onSaved     called after the price is stored, so the caller can reload rows AND chips
 */
export function createManualMarketPriceDialog({ categories = [], adapter, onSaved, onClose }) {
  const dialog = element("dialog", "manual-market-price-dialog");
  dialog.setAttribute("aria-label", "ثبت دستی قیمت بازار");

  const head = element("header", "manual-market-price-dialog__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { dialog.close(); onClose?.(); });
  head.append(element("h2", "", "ثبت دستی قیمت بازار"), close);

  const productInput = element("input", "app-input");
  productInput.type = "text";
  productInput.name = "productName";
  productInput.maxLength = 200;
  productInput.autocomplete = "off";

  /* Every chip the project can see, in the order the list arrived — the service already
     merges the sheet's own categories with the declared ones, and re-sorting here would be
     this page having an opinion about an order it is not the author of. */
  const categorySelect = element("select", "app-select");
  categorySelect.name = "category";

  function fillCategories(list) {
    categorySelect.replaceChildren();
    categorySelect.append(option("", list.length ? "انتخاب کنید" : "دسته‌ای یافت نشد"));
    list.forEach((item) => {
      const count = Number(item.itemCount ?? 0);
      categorySelect.append(option(item.category,
        count ? `${item.label ?? item.category} · ${formatDisplayNumber(String(count))} قلم` : (item.label ?? item.category)));
    });
    categorySelect.append(option(NEW_CATEGORY, "+ دستهٔ جدید…"));
  }
  fillCategories(categories);

  /* The whole of making a chip, inline. Hidden until it is asked for, so the common case —
     a price that belongs to a category that already exists — stays a four-field form. */
  const newCategoryBox = element("div", "manual-market-price-dialog__new-category");
  newCategoryBox.hidden = true;
  const newCategoryName = element("input", "app-input");
  newCategoryName.type = "text";
  newCategoryName.name = "newCategory";
  newCategoryName.maxLength = 64;
  newCategoryName.autocomplete = "off";
  const scopeSelect = element("select", "app-select");
  scopeSelect.name = "scopeLevel";
  SCOPES.forEach((scope) => scopeSelect.append(option(scope.value, scope.label)));
  const scopeHint = element("p", "table-note", SCOPES[0].hint);
  scopeSelect.addEventListener("change", () => {
    scopeHint.textContent = SCOPES.find((s) => s.value === scopeSelect.value)?.hint ?? "";
  });
  newCategoryBox.append(
    field("نام دستهٔ جدید", newCategoryName),
    field("این دسته کجا دیده شود؟", scopeSelect),
    scopeHint);

  const unitSelect = element("select", "app-select");
  unitSelect.name = "sourceUnit";
  unitSelect.append(option("", "انتخاب کنید"));
  /* The registry the rest of the module uses. A free-text unit would be a spelling nobody
     can convert from, which is the state this project is already trying to get out of. */
  getUnitOptions().forEach((unit) => unitSelect.append(option(unit.value, unit.label)));

  const priceInput = element("input", "app-input");
  priceInput.type = "text";
  priceInput.name = "price";
  priceInput.inputMode = "decimal";
  priceInput.autocomplete = "off";

  const observedAt = createPersianDatePicker({
    id: "manual-market-observed-at", label: "تاریخ این قیمت", value: getTehranTodayIso() });

  const reason = element("textarea", "app-textarea");
  reason.name = "reason";
  reason.rows = 2;
  reason.maxLength = 500;
  reason.placeholder = "این قیمت از کجا آمده است؟ مثلاً استعلام تلفنی از تأمین‌کننده";

  /* What was typed, read back as money. The box takes «۵۰۰۰۰۰» and this says «۵۰۰٬۰۰۰
     تومان», so a zero too many is caught before it is a price in a report. */
  const echo = element("p", "manual-market-price-dialog__echo", "");
  function renderEcho() {
    const irr = tomanInputToIrr(priceInput.value);
    echo.textContent = /^\d+$/.test(String(irr ?? "")) && /[1-9]/.test(irr)
      ? formatTomanFromIrr(irr)
      : "";
  }

  const feedback = element("p", "form-feedback", "");
  const save = element("button", "button button--primary", "ثبت قیمت");
  save.type = "button";
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => { dialog.close(); onClose?.(); });
  const actions = element("div", "manual-market-price-dialog__actions");
  actions.append(save, cancel);

  categorySelect.addEventListener("change", () => {
    newCategoryBox.hidden = categorySelect.value !== NEW_CATEGORY;
    feedback.textContent = "";
    if (!newCategoryBox.hidden) newCategoryName.focus();
  });
  priceInput.addEventListener("input", renderEcho);

  const form = element("form", "manual-market-price-dialog__form");
  form.addEventListener("submit", (event) => event.preventDefault());
  form.append(
    field("نام محصول", productInput),
    field("دسته", categorySelect,
          "دسته تعیین می‌کند این قیمت زیر کدام چیپ دیده شود."),
    newCategoryBox,
    field("واحد قیمت", unitSelect),
    field(`قیمت به ${getDisplayCurrencyLabel()}`, priceInput),
    echo,
    observedAt.field,
    field("دلیل و مبنا", reason),
    actions,
    feedback);

  dialog.append(head, form);

  /* THE CHIPS ARE FETCHED HERE WHEN THE CALLER HAS NONE.
     The page loads them inside `loadMarketPrices`, which does not run until somebody
     presses «نمایش قیمت روز بازار» -- so a person who opens this dialog first was being
     shown an empty menu and the only way forward was to invent a category that already
     existed. Asking for them is one request and it is the request this dialog cannot do
     without. A failure is not fatal: «+ دستهٔ جدید» still works, and the feedback line
     says why the list is empty rather than leaving it looking like the project has no
     categories at all. */
  if (!categories.length && adapter?.listCategories) {
    adapter.listCategories()
      .then((list) => { if (list?.length) fillCategories(list); })
      .catch((error) => {
        feedback.textContent = error?.message ?? "فهرست دسته‌ها دریافت نشد.";
      });
  }


  save.addEventListener("click", async () => {
    feedback.textContent = "";
    const productName = productInput.value.trim();
    const priceIrr = tomanInputToIrr(priceInput.value);
    const chosenReason = reason.value.trim();

    if (productName.length < 2) { feedback.textContent = "نام محصول را وارد کنید."; return; }
    if (!categorySelect.value) { feedback.textContent = "دسته را انتخاب کنید."; return; }
    if (!unitSelect.value) { feedback.textContent = "واحد قیمت را انتخاب کنید."; return; }
    if (!/^\d+$/.test(priceIrr) || !/[1-9]/.test(priceIrr)) {
      feedback.textContent = `قیمت باید عددی مثبت و معتبر به ${getDisplayCurrencyLabel()} باشد.`; return;
    }
    if (!observedAt.getValue()) { feedback.textContent = "تاریخ این قیمت را انتخاب کنید."; return; }
    if (!chosenReason) { feedback.textContent = "دلیل و مبنای این قیمت الزامی است."; return; }

    const makingCategory = categorySelect.value === NEW_CATEGORY;
    const categoryName = makingCategory ? newCategoryName.value.trim() : categorySelect.value;
    if (makingCategory && categoryName.length < 2) {
      feedback.textContent = "نام دستهٔ جدید را وارد کنید."; return;
    }

    save.disabled = true;
    try {
      /* THE CHIP FIRST, AND ONLY ONCE.
         A price whose category does not exist yet is refused, so the chip has to be made
         before the price is sent. If the price then fails, the chip stays — which is the
         right way round: an empty category is a word somebody can use or ignore, while a
         price filed under a category nobody declared is a row that cannot be found. */
      if (makingCategory) {
        await adapter.createCategory({
          category: categoryName,
          label: categoryName,
          scopeLevel: scopeSelect.value,
        });
        /* Adopted into the select so a retry after any later failure does not try to make
           the same chip twice and get the service's duplicate refusal. */
        categorySelect.append(option(categoryName, categoryName));
        categorySelect.value = categoryName;
        newCategoryBox.hidden = true;
      }

      const saved = await adapter.createManualPrice({
        productName,
        category: categoryName,
        sourceUnit: unitSelect.value,
        priceIrr,
        observedAt: observedAt.getValue(),
        reason: chosenReason,
      });
      dialog.close();
      onSaved?.(saved);
    } catch (error) {
      /* The service's own sentence. It knows which of the two calls refused and why — a
         duplicate category, an unknown unit, a category this project cannot see — and this
         dialog would only be guessing. */
      feedback.textContent = error?.message ?? "ثبت قیمت انجام نشد.";
      save.disabled = false;
    }
  });

  return {
    element: dialog,
    open() {
      document.body.append(dialog);
      showAccessibleDialog(dialog, { initialFocus: productInput });
    },
  };
}
