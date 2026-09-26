import { element } from "../../shared/dom/elements.js";
import { formatUnitLabel, formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { validatePriceVersion } from "../prices/prices-validation.js";
import { FILTERS, equipmentRows, groupByUnit, historyFor, isPriced, needsWorkingDayRule,
         pricingProgress, selectRows, workingDayRule } from "./equipment-pricing-model.js";
import { actorLabel } from "../../shared/formatters/actor.js";

/* Pricing the project's machines, in one place, by hand.
 *
 * WHY THIS SECTION EXISTS
 * Every material on this project has a market price arriving from a sheet. No machine
 * does: «بیل مکانیکی» costs what was agreed with whoever owns it, and the schedule file
 * carries no rate for any of the nineteen machines it names — measured, every equipment
 * row has a rate of zero. So these prices are typed, and this is where.
 *
 * IT IS NOT A SEPARATE KIND OF PRICE
 * Saving here writes the same `price_versions` row the prices page writes for a material:
 * same scopes, same versioning, same author, same history. Only the way the number arrives
 * is different, which is why this is a section and not a subsystem.
 *
 * THE UNIT IS SHOWN, NEVER ASKED
 * It comes from the schedule file. کامیون is assigned by the hour on this project and
 * جرثقیل by the day, and both appear here under headings that say so. A unit picker would
 * let somebody price a machine in a unit the estimate never asks for, and the row would
 * then need a conversion rule to undo a choice nobody should have been offered.
 */

const SCOPES = Object.freeze([
  { value: "project", label: "فقط این پروژه",
    hint: "قیمتی که با پیمانکار همین پروژه توافق شده." },
  { value: "organization", label: "کل سازمان",
    hint: "برای همهٔ پروژه‌های این سازمان که همین دستگاه را با همین واحد دارند." },
]);

const SCOPE_LABELS = Object.fromEntries(SCOPES.map((s) => [s.value, s.label]));

/** «هر ساعت» / «هر روز», or the honest gap when the file named no unit. */
function perUnit(unit) {
  const label = formatUnitLabel(unit);
  return label ? `هر ${label}` : null;
}

function priceLine(row) {
  if (!isPriced(row)) return element("span", "missing-value", "هنوز قیمتی ثبت نشده");
  const wrap = element("span", "equipment-price__figure");
  wrap.append(element("strong", "numeric", formatTomanFromIrr(row.unitPriceIRR)));
  const per = perUnit(row.unit);
  if (per) wrap.append(element("span", "equipment-price__per", `به ازای ${per}`));
  return wrap;
}

/** Where the number in force came from, said only when it is worth knowing. */
function provenance(row) {
  if (!isPriced(row)) return null;
  const parts = [];
  if (row.priceScope) parts.push(SCOPE_LABELS[row.priceScope] ?? row.priceScope);
  if (row.effectiveFrom) parts.push(`از ${formatBusinessDate(row.effectiveFrom)}`);
  /* A project price standing over an organization one is the single thing a person
     revising this row most needs to know, because revising the wrong level changes
     nothing they can see. */
  if (row.priceScope === "project" && row.organizationPrice) {
    parts.push(`قیمت سازمان: ${formatTomanFromIrr(row.organizationPrice.unitPriceIRR)}`);
  }
  return parts.length ? element("p", "table-note", parts.join(" · ")) : null;
}

/**
 * @param workspace   what `pricesAdapter.getPrices()` answered
 * @param adapter     needs `createPriceVersion(values)`, which answers a fresh workspace
 * @param canEdit     whether this account may write a price at all
 * @param onSaved     handed the fresh workspace, so the page repaints from the service
 */
export function createEquipmentPricingSection({ workspace, adapter, canEdit = true, onSaved }) {
  const section = element("section", "settings-card settings-equipment");

  const rows = equipmentRows(workspace);
  const progress = pricingProgress(rows);
  /* A price per hour is half a cost. The schedule measures a machine's span in DAYS, so
     for every hourly machine the two halves meet only through «ساعت هر روز دستگاه» — and
     eighteen of this project's nineteen are hourly. Without it, pricing all of them
     produces nothing, and nothing on this screen would have said why. */
  const workingDay = workingDayRule(workspace);

  /* Held here rather than rebuilt: repainting the list must not throw away what somebody
     typed into the search box or which filter they chose. */
  let search = "";
  let filter = "all";
  let editingId = null;
  /* Which machine's revisions are open, and the project's versions once they have been
     asked for. The service publishes every version at once, so the first machine opened
     pays for the request and none of the others do. */
  let historyId = null;
  let history = null;
  let historyError = null;
  let historyLoading = false;

  const head = element("div", "settings-card__head settings-card__head--actions");
  const copy = element("div", "settings-card__head-copy");
  copy.append(
    element("h2", "", "قیمت‌گذاری نیرو و تجهیزات"),
    element("p", "",
      "اکیپ‌ها و دستگاه‌های این پروژه قیمت بازار ندارند و باید دستی قیمت‌گذاری شوند. "
      + "واحد هر ردیف از فایل زمان‌بندی می‌آید و قابل تغییر نیست — قیمت را به ازای همان واحد وارد کنید."));
  head.append(element("div", "settings-card__icon", "⚙"), copy);

  /* The one number that says whether this job is finished. */
  const counter = element("span", "section-count", "");
  head.append(counter);
  section.append(head);

  // ------------------------------------------------------------------ search and filter

  const controls = element("div", "equipment-controls");
  const searchInput = element("input", "app-input equipment-controls__search");
  searchInput.type = "search";
  searchInput.placeholder = "جست‌وجوی نام یا کد دستگاه";
  searchInput.setAttribute("aria-label", "جست‌وجو در تجهیزات");
  searchInput.addEventListener("input", () => { search = searchInput.value; paintList(); });

  const filterGroup = element("div", "equipment-controls__filters");
  filterGroup.setAttribute("role", "group");
  filterGroup.setAttribute("aria-label", "فیلتر وضعیت قیمت");
  const filterButtons = new Map();
  FILTERS.forEach((option) => {
    /* `app-chip` is the module's own filter chip, the same one the prices page
       uses for categories. Every feature stylesheet is loaded globally, so this is the
       existing control rather than a second one that looks nearly like it. */
    const button = element("button", "app-chip", option.label);
    button.type = "button";
    button.dataset.filter = option.value;
    button.addEventListener("click", () => { filter = option.value; editingId = null; paintList(); });
    filterButtons.set(option.value, button);
    filterGroup.append(button);
  });
  controls.append(searchInput, filterGroup);
  section.append(controls);

  /* The scroller. Nineteen machines today and a bigger project has hundreds, so the list
     scrolls inside the card rather than growing the page and pushing every other setting
     out of reach. */
  const list = element("div", "equipment-list");
  list.setAttribute("role", "list");
  section.append(list);

  const feedback = element("p", "form-feedback", "");
  section.append(feedback);

  // ------------------------------------------------------------------------- the editor

  /** The whole of writing a price: one amount, one level, one date. */
  function editorFor(row) {
    const editor = element("form", "equipment-editor");
    editor.noValidate = true;

    const amountField = element("label", "form-field equipment-editor__amount");
    const per = perUnit(row.unit);
    amountField.append(element("span", "form-label",
      per ? `قیمت ${per} (${getDisplayCurrencyLabel()})` : `قیمت واحد (${getDisplayCurrencyLabel()})`));
    const amount = element("input", "app-input numeric");
    amount.type = "text";
    amount.inputMode = "decimal";
    amount.autocomplete = "off";
    amount.name = "unitPriceIRR";
    amountField.append(amount);

    const scopeField = element("label", "form-field");
    scopeField.append(element("span", "form-label", "سطح قیمت"));
    const scope = element("select", "app-select");
    scope.name = "scope";
    SCOPES.forEach((option) => {
      const node = element("option", "", option.label);
      node.value = option.value;
      scope.append(node);
    });
    scopeField.append(scope);
    const scopeHint = element("p", "table-note", SCOPES[0].hint);
    scope.addEventListener("change", () => {
      scopeHint.textContent = SCOPES.find((s) => s.value === scope.value)?.hint ?? "";
    });

    const date = createPersianDatePicker({
      id: `equipment-date-${row.resourceId}`,
      label: "از چه تاریخی",
      value: getTehranTodayIso(),
      hint: "قیمت از این تاریخ به بعد اعمال می‌شود.",
    });

    const errors = element("p", "form-feedback", "");
    const save = element("button", "button button--primary", isPriced(row) ? "ثبت قیمت جدید" : "ثبت قیمت");
    save.type = "submit";
    const cancel = element("button", "button button--ghost", "انصراف");
    cancel.type = "button";
    cancel.addEventListener("click", () => { editingId = null; paintList(); });
    const actions = element("div", "equipment-editor__actions");
    actions.append(save, cancel);

    /* Said once, here, because it is the thing people fear about a price field: revising
       does not rewrite history, and no report already issued moves. */
    const note = element("p", "table-note",
      isPriced(row)
        ? "قیمت قبلی بایگانی می‌شود و در تاریخچهٔ تغییرات مالی با نام شما می‌ماند."
        : "این قیمت در تاریخچهٔ تغییرات مالی با نام شما ثبت می‌شود.");

    editor.append(amountField, scopeField, scopeHint, date.field, actions, note, errors);

    editor.addEventListener("submit", async (event) => {
      event.preventDefault();
      errors.textContent = "";
      const validation = validatePriceVersion({
        resourceId: row.resourceId,
        scope: scope.value,
        unitPriceIRR: tomanInputToIrr(amount.value),
        effectiveFrom: date.getValue(),
      });
      if (!validation.valid) {
        errors.textContent = validation.errors.unitPriceIRR
          || validation.errors.effectiveFrom || validation.errors.scope
          || "ورودی‌ها را بررسی کنید.";
        amount.focus();
        return;
      }
      save.disabled = true;
      cancel.disabled = true;
      errors.textContent = "در حال ثبت…";
      try {
        /* No reason is asked for. A price revision is a fact with an author and a date,
           and demanding a sentence for each of nineteen machines is how a form gets
           filled with «تست». The service records who and when regardless. */
        /* No reason, not even a generated one. The service now accepts its absence, and
           a sentence this screen wrote is still a sentence nobody wrote: in the history it
           is indistinguishable from one a person meant. What identifies a machine's rate
           is the resource it is against, which the row already carries. */
        const fresh = await adapter.createPriceVersion(validation.values);
        editingId = null;
        onSaved?.(fresh);
      } catch (error) {
        errors.textContent = formatApiErrorMessage(error, "ثبت قیمت انجام نشد.");
        save.disabled = false;
        cancel.disabled = false;
      }
    });

    /* Focus lands in the only field that matters, so a person who clicked «ثبت قیمت»
       types the number immediately. */
    queueMicrotask(() => amount.focus());
    return editor;
  }

  /**
   * What happened to THIS machine's rate, and who changed it.
   *
   * A machine's price is an agreement rather than a market fact, so the useful question is
   * never «what happened to prices» but «what happened to this one». The prices page shows
   * the project's revisions together, which answers the first and buries the second.
   */
  function historyFor_(row) {
    const panel = element("div", "equipment-history");
    if (historyLoading) {
      panel.append(element("p", "table-note", "در حال خواندن تاریخچه…"));
      return panel;
    }
    if (historyError) {
      panel.append(element("p", "inline-notice",
        formatApiErrorMessage(historyError, "خواندن تاریخچهٔ قیمت انجام نشد.")));
      return panel;
    }
    const versions = historyFor(history, row.resourceId);
    if (!versions.length) {
      /* The row is priced and the list is empty only when the service published no
         versions at all — said plainly rather than drawn as an empty table. */
      panel.append(element("p", "table-note", "بازنگری‌ای برای این دستگاه ثبت نشده است."));
      return panel;
    }
    const list = element("ol", "equipment-history__list");
    versions.forEach((version, index) => {
      const item = element("li", "equipment-history__item");
      if (index === 0) item.dataset.current = "true";
      const figure = element("div", "equipment-history__figure");
      figure.append(element("strong", "numeric", formatTomanFromIrr(version.unitPriceIRR)));
      const per = perUnit(row.unit);
      if (per) figure.append(element("span", "equipment-price__per", `به ازای ${per}`));
      /* Which of the two is in force is the thing a reader scanning this list is looking
         for, and version order alone does not say it. */
      if (index === 0) figure.append(element("span", "equipment-history__badge", "در حال اعمال"));
      const meta = [
        SCOPE_LABELS[version.scope] ?? version.scope,
        version.effectiveFrom ? `از ${formatBusinessDate(version.effectiveFrom)}` : null,
        `ثبت: ${actorLabel(version.actorName, version.actorId)}`,
      ].filter(Boolean);
      item.append(figure, element("p", "table-note", meta.join(" · ")));
      /* A reason is optional by design — the service stopped requiring one because
         requiring it produced placeholders. Shown when somebody wrote one, absent when
         they did not, and never replaced by an invented sentence. */
      if (version.reason) item.append(element("p", "equipment-history__reason", version.reason));
      list.append(item);
    });
    panel.append(list);
    return panel;
  }

  async function openHistory(resourceId) {
    historyId = historyId === resourceId ? null : resourceId;
    if (historyId === null) { paintList(); return; }
    if (history !== null || typeof adapter.getPriceHistory !== "function") { paintList(); return; }
    historyLoading = true;
    historyError = null;
    paintList();
    try {
      history = await adapter.getPriceHistory();
      historyError = null;
    } catch (error) {
      historyError = error;
    } finally {
      historyLoading = false;
      paintList();
    }
  }

  // --------------------------------------------------------------------------- the list

  function paintList() {
    filterButtons.forEach((button, value) => {
      button.classList.toggle("app-chip--active", value === filter);
      button.setAttribute("aria-pressed", String(value === filter));
    });
    const priced = formatDisplayNumber(String(progress.priced));
    const total = formatDisplayNumber(String(progress.total));
    counter.textContent = `${priced} از ${total}`;
    counter.title = `${priced} ردیف از ${total} ردیف نیرو و تجهیزات قیمت دارد`;

    const visible = selectRows(rows, { search, filter });
    list.replaceChildren();

    if (!rows.length) {
      list.append(element("p", "inline-notice",
        "در فایل زمان‌بندی این پروژه هیچ نیرو یا دستگاهی ثبت نشده است."));
      return;
    }
    if (!visible.length) {
      list.append(element("p", "inline-notice",
        filter === "unpriced" ? "همهٔ ردیف‌های نیرو و تجهیزات قیمت دارند."
          : filter === "priced" ? "هنوز هیچ ردیفی قیمت‌گذاری نشده است."
          : "ردیفی با این عبارت پیدا نشد."));
      return;
    }

    groupByUnit(visible).forEach((group) => {
      const unitLabel = formatUnitLabel(group.unit);
      const groupNode = element("div", "equipment-group");
      const heading = element("h3", "equipment-group__title",
        unitLabel ? `قیمت‌گذاری بر اساس ${unitLabel}` : "بدون واحد در فایل زمان‌بندی");
      const count = element("span", "equipment-group__count",
        `${formatDisplayNumber(String(group.pricedCount))} از ${formatDisplayNumber(String(group.rows.length))}`);
      heading.append(count);
      groupNode.append(heading);

      /* The hourly machines and the rule their cost depends on. Stated quietly when it
         exists — a person pricing in hours should know which day the hours are counted
         against — and as the blocking fact when it does not. */
      if (group.unit === "hour" && needsWorkingDayRule(group.rows)) {
        if (workingDay) {
          groupNode.append(element("p", "table-note",
            `در این پروژه هر روز دستگاه ${formatDisplayNumber(workingDay.factor)} ساعت حساب می‌شود.`
            + " مقدار ساعت هر دستگاه از مدت فعالیت‌های آن و همین قاعده به دست می‌آید."));
        } else {
          const notice = element("p", "inline-notice",
            "برای این دستگاه‌ها هنوز مشخص نشده هر روز دستگاه چند ساعت است. تا وقتی این قاعده "
            + "در بخش «قواعد تبدیل واحد پروژه» ثبت نشود، قیمت ساعتی در هیچ مقداری ضرب نمی‌شود "
            + "و هزینه‌ای ساخته نمی‌شود.");
          notice.setAttribute("role", "status");
          groupNode.append(notice);
        }
      }

      /* The group the file left unanswered. Priced here it would be a number per nothing,
         so the section says what has to happen first instead of offering a box. */
      if (!group.unit) {
        groupNode.append(element("p", "inline-notice",
          "فایل زمان‌بندی برای این دستگاه‌ها واحدی نگفته است. تا وقتی واحد مشخص نشود، "
          + "قیمت به ازای چیزی ثبت نمی‌شود."));
      }

      group.rows.forEach((row) => {
        const item = element("div", "equipment-row");
        item.setAttribute("role", "listitem");
        item.dataset.resourceId = row.resourceId;
        item.dataset.priced = String(isPriced(row));

        const identity = element("div", "equipment-row__identity");
        identity.append(element("strong", "", row.title));
        if (row.code) identity.append(element("span", "equipment-row__code", row.code));

        const figure = element("div", "equipment-row__price");
        figure.append(priceLine(row));
        const where = provenance(row);
        if (where) figure.append(where);

        item.append(identity, figure);

        if (canEdit && group.unit) {
          const open = element("button", "button button--ghost",
            isPriced(row) ? "بازنگری قیمت" : "ثبت قیمت");
          open.type = "button";
          open.dataset.action = "price-equipment";
          open.addEventListener("click", () => {
            editingId = editingId === row.resourceId ? null : row.resourceId;
            paintList();
          });
          const actions = element("div", "equipment-row__actions");
          actions.append(open);
          item.append(actions);
        }

        /* Offered only on a machine that HAS a rate: there is no history of a price
           nobody has set, and a button promising one would open on nothing. Shown to
           readers as well as editors — seeing who changed a rate is not an edit. */
        if (isPriced(row)) {
          const seen = element("button", "button button--ghost", "تاریخچهٔ قیمت");
          seen.type = "button";
          seen.dataset.action = "equipment-history";
          seen.setAttribute("aria-expanded", String(historyId === row.resourceId));
          seen.addEventListener("click", () => openHistory(row.resourceId));
          const holder = item.querySelector(".equipment-row__actions")
            ?? item.appendChild(element("div", "equipment-row__actions"));
          holder.append(seen);
        }

        groupNode.append(item);
        if (editingId === row.resourceId) groupNode.append(editorFor(row));
        if (historyId === row.resourceId) groupNode.append(historyFor_(row));
      });
      list.append(groupNode);
    });
  }

  if (!canEdit) {
    feedback.textContent = "ثبت قیمت تجهیزات نیازمند مجوز ویرایش اطلاعات مالی است.";
  }
  paintList();
  return section;
}
