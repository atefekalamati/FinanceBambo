import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { downloadCsvFile } from "../../shared/exports/csv.js";
import { buildPricesCsv, pricesFileName } from "./prices-csv.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { createPriceTrend } from "../../shared/components/price-trend.js";
import { validatePriceVersion } from "./prices-validation.js";
import { getCompatibleTargetUnits, getConfigurableSourceUnits, getUnitDefinition, validateUnitConversion } from "./unit-conversions-validation.js";
import { describeImportPreview } from "../../shared/imports/import-preview-notice.js";
import { element } from "../../shared/dom/elements.js";
import { IDENTITY, PRIMARY, SECONDARY, applyColumnVisibility, createColumnControl, createDataTable, defaultVisibleColumns }
  from "../../shared/components/data-table.js";

const SCOPE_LABELS = Object.freeze({ organization: "پایه سازمان", project: "اختصاصی پروژه" });

function createSelect({ id, label, options }) {
  const field = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const select = document.createElement("select");
  select.id = id;
  const placeholder = element("option", "", "انتخاب کنید");
  placeholder.value = "";
  select.append(placeholder);
  options.forEach((option) => {
    const item = element("option", "", option.label);
    item.value = option.value;
    select.append(item);
  });
  const error = element("small", "form-error");
  error.setAttribute("aria-live", "polite");
  select.setAttribute("aria-describedby", `${id}Error`);
  error.id = `${id}Error`;
  field.append(labelNode, select, error);
  return { field, select, error };
}

function createInput({ id, label, type = "text", value = "", hint = "", inputMode }) {
  const field = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const input = document.createElement("input");
  input.id = id;
  input.type = type;
  input.value = value;
  if (inputMode) input.inputMode = inputMode;
  const hintNode = element("small", "form-hint", hint);
  hintNode.id = `${id}Hint`;
  const error = element("small", "form-error");
  error.id = `${id}Error`;
  error.setAttribute("aria-live", "polite");
  input.setAttribute("aria-describedby", `${hintNode.id} ${error.id}`);
  field.append(labelNode, input, hintNode, error);
  return { field, input, error };
}

