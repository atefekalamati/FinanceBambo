import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";

/* The materials one schedule item consumes, and what they cost at today's prices.
 *
 * An activity is not a material. «کانال‌کنی» is 500 cubic metres of trenching; it consumes
 * rebar and pipe and brick, and the schedule names none of them because a schedule
 * describes work rather than a bill of materials. So this panel is a LIST: each entry
 * names a real listing, an official unit, and how much of it this activity uses, and the
 * row costs the sum of them.
 *
 * A side panel opened from the row, not a page: the decision is about ONE row of the
 * estimate and the person making it is reading that row. Sending them somewhere else and
 * back is how the item they were looking at gets lost.
 *
 * WHAT IT WILL NOT DO
 * It never picks for you. There is no "best match", no name similarity, and no cheapest
 * first -- the list is ordered by category and name, and the daily prices sit beside each
 * candidate so a person compares them deliberately. Choosing by resemblance is exactly how
 * an estimate ends up priced from the wrong steel, and the sheet lists 622 rebar products.
 *
 * And it never decides HOW MUCH. «۵۰۰» is either 500 per cubic metre or 500 altogether,
 * and on a 500 m³ trench those differ by a factor of 500. The mode is a question, asked
 * plainly, with no default.
 *
 * WHY EVERY FIGURE IS A SERVER CALL
 * The conversion is Decimal arithmetic against the live observation and the approved
 * factors, and both live on the server. Converting here would mean a second implementation
 * in floating point, which would disagree with the saved figure in the last digits. So the
 * panel asks, and shows exactly what will be stored -- including the refusals. */

const STATUS_CLASS = Object.freeze({
  ready: "price-status--ready",
  needs_components: "price-status--pending",
  needs_product: "price-status--pending",
  needs_product_type: "price-status--pending",
  needs_unit: "price-status--pending",
  needs_usage_quantity: "price-status--pending",
  needs_factor: "price-status--pending",
  /* Its own class: a partly-priced row is not the same thing as an unstarted one. The
     total it shows is real AND incomplete, and a reader has to be able to see that at a
     glance rather than by reading the counts. */
  partially_unresolved: "price-status--partial",
  unknown_source_unit: "price-status--blocked",
  incompatible: "price-status--blocked",
  no_price: "price-status--blocked",
});

export function statusChip(status, label) {
  const chip = element("span", `price-status ${STATUS_CLASS[status] ?? "price-status--pending"}`, label ?? "");
  chip.dataset.status = status ?? "";
  return chip;
}

function priceText(value) {
  /* null is "nobody knows" and prints as an em dash. Zero would be a claim. */
  return value === null || value === undefined ? "—" : formatTomanFromIrr(value, { withCurrency: false });
}

function quantityText(value) {
  return value === null || value === undefined ? "—" : formatDisplayNumber(value);
}

/* A placeholder choice. The empty value is load-bearing: an <option> without one uses
   its own text as the value, so "همه دسته‌ها" would travel to the API as a category. */
function blankOption(label) {
  const option = element("option", "", label);
  option.value = "";
  return option;
}

/* Refill a dropdown as the cascade narrows, keeping a choice only if it survived.
   Silently keeping a value the new list no longer offers is how a form ends up sending a
   provider who sells nothing in the chosen category. */
function fillOptions(select, placeholder, items) {
  const previous = select.value;
  select.replaceChildren(blankOption(placeholder));
  items.forEach(({ value, label }) => {
    const option = element("option", "", label);
    option.value = value;
    select.append(option);
  });
  select.value = items.some((item) => String(item.value) === previous) ? previous : "";
  return select.value;
}

function labelled(text, field) {
  const wrapper = element("label", "field");
  wrapper.append(element("span", "", text), field);
  return wrapper;
}

function specList(candidate) {
  /* The worksheet's own columns for this category, and only the ones it states. */
  const list = element("dl", "price-candidate__specs");
  (candidate.specColumns ?? []).forEach((column) => {
    const value = (candidate.specs ?? {})[column.key];
    if (value === null || value === undefined || value === "") return;
    list.append(element("dt", "", column.label), element("dd", "", String(value)));
  });
  return list;
}

