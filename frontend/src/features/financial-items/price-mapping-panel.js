import { element } from "../../shared/dom/elements.js";
import { formatDisplayNumber, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr } from "../../shared/formatters/money.js";

/* Choosing which market listing prices one schedule item.
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
 * WHY THE PREVIEW IS A SERVER CALL
 * The conversion is Decimal arithmetic against the live observation and the approved
 * factors, and both live on the server. Converting here would mean a second implementation
 * in floating point, which would disagree with the saved figure in the last digits. So the
 * panel asks, and shows exactly what will be stored -- including the refusals. */

const STATUS_CLASS = Object.freeze({
  ready: "price-status--ready",
  needs_product: "price-status--pending",
  needs_unit: "price-status--pending",
  needs_factor: "price-status--pending",
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

/* A placeholder choice. The empty value is load-bearing: an <option> without one uses
   its own text as the value, so "همه دسته‌ها" would travel to the API as a category. */
function blankOption(label) {
  const option = element("option", "", label);
  option.value = "";
  return option;
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
  const panel = element("section", "price-mapping-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "اتصال قیمت روز به قلم هزینه");
  panel.dataset.estimateLineId = line.lineId ?? line.estimateLineId ?? "";

  let chosen = null;
  let selectedUnit = "";
  let units = [];
  let lastPreview = null;

  const head = element("header", "price-mapping-panel__head");
  const close = element("button", "button button--ghost", "بستن");
  close.type = "button";
  close.addEventListener("click", () => onClose?.());
  head.append(
    element("h2", "", "اتصال قیمت روز"),
    element("p", "", `${resource?.title ?? "قلم هزینه"} — فعالیت ${line.activityExternalId ?? "—"}`),
    close);

  const filters = element("form", "price-mapping-panel__filters");
  filters.addEventListener("submit", (event) => event.preventDefault());
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

  [["دسته", categorySelect], ["تأمین‌کننده", providerSelect],
   ["نوع محصول", typeSelect], ["جست‌وجو", search]].forEach(([label, field]) => {
    const wrapper = element("label", "field");
    wrapper.append(element("span", "", label), field);
    filters.append(wrapper);
  });
  filters.append(apply);

  const results = element("div", "price-mapping-panel__results");
  const unitRow = element("div", "price-mapping-panel__unit");
  const unitSelect = element("select", "");
  unitSelect.name = "selectedUnit";
  unitSelect.disabled = true;
  const unitLabel = element("label", "field");
  unitLabel.append(element("span", "", "واحد رسمی محاسبه"), unitSelect);
  const preview = element("div", "price-mapping-panel__preview");
  unitRow.append(unitLabel, preview);

  const reason = element("textarea", "");
  reason.name = "reason";
  reason.rows = 2;
  reason.placeholder = "چرا این محصول برای این قلم انتخاب شد؟";
  const reasonLabel = element("label", "field");
  reasonLabel.append(element("span", "", "دلیل"), reason);

  const save = element("button", "button button--primary", "ثبت اتصال");
  save.type = "button";
  save.disabled = true;
  const feedback = element("p", "form-feedback", "");

  function renderPreview(body) {
    lastPreview = body;
    preview.replaceChildren();
    if (!body) return;
    preview.append(statusChip(body.status, body.statusLabel));
    if (body.reason) preview.append(element("p", "price-mapping-panel__reason", body.reason));
    const figures = element("dl", "price-mapping-panel__figures");
    figures.append(
      element("dt", "", "قیمت روز محصول"), element("dd", "numeric", priceText(body.sourcePriceIRR ?? body.convertedDailyUnitPriceIRR)),
      element("dt", "", "قیمت تبدیل‌شده در واحد انتخابی"), element("dd", "numeric", priceText(body.convertedDailyUnitPriceIRR)),
      element("dt", "", "مقدار قلم"), element("dd", "numeric", body.quantity === null ? "—" : formatDisplayNumber(body.quantity)),
      element("dt", "", "هزینه روز این قلم"), element("dd", "numeric", priceText(body.dailyItemCostIRR)));
    preview.append(figures);
    /* Saving stays possible when the conversion is unresolved: which product this is and
       whether somebody has measured the crossing are different facts, and recording the
       first is progress. The row then shows «نیازمند ضریب تبدیل» until the second exists. */
    save.disabled = !canEdit || !chosen || !selectedUnit;
  }

  async function refreshPreview() {
    if (!chosen || !selectedUnit) { renderPreview(null); return; }
    try {
      renderPreview(await adapter.preview(panel.dataset.estimateLineId, {
        providerItemId: chosen.providerItemId, selectedUnit,
      }));
    } catch (error) {
      feedback.textContent = error?.message ?? "محاسبه قیمت تبدیل‌شده انجام نشد.";
    }
  }

  function choose(candidate, card) {
    chosen = candidate;
    results.querySelectorAll(".price-candidate").forEach((node) =>
      node.classList.toggle("price-candidate--chosen", node === card));
    unitSelect.disabled = !canEdit;
    /* Default to the unit the sheet states this price in, when it is one the registry
       knows. It is a starting point a person can change -- never a decision made for
       them, which is why it is only a preselection and the control stays open. */
    if (!selectedUnit && candidate.sourceUnitCode) {
      selectedUnit = candidate.sourceUnitCode;
      unitSelect.value = selectedUnit;
    }
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
      const title = element("h3", "", candidate.displayName || candidate.name || "—");
      const meta = element("p", "price-candidate__meta",
        [candidate.providerName, candidate.categoryLabel, candidate.externalId]
          .filter(Boolean).join(" · "));
      const price = element("p", "price-candidate__price",
        candidate.currentPriceIRR === null
          ? "بدون قیمت روز"
          : `${priceText(candidate.currentPriceIRR)} به ازای ${formatUnitLabel(candidate.sourceUnitCode)}`);
      const pick = element("button", "button button--ghost", "انتخاب");
      pick.type = "button";
      pick.disabled = !canEdit;
      pick.addEventListener("click", () => choose(candidate, card));
      card.append(title, meta, price, specList(candidate), pick);
      if (!candidate.active) card.append(element("p", "table-note", candidate.inactiveReason ?? "این قلم فعال نیست"));
      results.append(card);
    });
  }

  async function load() {
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
      results.replaceChildren(element("p", "form-feedback", error?.message ?? "فهرست محصولات خوانده نشد."));
    }
  }

  apply.addEventListener("click", load);
  categorySelect.addEventListener("change", load);
  providerSelect.addEventListener("change", load);
  typeSelect.addEventListener("change", load);
  unitSelect.addEventListener("change", () => { selectedUnit = unitSelect.value; refreshPreview(); });

  save.addEventListener("click", async () => {
    feedback.textContent = "";
    if (!chosen || !selectedUnit) { feedback.textContent = "محصول و واحد رسمی را انتخاب کنید."; return; }
    if (!reason.value.trim()) { feedback.textContent = "دلیل ثبت اتصال الزامی است."; return; }
    save.disabled = true;
    try {
      const saved = await adapter.saveMapping(panel.dataset.estimateLineId, {
        providerItemId: chosen.providerItemId,
        selectedUnit,
        reason: reason.value.trim(),
      });
      onSaved?.(saved);
    } catch (error) {
      feedback.textContent = error?.message ?? "ثبت اتصال انجام نشد.";
      save.disabled = false;
    }
  });

  (async () => {
    try {
      const body = await adapter.filters();
      units = body.units ?? [];
      categorySelect.replaceChildren(blankOption("همه دسته‌ها"));
      (body.categories ?? []).forEach((category) => {
        const option = element("option", "", `${category.label} (${category.itemCount})`);
        option.value = category.category;
        categorySelect.append(option);
      });
      providerSelect.replaceChildren(blankOption("همه تأمین‌کننده‌ها"));
      (body.providers ?? []).forEach((provider) => {
        const option = element("option", "", provider.name);
        option.value = provider.id;
        providerSelect.append(option);
      });
      typeSelect.replaceChildren(blankOption("همه انواع"));
      (body.productTypes ?? []).forEach((type) => {
        const option = element("option", "", type);
        option.value = type;
        typeSelect.append(option);
      });
      unitSelect.replaceChildren(blankOption("انتخاب واحد"));
      units.forEach((unit) => {
        const option = element("option", "", `${unit.label} (${unit.dimensionLabel})`);
        option.value = unit.code;
        unitSelect.append(option);
      });
    } catch (error) {
      feedback.textContent = error?.message ?? "فهرست فیلترها خوانده نشد.";
    }
    await load();
  })();

  if (!canEdit) {
    /* A viewer sees everything and changes nothing. The controls are disabled rather than
       hidden so it is clear the workflow exists and who may use it. */
    [search, apply, unitSelect, reason, save].forEach((node) => { node.disabled = true; });
    panel.append(element("p", "table-note", "برای ویرایش اتصال، دسترسی finance.edit لازم است."));
  }

  panel.append(head, filters, results, unitRow, reasonLabel, save, feedback);
  return panel;
}