export function createUnitConversionForm(adapter, workspace, onSaved, onCancel = () => {}) {
  const dialog = document.createElement("section");
  dialog.className = "conversion-inline-editor";
  const head = element("header", "price-dialog__head");
  const title = element("h3", "", "تعریف قاعده کاری تبدیل واحد");
  head.append(title);
  const form = element("form", "price-form conversion-inline-form");
  form.noValidate = true;
  const unitOptions = getConfigurableSourceUnits().map((unit) => ({ value: unit.value, label: `${unit.label} (${unit.value}) · ${unit.dimensionLabel}` }));
  const source = createSelect({ id: "conversionSourceUnit", label: "واحد مبدأ", options: unitOptions });
  const target = createSelect({ id: "conversionTargetUnit", label: "واحد مقصد سازگار", options: [] });
  target.select.disabled = true;
  const factor = createInput({ id: "conversionFactor", label: "هر ۱ واحد مبدأ برابر است با", hint: "مقدار معادل را در واحد مقصد وارد کنید؛ حداکثر شش رقم اعشار.", inputMode: "decimal" });
  const scope = createSelect({
    id: "conversionScope",
    label: "سطح تبدیل",
    options: [
      { value: "organization", label: "قابل استفاده در تمام پروژه‌های سازمان" },
      { value: "project", label: "فقط برای پروژه فعلی" },
    ],
  });
  const effectiveDate = createPersianDatePicker({ id: "conversionEffectiveDate", label: "تاریخ شروع اعتبار", value: getTehranTodayIso(), hint: "محاسبات از این تاریخ به بعد از قاعده جدید استفاده می‌کنند." });
  const preview = element("section", "conversion-preview");
  preview.setAttribute("role", "status");
  preview.setAttribute("aria-live", "polite");
  const previewTitle = element("strong", "", "پیش‌نمایش تبدیل");
  const previewSentence = element("p", "", "ابتدا واحد مبدأ و مقصد را انتخاب کنید.");
  const currentRule = element("small", "", "");
  preview.append(previewTitle, previewSentence, currentRule);
  const scopeHint = element("div", "conversion-scope-hint", "سطح تبدیل را انتخاب کنید تا محدوده استفاده از این قاعده مشخص شود.");
  scopeHint.setAttribute("role", "status");
  const notice = element("div", "inline-notice", "این فرم فقط برای قواعد کاری متغیر است. تبدیل‌های فیزیکی استاندارد مانند تن به کیلوگرم ثابت و غیرقابل‌ویرایش‌اند.");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", onCancel);
  const submit = element("button", "button button--primary", "ثبت نسخه تبدیل");
  submit.type = "submit";
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(source.field, target.field, factor.field, scope.field, effectiveDate.field, preview, scopeHint, notice, actions);

  function replaceTargetOptions() {
    const selected = target.select.value;
    const options = getCompatibleTargetUnits(source.select.value);
    target.select.replaceChildren(element("option", "", options.length ? "واحد مقصد را انتخاب کنید" : "ابتدا واحد مبدأ را انتخاب کنید"));
    target.select.firstElementChild.value = "";
    options.forEach((unit) => {
      const option = element("option", "", `${unit.label} (${unit.value}) · ${unit.dimensionLabel}`);
      option.value = unit.value;
      target.select.append(option);
    });
    target.select.disabled = !options.length;
    if (options.some((unit) => unit.value === selected)) target.select.value = selected;
  }

  function syncPreview() {
    const sourceDefinition = getUnitDefinition(source.select.value);
    const targetDefinition = getUnitDefinition(target.select.value);
    const enteredFactor = factor.input.value.trim();
    previewSentence.textContent = sourceDefinition && targetDefinition && enteredFactor
      ? `هر ۱ ${sourceDefinition.label} برابر با ${formatDisplayNumber(enteredFactor)} ${targetDefinition.label} محاسبه می‌شود.`
      : "واحدها و مقدار معادل را وارد کنید تا رابطه تبدیل را پیش از ثبت ببینید.";
    const current = workspace?.currentConversions?.find((item) => item.sourceUnit === source.select.value && item.targetUnit === target.select.value)?.currentConversion;
    currentRule.textContent = current
      ? `قاعده جاری: هر ۱ ${sourceDefinition.label} برابر با ${formatDisplayNumber(current.factor)} ${targetDefinition.label} · ${SCOPE_LABELS[current.scope] ?? ""}`
      : sourceDefinition && targetDefinition ? "برای این مسیر تبدیل، قاعده جاری ثبت نشده است." : "";
  }

  source.select.addEventListener("change", () => {
    replaceTargetOptions();
    syncPreview();
  });
  target.select.addEventListener("change", syncPreview);
  factor.input.addEventListener("input", syncPreview);
  scope.select.addEventListener("change", () => {
    scopeHint.textContent = scope.select.value === "organization"
      ? "این قاعده در تمام پروژه‌های سازمان قابل استفاده خواهد بود."
      : scope.select.value === "project"
        ? "این قاعده فقط برای پروژه فعلی است و بر قاعده عمومی سازمان اولویت دارد."
        : "سطح تبدیل را انتخاب کنید تا محدوده استفاده از این قاعده مشخص شود.";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateUnitConversion({ sourceUnit: source.select.value, targetUnit: target.select.value, factor: factor.input.value, scope: scope.select.value, effectiveDate: effectiveDate.getValue() });
    source.error.textContent = validation.errors.sourceUnit;
    target.error.textContent = validation.errors.targetUnit || validation.errors.dimension || validation.errors.direction || validation.errors.policy;
    factor.error.textContent = validation.errors.factor;
    scope.error.textContent = validation.errors.scope;
    effectiveDate.error.textContent = validation.errors.effectiveDate;
    source.select.setAttribute("aria-invalid", String(Boolean(validation.errors.sourceUnit)));
    target.select.setAttribute("aria-invalid", String(Boolean(validation.errors.targetUnit || validation.errors.dimension || validation.errors.direction || validation.errors.policy)));
    factor.input.setAttribute("aria-invalid", String(Boolean(validation.errors.factor)));
    scope.select.setAttribute("aria-invalid", String(Boolean(validation.errors.scope)));
    effectiveDate.input.setAttribute("aria-invalid", String(Boolean(validation.errors.effectiveDate)));
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      form.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    submit.disabled = true;
    cancel.disabled = true;
    status.textContent = "در حال ثبت تبدیل…";
    try {
      const workspace = await adapter.createUnitConversion(validation.values);
      onSaved(workspace);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });
  source.select.value = "day";
  replaceTargetOptions();
  target.select.value = "hour";
  factor.input.value = "8";
  scope.select.value = "project";
  syncPreview();
  dialog.append(head, form);
  return dialog;
}

function createPriceImportDialog(adapter, onSaved) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog price-import-dialog";
  const head = element("header", "price-dialog__head");
  const title = element("h2", "", "ورود گروهی قیمت");
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن پنجره");
  close.addEventListener("click", () => dialog.close());
  head.append(title, close);
  const description = element("p", "price-import-dialog__description", "فایل باید شامل کد قلم، قیمت، واحد پول، تاریخ اعتبار و سطح قیمت باشد. پیش‌نمایش معتبر قبل از ثبت نهایی الزامی است.");
  const form = element("form", "price-import-form");
  form.noValidate = true;
  const field = element("div", "form-field");
  const label = element("label", "form-label", "فایل اکسل قیمت‌ها");
  label.htmlFor = "priceImportFile";
  const input = document.createElement("input");
  input.id = "priceImportFile";
  input.type = "file";
  input.accept = ".xlsx";
  const hint = element("small", "form-hint", "واحد پول هر ردیف باید صریح باشد و از روی مبلغ حدس زده نمی‌شود.");
  hint.id = "priceImportHint";
  const error = element("small", "form-error");
  error.id = "priceImportError";
  error.setAttribute("aria-live", "polite");
  input.setAttribute("aria-describedby", `${hint.id} ${error.id}`);
  field.append(label, input, hint, error);
  const previewButton = element("button", "button button--primary", "بررسی و نمایش پیش‌نمایش");
  previewButton.type = "submit";
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const actions = element("div", "form-actions");
  actions.append(previewButton, status);
  form.append(field, actions);
  const resultRegion = element("section", "price-import-result");
  resultRegion.setAttribute("aria-live", "polite");
  resultRegion.hidden = true;

  function renderPreview(preview) {
    resultRegion.replaceChildren();
    resultRegion.hidden = false;
    const summary = element("div", "price-import-summary");
    const copy = element("div", "");
    copy.append(element("h3", "", "نتیجه بررسی فایل"), element("p", "", `${formatDisplayNumber(String(preview.totalRows))} ردیف بررسی شد.`));
    const counters = element("div", "price-import-summary__counters");
    counters.append(
      element("span", "price-import-count price-import-count--valid", `${formatDisplayNumber(String(preview.validRows))} معتبر`),
      element("span", `price-import-count ${preview.invalidRows ? "price-import-count--invalid" : ""}`, `${formatDisplayNumber(String(preview.invalidRows))} خطادار`),
    );
    summary.append(copy, counters);

    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table price-import-table");
    table.append(element("caption", "sr-only", "پیش‌نمایش ردیف‌های فایل قیمت"));
    const tableHead = document.createElement("thead");
    const header = document.createElement("tr");
    ["ردیف", "قلم هزینه", "قیمت", "واحد پول", "تاریخ اعتبار", "سطح قیمت", "نتیجه بررسی"].forEach((labelText) => header.append(element("th", "", labelText)));
    tableHead.append(header);
    const body = document.createElement("tbody");
    preview.rows.forEach((row) => {
      const record = document.createElement("tr");
      if (row.status === "invalid") record.className = "price-import-row--invalid";
      const resource = document.createElement("td");
      resource.append(element("strong", "", row.resourceTitle), element("small", "table-subtext numeric", row.resourceCode));
      const validationCell = document.createElement("td");
      if (row.errors.length) {
        const list = element("ul", "price-import-errors");
        row.errors.forEach((message) => list.append(element("li", "", message)));
        validationCell.append(list);
      } else {
        validationCell.append(element("span", "price-import-status", "معتبر"));
      }
      record.append(
        element("td", "numeric", formatDisplayNumber(String(row.rowNumber))),
        resource,
        element("td", "numeric", /^\d+$/.test(row.importedAmount ?? row.unitPriceIRR) ? formatDisplayNumber(row.importedAmount ?? row.unitPriceIRR) : row.unitPriceIRR),
        element("td", "", row.currency === "IRR" ? CURRENCY_LABELS.IRR : row.currency === "TOMAN" ? CURRENCY_LABELS.TOMAN : "نامعتبر"),
        element("td", "", row.status === "valid" ? formatBusinessDate(row.effectiveFrom) : "نامعتبر"),
        element("td", "", SCOPE_LABELS[row.scope] ?? "نامعتبر"),
        validationCell,
      );
      body.append(record);
    });
    table.append(tableHead, body);
    wrapper.append(table);
    const verdict = describeImportPreview(preview, {
      readyText: "تمام ردیف‌ها معتبرند و آماده ثبت نهایی هستند.",
      invalidText: "فایل ثبت نشده است. خطاها را اصلاح و دوباره پیش‌نمایش بگیرید.",
    });
    const notice = element("div", verdict.tone === "ready" ? "inline-notice" : "price-import-warning", verdict.text);
    const commit = element("button", "button button--primary", "ثبت نهایی قیمت‌ها");
    commit.type = "button";
    commit.disabled = !preview.canCommit;
    const resultActions = element("div", "price-import-result__actions");
    resultActions.append(commit);
    commit.addEventListener("click", () => {
      const confirmation = document.createElement("dialog");
      confirmation.className = "confirm-dialog";
      const confirmTitle = element("h2", "", "تأیید ثبت نهایی قیمت‌ها");
      const message = element("p", "", `${formatDisplayNumber(String(preview.validRows))} نسخه قیمت جدید به تاریخچه افزوده می‌شود و نسخه‌های قبلی تغییر نمی‌کنند.`);
      const cancel = element("button", "button button--ghost", "لغو");
      cancel.type = "button";
      const confirm = element("button", "button button--primary", "تأیید و ثبت نهایی");
      confirm.type = "button";
      const confirmStatus = element("div", "form-status");
      confirmStatus.setAttribute("role", "status");
      confirmStatus.setAttribute("aria-live", "polite");
      const confirmActions = element("div", "dialog-actions");
      confirmActions.append(cancel, confirm);
      confirmation.append(confirmTitle, message, confirmActions, confirmStatus);
      cancel.addEventListener("click", () => confirmation.close());
      confirm.addEventListener("click", async () => {
        cancel.disabled = true;
        confirm.disabled = true;
        confirmStatus.textContent = "در حال ثبت نهایی…";
        try {
          const committed = await adapter.commitPriceImport({ previewId: preview.previewId });
          confirmation.close();
          dialog.close();
          onSaved(committed.workspace);
        } catch (commitError) {
          confirmStatus.textContent = formatApiErrorMessage(commitError);
        } finally {
          cancel.disabled = false;
          confirm.disabled = false;
        }
      });
      dialog.after(confirmation);
      confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
      showAccessibleDialog(confirmation);
    });
    resultRegion.append(summary, wrapper, notice, resultActions);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files?.[0];
    error.textContent = file ? "" : "انتخاب فایل اکسل الزامی است.";
    input.setAttribute("aria-invalid", String(!file));
    if (!file) {
      input.focus();
      return;
    }
    input.disabled = true;
    previewButton.disabled = true;
    resultRegion.hidden = true;
    status.textContent = "در حال بررسی فایل…";
    try {
      const preview = await adapter.previewPriceImport(file);
      status.textContent = preview.canCommit ? "پیش‌نمایش معتبر آماده است." : "پیش‌نمایش دارای خطاست.";
      renderPreview(preview);
    } catch (previewError) {
      error.textContent = formatApiErrorMessage(previewError);
      status.textContent = "بررسی فایل انجام نشد.";
    } finally {
      input.disabled = false;
      previewButton.disabled = false;
    }
  });

  dialog.append(head, description, form, resultRegion);
  return dialog;
}