export function createPriceMappingPanel({ line, resource, adapter, canEdit, onSaved, onClose }) {
  /* A real <dialog>, not a <section> with role="dialog". `showAccessibleDialog` requires
     one and throws otherwise -- which it did, on every open, so the panel appeared with no
     focus trap, no Escape and no backdrop while an uncaught TypeError went to the console.
     The element is what provides those; the role attribute only describes them. */
  const panel = element("dialog", "price-mapping-panel");
  panel.setAttribute("aria-label", "مصالح و قیمت روز این قلم");
  const lineId = line.lineId ?? line.estimateLineId ?? "";
  panel.dataset.estimateLineId = lineId;

  let usageModes = [];
  let header = null;
  /* The material being entered right now, and the stored one being corrected. Both reset
     after each save, so the next «افزودن مصالح» starts blank rather than inheriting the
     last answer -- an inherited usage quantity is a number nobody typed. */
  let chosen = null;
  let editing = null;

  // --------------------------------------------------------------------------- the head

  const head = element("header", "price-mapping-panel__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { panel.close(); onClose?.(); });
  /* What the SCHEDULE says, shown before anything is entered. A usage of «۸۰ کیلوگرم به
     ازای هر مترمکعب» means nothing until a reader can see that the activity is 500 cubic
     metres. */
  const scheduleFacts = element("dl", "price-mapping-panel__schedule");
  head.append(
    element("h2", "", "مصالح و قیمت روز این قلم"),
    element("p", "price-mapping-panel__subtitle",
      `${resource?.title ?? "قلم هزینه"} — فعالیت ${line.activityExternalId ?? "—"}`),
    scheduleFacts, close);

  function renderSchedule() {
    scheduleFacts.replaceChildren();
    if (!header) return;
    scheduleFacts.append(
      element("dt", "", "مقدار فعالیت"),
      element("dd", "numeric",
        `${quantityText(header.mspQuantity)} ${formatUnitLabel(header.mspUnit) ?? ""}`.trim()),
      element("dt", "", "هزینه MSP فعالیت"),
      element("dd", "numeric", priceText(header.mspCostIRR)));
  }

  // -------------------------------------------------------- the materials already there

  const componentsSection = element("section", "price-components");
  const totalBox = element("div", "price-components__total");
  const componentList = element("div", "price-components__list");
  const add = element("button", "button button--primary", "افزودن مصالح");
  add.type = "button";
  add.disabled = !canEdit;
  componentsSection.append(element("h3", "", "مصالح به‌کاررفته در این قلم"),
                           totalBox, componentList, add);

  function renderTotal(total) {
    totalBox.replaceChildren();
    if (!total) return;
    totalBox.append(statusChip(total.status, total.statusLabel));
    const figures = element("dl", "price-components__figures");
    figures.append(element("dt", "", "هزینه روز این قلم"),
                   element("dd", "numeric", priceText(total.dailyItemCostIRR)));
    totalBox.append(figures);
    if (total.componentCount) {
      /* The counts, always -- not only when something is missing. «۲ از ۳» beside a total
         is what stops a partial sum from being read as a finished one. */
      totalBox.append(element("p", "price-components__counts",
        `${formatDisplayNumber(total.readyComponentCount)} از ${formatDisplayNumber(total.componentCount)} قلم مصالح قیمت‌گذاری شده است`));
    }
    if (total.reason) totalBox.append(element("p", "price-components__reason", total.reason));
  }

  function usageText(component) {
    const mode = usageModes.find((entry) => entry.value === component.usageMode);
    const unit = formatUnitLabel(component.usageUnit ?? component.selectedUnit) ?? "";
    return `${quantityText(component.usageQuantity)} ${unit} ${mode?.label ? `(${mode.label})` : ""}`
      .replace(/\s+/g, " ").trim();
  }

  function renderComponents(components) {
    componentList.replaceChildren();
    if (!components.some((component) => component.active)) {
      componentList.append(element("p", "empty-state",
        "برای این قلم هنوز مصالحی ثبت نشده است. با «افزودن مصالح» شروع کنید."));
    }
    components.forEach((component) => {
      const card = element("article",
        `price-component${component.active ? "" : " price-component--retired"}`);
      card.dataset.componentId = component.componentId ?? "";
      card.dataset.status = component.status ?? "";
      card.append(
        element("h4", "", component.productName ?? "—"),
        element("p", "price-component__meta",
          [component.providerName, component.categoryLabel, component.productExternalId]
            .filter(Boolean).join(" · ")),
        statusChip(component.status, component.statusLabel));

      const figures = element("dl", "price-component__figures");
      figures.append(
        element("dt", "", "مصرف"),
        element("dd", "numeric", usageText(component)),
        element("dt", "", `قیمت روز در ${formatUnitLabel(component.selectedUnit) ?? "واحد انتخابی"}`),
        element("dd", "numeric", priceText(component.convertedDailyUnitPriceIRR)),
        element("dt", "", "مقدار مصالح این قلم"),
        element("dd", "numeric",
          `${quantityText(component.componentQuantity)} ${formatUnitLabel(component.selectedUnit) ?? ""}`.trim()),
        element("dt", "", "هزینه روز این مصالح"),
        element("dd", "numeric", priceText(component.componentDailyCostIRR)));
      card.append(figures);

      /* Why there is no number, and -- separately -- why this material is on the line at
         all. Two different sentences; showing only the first loses the author. */
      if (component.reason) card.append(element("p", "price-component__reason", component.reason));
      if (component.reasonText) card.append(element("p", "table-note", component.reasonText));

      if (component.active && canEdit) {
        const actions = element("div", "price-component__actions");
        const edit = element("button", "button button--ghost", "ویرایش");
        edit.type = "button";
        edit.dataset.action = "edit-component";
        edit.addEventListener("click", () => openForm(component));
        const retire = element("button", "button button--ghost", "حذف از این قلم");
        retire.type = "button";
        retire.dataset.action = "deactivate-component";
        retire.addEventListener("click", () => askToRetire(component, card));
        actions.append(edit, retire);
        card.append(actions);
      }
      if (!component.active) {
        card.append(element("p", "table-note", "این مصالح از قلم کنار گذاشته شده است"));
      }
      componentList.append(card);
    });
  }

  // ---------------------------------------------------------------- adding one material

  const form = element("form", "price-component-form");
  form.hidden = true;
  form.addEventListener("submit", (event) => event.preventDefault());
  const formHeading = element("h3", "", "افزودن مصالح");

  const categorySelect = element("select", "");
  categorySelect.name = "category";
  const providerSelect = element("select", "");
  providerSelect.name = "providerId";
  const typeSelect = element("select", "");
  typeSelect.name = "productType";
  const search = element("input", "");
  search.type = "search";
  search.name = "query";
  search.placeholder = "نام یا شناسه محصول";
  const apply = element("button", "button button--ghost", "جست‌وجو");
  apply.type = "button";

  const filters = element("div", "price-component-form__filters");
  filters.append(labelled("دسته", categorySelect), labelled("تأمین‌کننده", providerSelect),
                 labelled("نوع محصول", typeSelect), labelled("جست‌وجو", search), apply);

  const results = element("div", "price-component-form__results");

  const unitSelect = element("select", "");
  unitSelect.name = "selectedUnit";
  unitSelect.disabled = true;
  const modeSelect = element("select", "");
  modeSelect.name = "usageMode";
  modeSelect.disabled = true;
  const modeHint = element("p", "table-note", "");
  const usageInput = element("input", "");
  usageInput.type = "text";
  usageInput.name = "usageQuantity";
  usageInput.inputMode = "decimal";
  usageInput.disabled = true;

  const reason = element("textarea", "");
  reason.name = "reason";
  reason.rows = 2;
  reason.placeholder = "چرا این مصالح برای این قلم لازم است؟";

  const measures = element("div", "price-component-form__measures");
  measures.append(labelled("واحد رسمی محاسبه", unitSelect),
                  labelled("نحوهٔ مصرف مصالح", modeSelect),
                  labelled("مقدار مصرف", usageInput));

  const preview = element("div", "price-component-form__preview");
  const save = element("button", "button button--primary", "ثبت مصالح");
  save.type = "button";
  save.disabled = true;
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  const feedback = element("p", "form-feedback", "");

  form.append(formHeading, filters, results, measures, modeHint,
              labelled("دلیل", reason), preview, save, cancel, feedback);

  function draft() {
    const usage = usageInput.value.trim();
    return {
      providerItemId: chosen?.providerItemId,
      selectedUnit: unitSelect.value || undefined,
      usageMode: modeSelect.value || undefined,
      usageQuantity: usage === "" ? undefined : usage,
    };
  }

  function renderPreview(component, total) {
    preview.replaceChildren();
    if (!component) return;
    preview.append(statusChip(component.status, component.statusLabel));
    if (component.reason) {
      preview.append(element("p", "price-component-form__reason", component.reason));
    }
    const figures = element("dl", "price-component-form__figures");
    figures.append(
      /* The listing's own price in its own unit. NOT defaulted to the converted figure:
         two rows showing one number under two labels is how a reader concludes that no
         conversion took place. Unknown stays an em dash. */
      element("dt", "", `قیمت روز محصول${component.sourceUnit ? ` (به ازای ${formatUnitLabel(component.sourceUnit)})` : ""}`),
      element("dd", "numeric", priceText(component.sourcePriceIRR)),
      element("dt", "", "قیمت تبدیل‌شده در واحد انتخابی"),
      element("dd", "numeric", priceText(component.convertedDailyUnitPriceIRR)),
      element("dt", "", "مقدار مصالح این قلم"),
      element("dd", "numeric", quantityText(component.componentQuantity)),
      element("dt", "", "هزینه روز این مصالح"),
      element("dd", "numeric", priceText(component.componentDailyCostIRR)));
    if (total) {
      /* What the ROW will come to once this is saved. The row total is the figure a reader
         acts on, and seeing it move is the difference between choosing deliberately and
         choosing then checking. */
      figures.append(element("dt", "", "هزینه روز این قلم پس از ثبت"),
                     element("dd", "numeric", priceText(total.dailyItemCostIRR)));
    }
    preview.append(figures);
  }

  async function refreshPreview() {
    const body = draft();
    if (!body.providerItemId || !body.selectedUnit || !body.usageMode
        || body.usageQuantity === undefined) {
      renderPreview(null);
      save.disabled = true;
      return;
    }
    try {
      const [component, total] = await Promise.all([
        adapter.previewComponent(lineId, body),
        adapter.previewTotal(lineId, body),
      ]);
      renderPreview(component, total);
      /* Saving stays possible when the conversion is unresolved: which material this is
         and whether somebody has measured the crossing are different facts, and recording
         the first is progress. The component then shows «نیازمند ضریب تبدیل» until the
         second exists. */
      save.disabled = !canEdit;
    } catch (error) {
      feedback.textContent = error?.message ?? "محاسبهٔ قیمت این مصالح انجام نشد.";
    }
  }

  function clearChoice() {
    chosen = null;
    unitSelect.value = "";
    unitSelect.disabled = true;
    modeSelect.disabled = true;
    usageInput.disabled = true;
    renderPreview(null);
    save.disabled = true;
  }

  function choose(candidate, card) {
    chosen = candidate;
    results.querySelectorAll(".price-candidate").forEach((node) =>
      node.classList.toggle("price-candidate--chosen", node === card));
    unitSelect.disabled = !canEdit;
    modeSelect.disabled = !canEdit;
    usageInput.disabled = !canEdit;
    /* Default to the unit the sheet states this price in, when it is one the registry
       knows. It is a starting point a person can change -- never a decision made for
       them, which is why it is only a preselection and the control stays open. */
    if (!unitSelect.value && candidate.sourceUnitCode) unitSelect.value = candidate.sourceUnitCode;
    refreshPreview();
  }

  function renderCandidates(items) {
    results.replaceChildren();
    if (!items.length) {
      results.append(element("p", "empty-state", "محصولی با این فیلترها پیدا نشد."));
      return;
    }
    items.forEach((candidate) => {
      const card = element("article", "price-candidate");
      card.dataset.providerItemId = candidate.providerItemId;
      const pick = element("button", "button button--ghost", "انتخاب");
      pick.type = "button";
      pick.disabled = !canEdit;
      pick.addEventListener("click", () => choose(candidate, card));
      card.append(
        element("h4", "", candidate.displayName || candidate.name || "—"),
        element("p", "price-candidate__meta",
          [candidate.providerName, candidate.categoryLabel, candidate.externalId]
            .filter(Boolean).join(" · ")),
        element("p", "price-candidate__price",
          candidate.currentPriceIRR === null
            ? "بدون قیمت روز"
            : `${priceText(candidate.currentPriceIRR)} به ازای ${formatUnitLabel(candidate.sourceUnitCode)}`),
        specList(candidate), pick);
      if (!candidate.active) {
        card.append(element("p", "table-note", candidate.inactiveReason ?? "این قلم فعال نیست"));
      }
      results.append(card);
    });
  }

  async function loadCandidates() {
    results.replaceChildren(element("p", "empty-state", "در حال بارگذاری…"));
    try {
      const body = await adapter.candidates({
        category: categorySelect.value || undefined,
        providerId: providerSelect.value || undefined,
        productType: typeSelect.value || undefined,
        query: search.value.trim() || undefined,
        pageSize: 25,
      });
      renderCandidates(body.items);
    } catch (error) {
      results.replaceChildren(
        element("p", "form-feedback", error?.message ?? "فهرست محصولات خوانده نشد."));
    }
  }

  /* The cascade. Each step narrows the next and CLEARS what it invalidates -- a provider
     chosen under «میلگرد» must not survive a switch to «آجر», and a product chosen under
     that provider must not survive either. Keeping a stale choice is how a form submits a
     combination the person never saw. */
  async function reloadFilters() {
    try {
      const body = await adapter.filters({
        category: categorySelect.value || undefined,
        providerId: providerSelect.value || undefined,
      });
      fillOptions(providerSelect, "همه تأمین‌کننده‌ها",
        (body.providers ?? []).map((provider) => ({ value: provider.id, label: provider.name })));
      fillOptions(typeSelect, "همه انواع",
        (body.productTypes ?? []).map((type) => ({ value: type, label: type })));
    } catch (error) {
      feedback.textContent = error?.message ?? "فهرست فیلترها خوانده نشد.";
    }
  }

  categorySelect.addEventListener("change", async () => {
    providerSelect.value = "";
    typeSelect.value = "";
    clearChoice();
    await reloadFilters();
    await loadCandidates();
  });
  providerSelect.addEventListener("change", async () => {
    typeSelect.value = "";
    clearChoice();
    await reloadFilters();
    await loadCandidates();
  });
  typeSelect.addEventListener("change", async () => { clearChoice(); await loadCandidates(); });
  apply.addEventListener("click", loadCandidates);
  unitSelect.addEventListener("change", refreshPreview);
  modeSelect.addEventListener("change", () => {
    /* The hint is the whole difference between the two modes, and it is the sentence that
       stops «۵۰۰» from being entered as a total when it was meant per cubic metre. */
    modeHint.textContent = usageModes.find((entry) => entry.value === modeSelect.value)?.hint ?? "";
    refreshPreview();
  });
  usageInput.addEventListener("input", refreshPreview);
  usageInput.addEventListener("change", refreshPreview);

  function openForm(component = null) {
    editing = component;
    formHeading.textContent = component ? "ویرایش مصالح" : "افزودن مصالح";
    save.textContent = component ? "ثبت ویرایش" : "ثبت مصالح";
    form.hidden = false;
    add.hidden = true;
    feedback.textContent = "";
    if (component) {
      /* Editing starts from what was stored, so somebody changing only the usage does not
         have to find the product again. */
      chosen = { providerItemId: component.providerItemId,
                 sourceUnitCode: component.sourceUnit };
      unitSelect.value = component.selectedUnit ?? "";
      modeSelect.value = component.usageMode ?? "";
      usageInput.value = component.usageQuantity ?? "";
      reason.value = component.reasonText ?? "";
      [unitSelect, modeSelect, usageInput].forEach((node) => { node.disabled = !canEdit; });
      refreshPreview();
    } else {
      [categorySelect, providerSelect, typeSelect, search, modeSelect, usageInput, reason]
        .forEach((node) => { node.value = ""; });
      modeHint.textContent = "";
      clearChoice();
    }
    loadCandidates();
  }

  function closeForm() {
    editing = null;
    form.hidden = true;
    add.hidden = !canEdit;
    clearChoice();
  }

  add.addEventListener("click", () => openForm(null));
  cancel.addEventListener("click", closeForm);

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    const body = draft();
    if (!body.providerItemId || !body.selectedUnit) {
      feedback.textContent = "محصول و واحد رسمی را انتخاب کنید."; return;
    }
    if (!body.usageMode) { feedback.textContent = "نحوهٔ مصرف مصالح را انتخاب کنید."; return; }
    if (body.usageQuantity === undefined) {
      feedback.textContent = "مقدار مصرف مصالح الزامی است."; return;
    }
    if (!reason.value.trim()) { feedback.textContent = "دلیل ثبت این مصالح الزامی است."; return; }
    save.disabled = true;
    const payload = {
      providerItemId: body.providerItemId,
      selectedUnit: body.selectedUnit,
      usageMode: body.usageMode,
      usageQuantity: body.usageQuantity,
      reason: reason.value.trim(),
    };
    try {
      if (editing) await adapter.updateComponent(lineId, editing.componentId, payload);
      else await adapter.addComponent(lineId, payload);
      closeForm();
      await loadComponents();
      onSaved?.();
    } catch (error) {
      feedback.textContent = error?.message ?? "ثبت این مصالح انجام نشد.";
      save.disabled = false;
    }
  });

  /* Retiring asks for a reason in place, on the card. It is not a confirm dialog: the
     reason IS the record of why a material left the line, and a dialog that only asks
     "are you sure" collects nothing. */
  function askToRetire(component, card) {
    if (card.querySelector(".price-component__retire")) return;
    const why = element("div", "price-component__retire");
    const text = element("input", "");
    text.type = "text";
    text.name = "deactivateReason";
    text.placeholder = "دلیل حذف این مصالح";
    const confirm = element("button", "button button--ghost", "تأیید حذف");
    confirm.type = "button";
    confirm.dataset.action = "confirm-deactivate";
    confirm.addEventListener("click", async () => {
      if (!text.value.trim()) { feedback.textContent = "دلیل حذف این مصالح الزامی است."; return; }
      try {
        await adapter.deactivateComponent(lineId, component.componentId, text.value.trim());
        await loadComponents();
        onSaved?.();
      } catch (error) {
        feedback.textContent = error?.message ?? "حذف این مصالح انجام نشد.";
      }
    });
    why.append(text, confirm);
    card.append(why);
  }

  // ---------------------------------------------------------------------------- loading

  async function loadComponents() {
    try {
      const body = await adapter.componentsFor(lineId);
      header = body.line;
      renderSchedule();
      renderComponents(body.components);
      renderTotal(body.total);
    } catch (error) {
      componentList.replaceChildren(
        element("p", "form-feedback", error?.message ?? "فهرست مصالح این قلم خوانده نشد."));
    }
  }

  (async () => {
    try {
      const body = await adapter.filters();
      usageModes = body.usageModes ?? [];
      fillOptions(categorySelect, "همه دسته‌ها",
        (body.categories ?? []).map((category) => ({
          value: category.category, label: `${category.label} (${category.itemCount})` })));
      fillOptions(providerSelect, "همه تأمین‌کننده‌ها",
        (body.providers ?? []).map((provider) => ({ value: provider.id, label: provider.name })));
      fillOptions(typeSelect, "همه انواع",
        (body.productTypes ?? []).map((type) => ({ value: type, label: type })));
      fillOptions(unitSelect, "انتخاب واحد",
        (body.units ?? []).map((unit) => ({
          value: unit.code, label: `${unit.label} (${unit.dimensionLabel})` })));
      /* No default mode. «۵۰۰ به ازای هر مترمکعب» and «۵۰۰ در کل» differ by a factor of
         the activity quantity, and picking one for the person is picking their answer. */
      fillOptions(modeSelect, "انتخاب کنید",
        usageModes.map((mode) => ({ value: mode.value, label: mode.label })));
    } catch (error) {
      feedback.textContent = error?.message ?? "فهرست فیلترها خوانده نشد.";
    }
    await loadComponents();
  })();

  if (!canEdit) {
    /* A viewer sees everything and changes nothing. The controls are disabled rather than
       hidden so it is clear the workflow exists and who may use it. */
    [search, apply, unitSelect, modeSelect, usageInput, reason, save, add]
      .forEach((node) => { node.disabled = true; });
    componentsSection.append(
      element("p", "table-note", "برای ویرایش مصالح این قلم، دسترسی finance.edit لازم است."));
  }

  panel.append(head, componentsSection, form);
  return panel;
}
