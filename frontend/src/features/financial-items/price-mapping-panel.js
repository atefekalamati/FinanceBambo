import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";
import { createConversionRuleDialog } from "./conversion-rule-dialog.js";
import { createSourceUnitDialog } from "./source-unit-dialog.js";

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

/* `form-field` stacks the label over its control and `form-label` gives the label the
   module's own type. `.field` is defined in no stylesheet here, so the two sat on one line
   and ran into each other. */
function labelled(text, field) {
  const wrapper = element("label", "form-field");
  wrapper.append(element("span", "form-label", text), field);
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

export function createPriceMappingPanel({ line, resource, adapter, materialPricesAdapter = null, canEdit, canManageSettings = true, onSaved, onClose }) {
  /* A real <dialog>, not a <section> with role="dialog". `showAccessibleDialog` requires
     one and throws otherwise -- which it did, on every open, so the panel appeared with no
     focus trap, no Escape and no backdrop while an uncaught TypeError went to the console.
     The element is what provides those; the role attribute only describes them. */
  const panel = element("dialog", "price-mapping-panel");
  panel.setAttribute("aria-label", "مصالح و قیمت روز این قلم");
  const lineId = line.lineId ?? line.estimateLineId ?? "";
  panel.dataset.estimateLineId = lineId;

  let header = null;
  /* The listing being chosen right now, and the stored link being corrected. Both reset
     after each save, so reopening the form starts from what is stored rather than from
     the last answer somebody abandoned. */
  let chosen = null;
  let editing = null;
  /* The last answer the server gave about the chosen listing. Kept because the conversion
     dialog is built from it: the two units it must reconcile are the ones the server just
     said do not meet. */
  let lastPreview = null;

  // --------------------------------------------------------------------------- the head

  /* WHICH ROW, before anything else.
     Choosing between 311 rebar listings is meaningless until a person can see that the
     row in front of them is «آرماتور، ۴۰٬۰۰۰ کیلوگرم، در کانال‌کنی». This used to sit
     under a heading about materials, in a definition list beside the activity's own MSP
     cost -- two figures that are not the decision, above the one thing that identifies
     it. The identity is the heading now. */
  const head = element("header", "price-mapping-panel__head");
  /* Small and out of the way. A full-width «بستن» directly under the item's name read as
     the panel's main action, which is the opposite of what it is. */
  const close = element("button", "button button--ghost price-mapping-panel__close", "بستن");
  close.type = "button";
  close.addEventListener("click", () => { panel.close(); onClose?.(); });

  const identity = element("div", "price-mapping-panel__identity");
  const quantityLine = element("p", "price-mapping-panel__quantity", "");
  identity.append(
    element("h2", "", resource?.title ?? "قلم هزینه"),
    element("p", "price-mapping-panel__subtitle",
      [resource?.activityTitle ?? line.activityTitle, line.activityExternalId]
        .filter(Boolean).join(" · ") || "—"),
    quantityLine);
  head.append(identity, close);

  function renderSchedule() {
    /* The quantity this row IS. Shown as a sentence rather than a labelled row: it is the
       subject of the whole panel, not one fact among several. */
    quantityLine.textContent = header
      ? `${quantityText(header.mspQuantity)} ${formatUnitLabel(header.mspUnit) ?? ""}`.trim()
      : "";
  }

  /* ------------------------------------------------- what this line is priced from
     One line, one listing. An estimate line here is already a single resource on a
     single activity -- it arrives that way from the MPP assignment rows, naming its own
     material and its own quantity. Materials entered underneath it would be a level this
     data does not have, so there is no list and nothing to add to. */

  const componentsSection = element("section", "price-components");
  const totalBox = element("div", "price-components__total");
  const componentList = element("div", "price-components__list");
  const add = element("button", "button button--primary", "اتصال به قیمت روز");
  add.type = "button";
  add.disabled = !canEdit;
  componentsSection.append(element("h3", "", "قیمت روز این قلم"),
                           totalBox, componentList, add);

  /* The server's own labels still say «مصالح», from the days when a line held several.
     Translated here rather than shown as they arrive: a panel whose heading says «اتصال»
     and whose status chip says «افزودن مصالح» is describing two different features. Only
     the statuses this page can produce are listed; anything else is passed through, so a
     new server status appears verbatim instead of disappearing. */
  const STATUS_WORDING = Object.freeze({
    needs_components: "هنوز به قیمت روز وصل نشده",
    partially_unresolved: "قیمت روز این قلم کامل نیست",
  });

  function renderTotal(total) {
    totalBox.replaceChildren();
    if (!total) return;
    totalBox.append(statusChip(total.status,
      STATUS_WORDING[total.status] ?? total.statusLabel));
    const figures = element("dl", "price-components__figures");
    figures.append(element("dt", "", "هزینه روز این قلم"),
                   element("dd", "numeric", priceText(total.dailyItemCostIRR)));
    totalBox.append(figures);
    if (total.reason) totalBox.append(element("p", "price-components__reason", total.reason));
  }

  function renderConnection(components) {
    componentList.replaceChildren();
    if (!components.some((component) => component.active)) {
      componentList.append(element("p", "empty-state",
        "این قلم هنوز به قیمت روز وصل نشده است. با «اتصال به قیمت روز» محصول بازار آن را انتخاب کنید."));
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
        element("dt", "", `قیمت روز در ${formatUnitLabel(component.selectedUnit) ?? "واحد انتخابی"}`),
        element("dd", "numeric", priceText(component.convertedDailyUnitPriceIRR)),
        /* The line's own quantity, restated here rather than asked for. It is what the
           schedule says this item is, and the cost below is that quantity at today's
           price -- showing one without the other invites the reader to multiply. */
        element("dt", "", "مقدار این قلم"),
        element("dd", "numeric",
          `${quantityText(component.componentQuantity)} ${formatUnitLabel(component.selectedUnit) ?? ""}`.trim()),
        element("dt", "", "هزینه روز این قلم"),
        element("dd", "numeric", priceText(component.componentDailyCostIRR)));
      card.append(figures);

      /* Why there is no number, and -- separately -- why this material is on the line at
         all. Two different sentences; showing only the first loses the author. */
      if (component.reason) card.append(element("p", "price-component__reason", component.reason));
      if (component.reasonText) card.append(element("p", "table-note", component.reasonText));

      if (component.active && canEdit) {
        const actions = element("div", "price-component__actions");
        const edit = element("button", "button button--ghost", "تغییر محصول");
        edit.type = "button";
        edit.dataset.action = "edit-component";
        edit.addEventListener("click", () => openForm(component));
        const retire = element("button", "button button--ghost", "برداشتن اتصال");
        retire.type = "button";
        retire.dataset.action = "deactivate-component";
        retire.addEventListener("click", () => askToRetire(component, card));
        actions.append(edit, retire);
        /* THE WAY OUT SITS ON THE SAVED CARD, not only on a draft being edited.
           These prompts used to render from `refreshPreview` alone -- so a line that was
           already linked and stuck showed its problem and no way to answer it, and the
           person had to press «تغییر محصول» and re-enter a form they were not changing to
           reach the button. The row being blocked is the state they came here about. */
        const way = unitPromptFor(component);
        if (way) actions.append(way);
        card.append(actions);
      }
      if (!component.active) {
        card.append(element("p", "table-note", "این اتصال برداشته شده است"));
      }
      componentList.append(card);
    });
  }

  // ------------------------------------------------------------- choosing the listing

  const form = element("form", "price-component-form");
  form.hidden = true;
  form.addEventListener("submit", (event) => event.preventDefault());
  const formHeading = element("h3", "", "انتخاب محصول قیمت روز");

  const categorySelect = element("select", "app-select");
  categorySelect.name = "category";
  const providerSelect = element("select", "app-select");
  providerSelect.name = "providerId";
  const typeSelect = element("select", "app-select");
  typeSelect.name = "productType";
  const search = element("input", "app-input");
  search.type = "search";
  search.name = "query";
  search.placeholder = "نام یا شناسه محصول";
  const apply = element("button", "button button--ghost", "جست‌وجو");
  apply.type = "button";

  const filters = element("div", "price-component-form__filters");
  filters.append(labelled("دسته", categorySelect), labelled("تأمین‌کننده", providerSelect),
                 labelled("نوع محصول", typeSelect), labelled("جست‌وجو", search), apply);

  /* Numbered, because the two questions are answered in order and the second is
     meaningless before the first: a unit is chosen for a product. */
  function step(number, title) {
    const heading = element("h4", "price-component-form__step");
    heading.append(element("span", "price-component-form__step-number", number),
                   element("span", "", title));
    return heading;
  }

  const results = element("div", "price-component-form__results");

  const unitSelect = element("select", "app-select");
  unitSelect.name = "selectedUnit";
  unitSelect.disabled = true;
  const reason = element("textarea", "app-textarea");
  reason.name = "reason";
  reason.rows = 2;
  reason.placeholder = "چرا این محصول قیمت این قلم را می‌دهد؟";

  const measures = element("div", "price-component-form__measures");
  measures.append(labelled("", unitSelect));

  const preview = element("div", "price-component-form__preview");
  /* Where «نیازمند ضریب تبدیل» stops being a dead end. Empty for every other status. */
  const conversionPrompt = element("div", "price-component-form__conversion");

  /* TWO WALLS, TWO DOORS, AND THEY ARE NOT THE SAME DOOR.
   *
   * `needs_factor` means both units are known and do not meet: «۱ کیسه چند کیلوگرم است»,
   * which a conversion rule answers and which may be stated for this project, the whole
   * organization, or all of BAMBO.
   *
   * `unknown_source_unit` means the SHEET never said what its price is a price of. There
   * is nothing to convert from, and a conversion dialog opened there asks somebody to
   * bridge a gap whose near side is missing. Measured on this project that is where the
   * linked rows actually stop: five read «واحد قیمت مبدأ مشخص نیست» and none reads
   * «نیازمند ضریب تبدیل» -- and this panel used to answer that by opening and offering
   * nothing at all.
   *
   * Any other status -- no price today, no unit chosen -- is a third thing again, and
   * neither door helps, so neither is shown. */
  /* The way out of «واحد قیمت مبدأ مشخص نیست».
   *
   * Offered only when this host wired the material-prices module, because that is whose
   * endpoint writes the label. A host without it has no way to record the answer, and a
   * button that cannot save is worse than the plain statement of the problem. */
  function sourceUnitButton(component) {
    const providerItemId = component.providerItemId ?? chosen?.providerItemId ?? null;
    if (!materialPricesAdapter?.saveLabel || !providerItemId) return null;
    const open = element("button", "button button--ghost", "مشخص‌کردن واحد قیمت");
    open.type = "button";
    open.dataset.action = "define-source-unit";
    open.addEventListener("click", () => {
      const dialog = createSourceUnitDialog({
        adapter: materialPricesAdapter,
        context: {
          providerItemId,
          productName: component.productName ?? chosen?.name ?? null,
          providerName: component.providerName ?? chosen?.providerName ?? null,
          rawPrice: chosen?.rawPrice ?? null,
          selectedUnit: component.selectedUnit ?? null,
        },
        /* The same two refreshes the conversion dialog does, for the same reason: the
           preview so this row answers, and the page's own reload because a listing's unit
           can unblock every other line pointing at the same product. */
        onSaved: () => { refreshPreview(); onSaved?.(); },
        onClose: () => dialog.element.remove(),
      });
      dialog.open();
    });
    return open;
  }

  function renderConversionPrompt(component) {
    conversionPrompt.replaceChildren();
    const way = unitPromptFor(component);
    if (way) conversionPrompt.append(way);
  }

  /** The one button that answers whatever this component is stuck on, or null. */
  function unitPromptFor(component) {
    if (!canEdit) return null;
    if (component?.status === "unknown_source_unit") return sourceUnitButton(component);
    if (component?.status !== "needs_factor") return null;
    const open = element("button", "button button--ghost", "تعریف قانون تبدیل واحد");
    open.type = "button";
    open.dataset.action = "define-conversion-rule";
    open.addEventListener("click", () => {
      const dialog = createConversionRuleDialog({
        adapter,
        /* Passed through rather than read here: a feature may not name a permission code,
           and the page above already asked the one place that translates them. */
        canManageSettings,
        context: {
          fromUnit: component.sourceUnit,
          toUnit: component.selectedUnit,
          providerItemId: component.providerItemId ?? chosen?.providerItemId ?? null,
          providerId: chosen?.providerId ?? null,
          category: component.category ?? chosen?.category ?? null,
          productName: component.productName ?? chosen?.name ?? null,
          providerName: component.providerName ?? chosen?.providerName ?? null,
          categoryLabel: component.categoryLabel ?? chosen?.categoryLabel ?? null,
        },
        /* Recalculated rather than assumed: whether the new rule actually resolves THIS
           crossing is the server's answer, and asking again is how the person sees it.

           AND THE TABLE BEHIND THIS PANEL, which is the point of writing a rule at all. A
           rule is not about one row: a `category` or `project` rule can unblock a dozen
           lines at once, and refreshing only the preview would leave every one of them
           still reading «نیازمند ضریب تبدیل» behind an open panel that says it is solved.
           `onSaved` is the page's own reload of the row statuses -- it does not close this
           panel, so the person keeps the row they were working on. */
        onSaved: () => { refreshPreview(); onSaved?.(); },
      });
      dialog.open();
    });
    return open;
  }
  const save = element("button", "button button--primary", "ثبت اتصال");
  save.type = "button";
  save.disabled = true;
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  const feedback = element("p", "form-feedback", "");

  const actions = element("div", "price-component-form__actions");
  actions.append(save, cancel);

  form.append(formHeading,
              step("۱", "محصول قیمت روز را انتخاب کنید"), filters, results,
              step("۲", "واحد رسمی محاسبه"), measures,
              preview, conversionPrompt,
              labelled("دلیل", reason), actions, feedback);

  /* Two answers, not four. How much of this material the line uses is not asked, because
     the line already states it: the item IS «۱۲۰۰ کیلوگرم آرماتور», and asking again
     would invite a second, different number for the same fact. */
  function draft() {
    return {
      providerItemId: chosen?.providerItemId,
      selectedUnit: unitSelect.value || undefined,
    };
  }

  /* «۴۰٬۰۰۰ کیلوگرم × ۱۰۱٬۴۶۰ تومان = ۴٬۰۵۸ میلیون تومان», written out.
     The same three numbers were already in the table below, one per row, and a reader had
     to assemble the multiplication themselves. This is the answer the panel exists to
     produce, so it is a sentence and it comes first. Absent entirely when any part of it
     is unknown -- a half-written equation reads as a figure. */
  function renderOutcome(component) {
    if (!component || component.convertedDailyUnitPriceIRR === null
        || component.componentQuantity === null
        || component.componentDailyCostIRR === null) return null;
    const outcome = element("p", "price-component-form__outcome");
    const unit = formatUnitLabel(component.selectedUnit) ?? "";
    outcome.append(
      element("span", "", `${quantityText(component.componentQuantity)} ${unit}`.trim()),
      element("span", "price-component-form__times", "×"),
      element("span", "", priceText(component.convertedDailyUnitPriceIRR)),
      element("span", "price-component-form__equals", "="),
      element("strong", "", priceText(component.componentDailyCostIRR)));
    return outcome;
  }

  function renderPreview(component) {
    preview.replaceChildren();
    if (!component) return;
    preview.append(statusChip(component.status, component.statusLabel));
    const outcome = renderOutcome(component);
    if (outcome) preview.append(outcome);
    if (component.reason) {
      preview.append(element("p", "price-component-form__reason", component.reason));
    }
    const figures = element("dl", "price-component-form__figures");
    /* Only what the sentence above does NOT say. It already carries the quantity, the
       price per chosen unit and the product. What it cannot carry is the listing's own
       price in the listing's own unit, which is the number a person recognises from the
       sheet -- and the only way to see that a conversion happened at all. */
    figures.append(
      element("dt", "", `قیمت روز محصول${component.sourceUnit ? ` (به ازای ${formatUnitLabel(component.sourceUnit)})` : ""}`),
      element("dd", "numeric", priceText(component.sourcePriceIRR)),
      element("dt", "", "تاریخ قیمت"),
      element("dd", "", component.workflowDateJalali ?? "—"));
    preview.append(figures);
  }

  async function refreshPreview() {
    const body = draft();
    if (!body.providerItemId || !body.selectedUnit) {
      renderPreview(null);
      save.disabled = true;
      return;
    }
    try {
      const component = await adapter.preview(lineId, body);
      renderPreview(component);
      lastPreview = component;
      /* Saving stays possible when the conversion is unresolved: which listing prices
         this line and whether somebody has measured the crossing between its unit and
         this line's are different facts, and recording the first is progress. The link
         then shows «نیازمند ضریب تبدیل» until the second exists -- and the button beside
         that message is how it gets answered. */
      save.disabled = !canEdit;
      renderConversionPrompt(component);
    } catch (error) {
      feedback.textContent = error?.message ?? "محاسبهٔ قیمت روز این قلم انجام نشد.";
    }
  }

  function clearChoice() {
    chosen = null;
    lastPreview = null;
    unitSelect.value = "";
    unitSelect.disabled = true;
    renderPreview(null);
    renderConversionPrompt(null);
    save.disabled = true;
  }

  function choose(candidate, card) {
    chosen = candidate;
    results.querySelectorAll(".price-candidate").forEach((node) =>
      node.classList.toggle("price-candidate--chosen", node === card));
    unitSelect.disabled = !canEdit;
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

  function openForm(component = null) {
    editing = component;
    formHeading.textContent = component ? "تغییر محصول قیمت روز" : "انتخاب محصول قیمت روز";
    save.textContent = component ? "ثبت تغییر" : "ثبت اتصال";
    form.hidden = false;
    add.hidden = true;
    feedback.textContent = "";
    if (component) {
      /* Changing starts from what was stored, so somebody correcting only the unit does
         not have to find the product again. */
      chosen = { providerItemId: component.providerItemId,
                 sourceUnitCode: component.sourceUnit };
      unitSelect.value = component.selectedUnit ?? "";
      reason.value = component.reasonText ?? "";
      unitSelect.disabled = !canEdit;
      refreshPreview();
    } else {
      [categorySelect, providerSelect, typeSelect, search, reason]
        .forEach((node) => { node.value = ""; });
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
    if (!reason.value.trim()) { feedback.textContent = "دلیل ثبت این اتصال الزامی است."; return; }
    save.disabled = true;
    const payload = {
      providerItemId: body.providerItemId,
      selectedUnit: body.selectedUnit,
      reason: reason.value.trim(),
    };
    try {
      if (editing) await adapter.reconnect(lineId, editing.componentId, payload);
      else await adapter.connect(lineId, payload);
      closeForm();
      await loadConnection();
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
    const text = element("input", "app-input");
    text.type = "text";
    text.name = "deactivateReason";
    text.placeholder = "دلیل حذف این مصالح";
    const confirm = element("button", "button button--ghost", "تأیید حذف");
    confirm.type = "button";
    confirm.dataset.action = "confirm-deactivate";
    confirm.addEventListener("click", async () => {
      if (!text.value.trim()) { feedback.textContent = "دلیل حذف این مصالح الزامی است."; return; }
      try {
        await adapter.disconnect(lineId, component.componentId, text.value.trim());
        await loadConnection();
        onSaved?.();
      } catch (error) {
        feedback.textContent = error?.message ?? "حذف این مصالح انجام نشد.";
      }
    });
    why.append(text, confirm);
    card.append(why);
  }

  // ---------------------------------------------------------------------------- loading

  async function loadConnection() {
    try {
      const body = await adapter.connectionFor(lineId);
      header = body.line;
      renderSchedule();
      renderConnection(body.connection ? [body.connection] : []);
      renderTotal(body.total);
      /* Hidden once the line is linked: there is one listing per line, and a second
         «اتصال» button would offer a state this page cannot produce. Changing the product
         is on the card, where the current one is. */
      add.hidden = Boolean(body.connection) || !canEdit;
    } catch (error) {
      componentList.replaceChildren(
        element("p", "form-feedback", error?.message ?? "اتصال قیمت روز این قلم خوانده نشد."));
    }
  }

  (async () => {
    try {
      const body = await adapter.filters();
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
    } catch (error) {
      feedback.textContent = error?.message ?? "فهرست فیلترها خوانده نشد.";
    }
    await loadConnection();
  })();

  if (!canEdit) {
    /* A viewer sees everything and changes nothing. The controls are disabled rather than
       hidden so it is clear the workflow exists and who may use it. */
    [search, apply, unitSelect, reason, save, add]
      .forEach((node) => { node.disabled = true; });
    componentsSection.append(
      element("p", "table-note", "برای تغییر اتصال قیمت روز این قلم، دسترسی finance.edit لازم است."));
  }

  panel.append(head, componentsSection, form);
  return panel;
}