function createPriceDialog(adapter, currentPrices, onSaved) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog price-dialog";
  const head = element("header", "price-dialog__head");
  const title = element("h2", "", "ثبت نسخه جدید قیمت");
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن پنجره");
  close.addEventListener("click", () => dialog.close());
  head.append(title, close);

  const form = element("form", "price-form");
  form.noValidate = true;
  const resource = createSelect({
    id: "priceResource",
    label: "قلم هزینه",
    options: currentPrices.map((item) => ({ value: item.resource.resourceId, label: `${item.resource.code} · ${item.resource.title}` })),
  });
  const scope = createSelect({
    id: "priceScope",
    label: "سطح قیمت",
    options: [
      { value: "organization", label: "قیمت پایه سازمان" },
      { value: "project", label: "قیمت اختصاصی پروژه" },
    ],
  });
  const amount = createInput({ id: "unitPriceIRR", label: `قیمت واحد (${getDisplayCurrencyLabel()})`, hint: `مبلغ با واحد نمایش انتخاب‌شده وارد می‌شود و برای Backend به ${CURRENCY_LABELS.IRR} ارسال خواهد شد.`, inputMode: "decimal" });
  const effectiveFrom = createPersianDatePicker({ id: "priceEffectiveFrom", label: "تاریخ اعتبار", value: getTehranTodayIso(), hint: "تاریخ را براساس تقویم جلالی و زمان ایران انتخاب کنید." });
  const notice = element("div", "inline-notice", "ثبت قیمت، نسخه جدید می‌سازد. نسخه‌های قبلی و گزارش‌های صادرشده بازنویسی نمی‌شوند.");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت نسخه قیمت");
  submit.type = "submit";
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(resource.field, scope.field, amount.field, effectiveFrom.field, notice, actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validatePriceVersion({
      resourceId: resource.select.value,
      scope: scope.select.value,
      unitPriceIRR: tomanInputToIrr(amount.input.value),
      effectiveFrom: effectiveFrom.getValue(),
    });
    resource.error.textContent = validation.errors.resourceId;
    scope.error.textContent = validation.errors.scope;
    amount.error.textContent = validation.errors.unitPriceIRR;
    effectiveFrom.error.textContent = validation.errors.effectiveFrom;
    resource.select.setAttribute("aria-invalid", String(Boolean(validation.errors.resourceId)));
    scope.select.setAttribute("aria-invalid", String(Boolean(validation.errors.scope)));
    amount.input.setAttribute("aria-invalid", String(Boolean(validation.errors.unitPriceIRR)));
    effectiveFrom.input.setAttribute("aria-invalid", String(Boolean(validation.errors.effectiveFrom)));
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      form.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    submit.disabled = true;
    cancel.disabled = true;
    status.textContent = "در حال ثبت قیمت…";
    try {
      const workspace = await adapter.createPriceVersion(validation.values);
      dialog.close();
      onSaved(workspace);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });

  dialog.append(head, form);
  return dialog;
}

/* The columns of the day-price list. Labels carry the display currency, so they
   are built per render rather than frozen at module load. */
function currentPriceColumns() {
  const currency = getDisplayCurrencyLabel();
  return [
    { key: "identity", label: "قلم هزینه", tier: IDENTITY },
    { key: "unit", label: "واحد پایه", tier: SECONDARY, keepOnTablet: true },
    { key: "organization", label: `قیمت پایه سازمان (${currency})`, tier: SECONDARY, cellClass: "numeric" },
    { key: "project", label: `قیمت اختصاصی پروژه (${currency})`, tier: SECONDARY, cellClass: "numeric" },
    { key: "current", label: `قیمت روز (${currency})`, tier: PRIMARY, cellClass: "numeric price-current" },
    { key: "trend", label: "روند", tier: PRIMARY },
    { key: "scope", label: "منبع قیمت", tier: SECONDARY, keepOnTablet: true },
    { key: "effectiveFrom", label: "تاریخ اعتبار", tier: SECONDARY },
  ];
}

function renderCurrentPrices(items, history, focusResourceId = "", columns, visible) {
  return createDataTable({
    className: "current-prices-table",
    caption: "فهرست قیمت روز اقلام پروژه",
    scrollLabel: "جدول قیمت روز اقلام",
    columns,
    rows: items,
    visible,
    rowAttributes: (item) => (focusResourceId && item.resource.resourceId === focusResourceId
      ? { className: "deep-link-target", tabIndex: -1 }
      : null),
    cells: (item) => {
      // No .data-table-identity here: that class is a flex row, and this cell is a
      // title with its code stacked under it -- .table-subtext is display: block
      // and was doing that before this table moved onto the component.
      const identity = document.createDocumentFragment();
      identity.append(element("strong", "", item.resource.title), element("small", "table-subtext numeric", item.resource.code));
      return {
        identity,
        unit: formatUnitLabel(item.resource.baseUnit),
        organization: item.organizationPrice ? formatTomanFromIrr(item.organizationPrice.unitPriceIRR, { withCurrency: false }) : "—",
        project: item.projectPrice ? formatTomanFromIrr(item.projectPrice.unitPriceIRR, { withCurrency: false }) : "—",
        current: item.currentPrice ? formatTomanFromIrr(item.currentPrice.unitPriceIRR, { withCurrency: false }) : "ثبت نشده",
        trend: createPriceTrend(item, history),
        scope: item.currentPrice ? SCOPE_LABELS[item.currentPrice.scope] : "بدون قیمت",
        effectiveFrom: item.currentPrice ? formatBusinessDate(item.currentPrice.effectiveFrom) : "—",
      };
    },
  });
}

function renderPriceFilters(filters, onApply, onReset) {
  const form = element("form", "price-list-filters");
  const search = element("input", "app-input");
  search.type = "search";
  search.value = filters.query;
  search.placeholder = "جست‌وجوی عنوان یا کد قلم هزینه";
  search.setAttribute("aria-label", "جست‌وجوی قلم هزینه");
  const scope = element("select", "app-select");
  scope.setAttribute("aria-label", "فیلتر منبع قیمت روز");
  [["all", "همه مبناها"], ["project", "اختصاصی پروژه"], ["organization", "پایه سازمان"], ["missing", "بدون قیمت"]].forEach(([value, label]) => {
    const node = element("option", "", label);
    node.value = value;
    scope.append(node);
  });
  scope.value = filters.scope;
  const submit = element("button", "button button--primary", "اعمال فیلتر");
  submit.type = "submit";
  const reset = element("button", "button button--ghost", "پاک‌کردن");
  reset.type = "button";
  reset.addEventListener("click", onReset);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onApply({ query: search.value.trim(), scope: scope.value });
  });
  form.append(search, scope, submit, reset);
  return form;
}

function renderHistory(history, currentPrices) {
  const resourceMap = new Map(currentPrices.map((item) => [item.resource.resourceId, item.resource]));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table price-history-table");
  table.append(element("caption", "sr-only", "تاریخچه تغییرناپذیر قیمت‌ها"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["قلم هزینه", "سطح", `قیمت واحد (${getDisplayCurrencyLabel()})`, "تاریخ اعتبار", "ثبت‌کننده", "زمان ثبت"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  history.forEach((price) => {
    const resource = resourceMap.get(price.resourceId);
    const row = document.createElement("tr");
    row.append(
      element("td", "", resource?.title ?? "قلم حذف‌شده"),
      element("td", "", SCOPE_LABELS[price.scope] ?? "سطح نامشخص"),
      element("td", "numeric", formatTomanFromIrr(price.unitPriceIRR, { withCurrency: false })),
      element("td", "", formatBusinessDate(price.effectiveFrom)),
      element("td", "", price.actorName || price.actorId),
      element("td", "", formatSystemDateTime(price.createdAt)),
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function renderCurrentConversions(items) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table current-conversions-table");
  table.append(element("caption", "sr-only", "فهرست تبدیل‌های واحد جاری"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["تبدیل", "نوع واحد", "ضریب پایه سازمان", "تبدیل اختصاصی پروژه", "ضریب جاری", "مبنای جاری", "تاریخ اعتبار"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  items.forEach((item) => {
    const definition = getUnitDefinition(item.sourceUnit);
    const currentScope = item.currentConversion?.projectId ? "اختصاصی پروژه" : "پایه سازمان";
    const row = document.createElement("tr");
    row.append(
      element("td", "", `${formatUnitLabel(item.sourceUnit)} ← ${formatUnitLabel(item.targetUnit)}`),
      element("td", "", definition?.dimensionLabel ?? "نامشخص"),
      element("td", "numeric", item.organizationConversion ? formatDisplayNumber(item.organizationConversion.factor) : "—"),
      element("td", "numeric", item.projectConversion ? formatDisplayNumber(item.projectConversion.factor) : "—"),
      element("td", "numeric conversion-current", formatDisplayNumber(item.currentConversion.factor)),
      element("td", "", currentScope),
      element("td", "", formatBusinessDate(item.currentConversion.effectiveDate)),
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function renderConversionHistory(history) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table conversion-history-table");
  table.append(element("caption", "sr-only", "تاریخچه نسخه‌های تبدیل واحد"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["واحد مبدأ", "واحد مقصد", "نوع واحد", "ضریب تبدیل", "سطح", "تاریخ اعتبار", "ثبت‌کننده", "زمان ثبت"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  history.forEach((conversion) => {
    const definition = getUnitDefinition(conversion.sourceUnit);
    const row = document.createElement("tr");
    row.append(
      element("td", "", formatUnitLabel(conversion.sourceUnit)),
      element("td", "", formatUnitLabel(conversion.targetUnit)),
      element("td", "", definition?.dimensionLabel ?? "نامشخص"),
      element("td", "numeric", formatDisplayNumber(conversion.factor)),
      element("td", "", conversion.projectId ? "اختصاصی پروژه" : "پایه سازمان"),
      element("td", "", formatBusinessDate(conversion.effectiveDate)),
      element("td", "", conversion.createdByName || conversion.createdBy),
      element("td", "", formatSystemDateTime(conversion.createdAt)),
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

/**
 * The price list, on both surfaces.
 *
 * On امور مالی it is the working page: new versions, bulk entry, the conversion
 * rules. On گزارش مالی it is the same table with nothing to press — and that is
 * decided by which route opened it, not only by what the account may do. An
 * administrator reading the report gets the read-only table too; if they want to
 * change a price they go to the page that is for changing prices. One mode per
 * route is a thing you can reason about; one mode per account is not.
 */
export function createPricesPage({ context, adapter, surface = SURFACES.OPERATIONS, focusResourceId = "" }) {
  const root = element("div", "prices-page");
  const readOnly = surface === SURFACES.REPORT;
  const canEdit = !readOnly && capabilitiesFor(context).writeFinance;
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let listFilters = { query: "", scope: "all" };
  // Lives with the page: paint() rebuilds the tree, so a choice held inside a
  // render would last only until the next filter.
  const priceColumns = currentPriceColumns();
  const visiblePriceColumns = defaultVisibleColumns(priceColumns);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const workspace = await adapter.getPrices();
      state = createRequestState(workspace.history.length || workspace.conversionHistory.length ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, workspace);
    } catch (error) {
      state = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(
      element("span", "feature-header__eyebrow", readOnly ? "جدول قیمت‌های پروژه" : "قیمت روز و تاریخچه قیمت"),
      element("h1", "", readOnly ? "جدول قیمت‌ها" : "قیمت روز"),
      element("p", "", readOnly
        ? "قیمت پایه سازمان، قیمت اختصاصی پروژه و قیمت روز هر قلم. این صفحه فقط‌خواندنی است و می‌توانید از آن خروجی اکسل بگیرید."
        : "قیمت پایه سازمان و قیمت اختصاصی پروژه را بدون بازنویسی نسخه‌های قبلی مدیریت کنید."),
    );
    const back = element("a", "button button--ghost", `بازگشت به ${SURFACE_LABELS[surface]}`);
    back.classList.add("finance-back-link");
    back.href = `#${homeRouteFor(surface)?.path ?? "/finance"}`;
    const navigation = element("div", "feature-header__navigation");
    const otherActions = element("div", "feature-header__other-actions");
    navigation.append(otherActions, back);
    header.append(copy, navigation);
    return header;
  }

  function openEditor(workspace) {
    const dialog = createPriceDialog(adapter, workspace.currentPrices, (next) => {
      state = createRequestState(REQUEST_STATUS.SUCCESS, next);
      paint();
    });
    root.append(dialog);
    showAccessibleDialog(dialog);
  }

  function renderEmpty() {
    const card = element("section", "state-card prices-empty");
    card.append(element("h2", "", "هنوز قیمتی ثبت نشده است"), element("p", "", canEdit ? "اولین قیمت پایه سازمان یا قیمت اختصاصی پروژه را ثبت کنید." : "برای اقلام این پروژه هنوز قیمت قابل نمایشی وجود ندارد."));
    if (canEdit) {
      const button = element("button", "button button--primary", "ثبت اولین قیمت");
      button.type = "button";
      button.addEventListener("click", async () => openEditor(await adapter.getPrices()));
      card.append(button);
    }
    return card;
  }

  function renderContent(workspace) {
    const fragment = document.createDocumentFragment();
    const toolbar = element("div", "prices-toolbar");
    toolbar.append(element("p", "", "قیمت روز، آخرین قیمت معتبر است و قیمت اختصاصی پروژه بر قیمت پایه سازمان اولویت دارد."));
    // Taking away a copy of a table you are already reading is not a privilege,
    // so the export is offered to every account that can see the page.
    const toolbarActions = element("div", "prices-toolbar__actions");
    const exportCsv = element("button", "button button--ghost", "خروجی اکسل");
    exportCsv.type = "button";
    exportCsv.addEventListener("click", () => {
      // What leaves is what is on screen: the filters are already applied.
      downloadCsvFile(buildPricesCsv(filteredPrices), pricesFileName({ projectCode: context.projectCode, asOfDate: workspace.asOfDate }));
    });
    toolbarActions.append(exportCsv);
    toolbar.append(toolbarActions);
    if (canEdit) {
      const importPrices = element("button", "button button--ghost", "ورود گروهی قیمت");
      importPrices.type = "button";
      importPrices.addEventListener("click", () => {
        const dialog = createPriceImportDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      });
      const add = element("button", "button button--primary", "ثبت نسخه جدید قیمت");
      add.type = "button";
      add.addEventListener("click", () => openEditor(workspace));
      const conversions = element("a", "button button--ghost", "مدیریت تبدیل واحد");
      conversions.href = "#/settings";
      toolbarActions.append(conversions, importPrices, add);
    }
    const normalizedQuery = listFilters.query.toLocaleLowerCase("fa-IR");
    const filteredPrices = workspace.currentPrices.filter((item) => {
      const matchesQuery = !normalizedQuery || `${item.resource.title} ${item.resource.code}`.toLocaleLowerCase("fa-IR").includes(normalizedQuery);
      const currentScope = item.currentPrice?.scope ?? "missing";
      return matchesQuery && (listFilters.scope === "all" || currentScope === listFilters.scope);
    });
    const filters = renderPriceFilters(listFilters, (next) => { listFilters = next; paint(); }, () => { listFilters = { query: "", scope: "all" }; paint(); });
    const current = element("section", "prices-section prices-section--current");
    const currentHeading = element("div", "prices-section-heading");
    const currentMeta = element("div", "prices-section-heading__meta");
    currentMeta.append(
      element("span", "section-count numeric", `${formatDisplayNumber(String(filteredPrices.length))} قلم`),
      createColumnControl({
        name: "current-prices",
        columns: priceColumns,
        visible: visiblePriceColumns,
        onToggle: (key, on) => {
          if (on) visiblePriceColumns.add(key);
          else visiblePriceColumns.delete(key);
          applyColumnVisibility(root.querySelector(".current-prices-table"), key, on);
        },
      }),
    );
    currentHeading.append(element("div", "", ""), currentMeta);
    currentHeading.firstElementChild.append(element("h2", "", "قیمت روز اقلام"), element("p", "prices-section__hint", `قیمت‌ها به ${getDisplayCurrencyLabel()} نمایش داده می‌شوند و نمودار کوچک، روند تغییرات هر قلم را نشان می‌دهد.`));
    current.append(currentHeading, filters);
    if (filteredPrices.length) current.append(renderCurrentPrices(filteredPrices, workspace.history, focusResourceId, priceColumns, visiblePriceColumns));
    else current.append(element("div", "state-card price-filter-empty", "قلمی مطابق فیلترهای انتخاب‌شده پیدا نشد."));
    const history = element("section", "prices-section");
    history.append(element("h2", "", "تاریخچه قیمت‌ها"), element("p", "prices-section__hint", "تمام نسخه‌ها فقط‌خواندنی هستند و ثبت جدید، رکورد قبلی را تغییر نمی‌دهد."), renderHistory(workspace.history, workspace.currentPrices));
    fragment.append(toolbar, current, history);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
    const target = root.querySelector(".deep-link-target");
    if (target) queueMicrotask(() => {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.focus({ preventScroll: true });
    });
  }

  load();
  return root;
}
