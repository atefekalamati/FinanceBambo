import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { SURFACES } from "../../core/config/routes.js";
import { renderMaterialPrices } from "./material-prices-section.js";
import { createManualMarketPriceDialog } from "./manual-market-price-dialog.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { getRowsPerPage } from "../../shared/preferences/rows-per-page.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { actorLabel } from "../../shared/formatters/actor.js";
import { createPriceTrend } from "../../shared/components/price-trend.js";
import { validatePriceVersion } from "./prices-validation.js";
import { getCompatibleTargetUnits, getConfigurableSourceUnits, getUnitDefinition, validateUnitConversion } from "./unit-conversions-validation.js";
import { describeImportPreview } from "../../shared/imports/import-preview-notice.js";
import { element } from "../../shared/dom/elements.js";
import { GoogleSheetError, requireSheetLink } from "../../shared/imports/google-sheet.js";
import { IDENTITY, PRIMARY, SECONDARY, createDataTableWithControl, createPagedDataTable, defaultVisibleColumns }
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

  // The same import, from a link instead of a disk.
  const sheetField = element("div", "form-field form-field--wide");
  const sheetLabel = element("label", "form-label", "یا نشانی گوگل شیت");
  sheetLabel.htmlFor = "priceImportSheet";
  const sheetInput = element("input", "app-input");
  sheetInput.id = "priceImportSheet";
  sheetInput.type = "url";
  sheetInput.placeholder = "نشانی برگه را از نوار آدرس مرورگر کپی کنید";
  sheetInput.setAttribute("aria-describedby", "priceSheetHint");
  const sheetHint = element("small", "form-hint", "برگه باید روی «هر کسی که لینک را دارد» باشد. اگر نشانی را از روی تب موردنظر کپی کنید، همان تب خوانده می‌شود.");
  sheetHint.id = "priceSheetHint";
  sheetField.append(sheetLabel, sheetInput, sheetHint);
  const previewButton = element("button", "button button--primary", "بررسی و نمایش پیش‌نمایش");
  previewButton.type = "submit";
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const actions = element("div", "form-actions");
  actions.append(previewButton, status);
  form.append(field, sheetField, actions);
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
    const picked = input.files?.[0];
    const link = sheetInput.value.trim();
    error.textContent = picked || link ? "" : "یک فایل اکسل انتخاب کنید یا نشانی گوگل شیت را وارد کنید.";
    input.setAttribute("aria-invalid", String(!picked && !link));
    if (!picked && !link) {
      input.focus();
      return;
    }
    input.disabled = true;
    sheetInput.disabled = true;
    previewButton.disabled = true;
    resultRegion.hidden = true;
    status.textContent = link && !picked ? "در حال دریافت برگه از گوگل…" : "در حال بررسی فایل…";
    try {
      // A picked file wins: it is the more deliberate of the two. A link goes to
      // the service, which fetches the sheet -- this page never calls Google.
      const preview = picked
        ? await adapter.previewPriceImport(picked)
        : await adapter.previewPriceImportFromLink(requireSheetLink(link));
      status.textContent = preview.canCommit ? "پیش‌نمایش معتبر آماده است." : "پیش‌نمایش دارای خطاست.";
      renderPreview(preview);
    } catch (previewError) {
      error.textContent = previewError instanceof GoogleSheetError
        ? previewError.message
        : formatApiErrorMessage(previewError);
      status.textContent = "بررسی فایل انجام نشد.";
    } finally {
      input.disabled = false;
      sheetInput.disabled = false;
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

function priceHistoryColumns() {
  return [
    { key: "identity", label: "قلم هزینه", tier: IDENTITY },
    { key: "scope", label: "سطح", tier: PRIMARY },
    { key: "unitPrice", label: `قیمت واحد (${getDisplayCurrencyLabel()})`, tier: PRIMARY, cellClass: "numeric" },
    { key: "effectiveFrom", label: "تاریخ اعتبار", tier: SECONDARY, keepOnTablet: true },
    { key: "actor", label: "ثبت‌کننده", tier: SECONDARY },
    { key: "createdAt", label: "زمان ثبت", tier: SECONDARY },
  ];
}

function renderHistory(history, currentPrices, columns, visible, paging) {
  const resourceMap = new Map(currentPrices.map((item) => [item.resource.resourceId, item.resource]));
  return createPagedDataTable({
    name: "price-history",
    page: paging.page,
    pageSize: paging.pageSize,
    onChange: paging.onChange,
    paginationLabel: "صفحه‌بندی تاریخچه قیمت‌ها",
    className: "price-history-table",
    caption: "تاریخچه تغییرناپذیر قیمت‌ها",
    scrollLabel: "جدول تاریخچه قیمت‌ها",
    columns,
    rows: history,
    visible,
    cells: (price) => ({
      identity: resourceMap.get(price.resourceId)?.title ?? "قلم حذف‌شده",
      scope: SCOPE_LABELS[price.scope] ?? "سطح نامشخص",
      unitPrice: formatTomanFromIrr(price.unitPriceIRR, { withCurrency: false }),
      effectiveFrom: formatBusinessDate(price.effectiveFrom),
      actor: actorLabel(price.actorName, price.actorId),
      createdAt: formatSystemDateTime(price.createdAt),
    }),
  });
}

/* These two are rendered by the settings page but built here, so their column
   state lives with the module rather than being threaded through a caller that
   has no other reason to know about columns. One page, one of each table. */
const CONVERSION_COLUMNS = Object.freeze([
  { key: "identity", label: "تبدیل", tier: IDENTITY },
  { key: "dimension", label: "نوع واحد", tier: SECONDARY, keepOnTablet: true },
  { key: "organization", label: "ضریب پایه سازمان", tier: SECONDARY, cellClass: "numeric" },
  { key: "project", label: "تبدیل اختصاصی پروژه", tier: SECONDARY, cellClass: "numeric" },
  { key: "current", label: "ضریب جاری", tier: PRIMARY, cellClass: "numeric conversion-current" },
  { key: "scope", label: "مبنای جاری", tier: PRIMARY },
  { key: "effectiveDate", label: "تاریخ اعتبار", tier: SECONDARY },
]);
const visibleConversionColumns = defaultVisibleColumns(CONVERSION_COLUMNS);

export function renderCurrentConversions(items) {
  return createDataTableWithControl({
    name: "current-conversions",
    className: "current-conversions-table",
    caption: "فهرست تبدیل‌های واحد جاری",
    scrollLabel: "جدول تبدیل‌های واحد جاری",
    columns: CONVERSION_COLUMNS,
    visible: visibleConversionColumns,
    rows: items,
    cells: (item) => ({
      identity: `${formatUnitLabel(item.sourceUnit)} ← ${formatUnitLabel(item.targetUnit)}`,
      dimension: getUnitDefinition(item.sourceUnit)?.dimensionLabel ?? "نامشخص",
      organization: item.organizationConversion ? formatDisplayNumber(item.organizationConversion.factor) : "—",
      project: item.projectConversion ? formatDisplayNumber(item.projectConversion.factor) : "—",
      current: formatDisplayNumber(item.currentConversion.factor),
      scope: item.currentConversion?.projectId ? "اختصاصی پروژه" : "پایه سازمان",
      effectiveDate: formatBusinessDate(item.currentConversion.effectiveDate),
    }),
  });
}

const CONVERSION_HISTORY_COLUMNS = Object.freeze([
  { key: "identity", label: "واحد مبدأ", tier: IDENTITY },
  { key: "target", label: "واحد مقصد", tier: PRIMARY },
  { key: "dimension", label: "نوع واحد", tier: SECONDARY },
  { key: "factor", label: "ضریب تبدیل", tier: PRIMARY, cellClass: "numeric" },
  { key: "scope", label: "سطح", tier: SECONDARY, keepOnTablet: true },
  { key: "effectiveDate", label: "تاریخ اعتبار", tier: SECONDARY, keepOnTablet: true },
  { key: "actor", label: "ثبت‌کننده", tier: SECONDARY },
  { key: "createdAt", label: "زمان ثبت", tier: SECONDARY },
]);
const visibleConversionHistoryColumns = defaultVisibleColumns(CONVERSION_HISTORY_COLUMNS);

export function renderConversionHistory(history) {
  return createDataTableWithControl({
    name: "conversion-history",
    className: "conversion-history-table",
    caption: "تاریخچه نسخه‌های تبدیل واحد",
    scrollLabel: "جدول تاریخچه تبدیل واحد",
    columns: CONVERSION_HISTORY_COLUMNS,
    visible: visibleConversionHistoryColumns,
    rows: history,
    cells: (conversion) => ({
      identity: formatUnitLabel(conversion.sourceUnit),
      target: formatUnitLabel(conversion.targetUnit),
      dimension: getUnitDefinition(conversion.sourceUnit)?.dimensionLabel ?? "نامشخص",
      factor: formatDisplayNumber(conversion.factor),
      scope: conversion.projectId ? "اختصاصی پروژه" : "پایه سازمان",
      effectiveDate: formatBusinessDate(conversion.effectiveDate),
      actor: actorLabel(conversion.createdByName, conversion.createdBy),
      createdAt: formatSystemDateTime(conversion.createdAt),
    }),
  });
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
export function createPricesPage({ context, adapter, materialPricesAdapter = null,
                                  surface = SURFACES.OPERATIONS }) {
  const root = element("div", "prices-page");
  const readOnly = surface === SURFACES.REPORT;
  const canEdit = !readOnly && capabilitiesFor(context).writeFinance;
  /* A category above project level is checked in the service and never at the route, so a
     request cannot reveal it in advance. The dialog is told before it offers the levels. */
  const canManageSettings = capabilitiesFor(context).manageSettings;
  let state = createRequestState(REQUEST_STATUS.LOADING);
  /* One page number per table on this page. Held here rather than inside the
     component because `paint()` rebuilds the whole tree: a component that
     remembered its own page would lose it on every repaint, and one that both
     remembered would disagree. */
  /* Held beside the workspace rather than inside it: the workspace is replaced
     whole on every reload, and a history the reader asked to see should survive
     one -- adding a price version should not close the section again. */
  let priceHistory = null;
  let historyLoading = false;
  let historyError = null;

  async function loadHistory() {
    historyLoading = true;
    historyError = null;
    paint();
    try {
      priceHistory = await adapter.getPriceHistory();
    } catch (error) {
      historyError = error;
    }
    historyLoading = false;
    paint();
  }

  let historyPaging = { page: 1, pageSize: getRowsPerPage("price-history") };
  // Lives with the page: paint() rebuilds the tree, so a choice held inside a
  // render would last only until the next filter.
  const historyColumns = priceHistoryColumns();
  const visibleHistoryColumns = defaultVisibleColumns(historyColumns);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const workspace = await adapter.getPrices();
      /* No emptiness of its own any more. The page used to call itself empty when the
         project had no cost items, because the item roster was its content; the content is
         now the market sheet, which reports its own states -- not configured, not loaded
         yet, no rows in this category -- and none of those is the page being blank. */
      state = createRequestState(REQUEST_STATUS.SUCCESS, workspace);
      await loadMarketPrices();
    } catch (error) {
      state = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    return createFinancePageHeader(readOnly ? "جدول قیمت‌ها" : "قیمت روز", "feature-header", surface);
  }

  function openEditor(workspace) {
    const dialog = createPriceDialog(adapter, workspace.currentPrices, (next) => {
      state = createRequestState(REQUEST_STATUS.SUCCESS, next);
      paint();
    });
    root.append(dialog);
    showAccessibleDialog(dialog);
  }

  function renderContent(workspace) {
    const fragment = document.createDocumentFragment();
    const toolbar = element("div", "prices-toolbar");
    /* No sentence about scope precedence, and no CSV button. Both described the item
       roster that used to be here: the sentence explained which of an item's two price
       versions wins, and the export wrote exactly the rows that table was showing -- «what
       leaves is what is on screen» was its own rule, and there is no such screen now. The
       market table below is paged by the server, so exporting it means asking for every
       page; that is a feature to add deliberately, not a button to repoint quietly. */
    const toolbarActions = element("div", "prices-toolbar__actions");
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
      conversions.href = "#finance/settings";
      toolbarActions.append(conversions, importPrices, add);

      /* A price for something the worksheet will never carry.
         Offered only where the market table itself is — a host with no material-prices
         adapter has no table for the row to appear in, and a button that writes somewhere
         invisible is worse than no button. Saving reloads through `loadMarketPrices`, which
         fetches the rows AND the categories in one pass: a chip made here has to be on
         screen straight away, or the person who just made it will make it again. */
      if (materialPricesAdapter) {
        const manual = element("button", "button button--ghost", "ثبت دستی قیمت بازار");
        manual.type = "button";
        manual.dataset.action = "manual-market-price";
        manual.addEventListener("click", () => {
          const dialog = createManualMarketPriceDialog({
            categories: marketCategories,
            adapter: materialPricesAdapter,
            canManageSettings,
            onSaved: () => { marketPaging = { ...marketPaging, page: 1 }; loadMarketPrices(); },
            onClose: () => dialog.element.remove(),
          });
          dialog.open();
        });
        toolbarActions.append(manual);
      }
    }
    /* «قیمت روز اقلام» -- a row per cost item and its price version -- stood here.
       It listed ITEMS, not prices: every cost item got a row whether or not anybody had
       priced it, so most of the table read «ثبت نشده». And it could never hold what this
       page is for. The sheet writes no price version at all, so market prices lived in a
       SECOND table below it, and one page answered "what does this cost" twice, in two
       vocabularies and two kinds of identity -- a cost item «آرماتور» above, a supplier's
       listing «میلگرد ۱۶ · فولاد مبارکه» below.

       One table now, and it is the market one. A price entered by hand will join it once
       the service can take one: as a listing with a category, the way a sheet row is,
       so it lands under the same chips and needs no second vocabulary. Until then an
       unpriced item is reported where something can be done about it -- «ریز برآورد»
       states its status and carries the button that prices it. */
    /* Asked for, not assumed. The history is append-only and only grows, and
       nothing on this page reads it -- the current price and its sparkline both
       come from `/prices/current`. A reader who opened this page to check one
       item's price today should not wait for every price it ever had. */
    /* Not on the report surface. «گزارش مالی» answers what things cost now; every price
       an item ever had is a maintenance question, and the page that maintains prices is
       where it belongs. Nothing loads it there either -- the section is what carries the
       button that asks for it. */
    const history = element("section", "prices-section");
    history.append(
      element("h2", "", "تاریخچه قیمت‌ها"),
      element("p", "prices-section__hint", "تمام نسخه‌ها فقط‌خواندنی هستند و ثبت جدید، رکورد قبلی را تغییر نمی‌دهد."),
    );
    if (historyError) {
      const failed = element("div", "state-card state-card--danger", formatApiErrorMessage(historyError, "دریافت تاریخچه قیمت‌ها انجام نشد."));
      const again = element("button", "button button--ghost", "تلاش دوباره");
      again.type = "button";
      again.addEventListener("click", loadHistory);
      failed.append(again);
      history.append(failed);
    } else if (historyLoading) {
      history.append(element("div", "inline-notice", "در حال دریافت تاریخچه قیمت‌ها…"));
    } else if (priceHistory === null) {
      const ask = element("div", "prices-history-ask");
      const show = element("button", "button button--primary", "نمایش تاریخچه قیمت‌ها");
      show.type = "button";
      show.addEventListener("click", loadHistory);
      ask.append(show);
      history.append(ask);
    } else {
      history.append(renderHistory(priceHistory, workspace.currentPrices, historyColumns, visibleHistoryColumns, {
        ...historyPaging,
        onChange: (next) => { historyPaging = next; paint(); },
      }));
    }
    /* The material sheet's observations, below the Finance prices and never mixed into
       them. Asked for rather than assumed, exactly as the history above is: a project with
       no import configured has nothing to show here, and fetching hundreds of rows for a
       reader who came to check one Finance price would be rude.

       `materialPricesAdapter` is absent when the host has not wired it -- an older host,
       or the standalone preview -- and then the section says so. It is never replaced with
       sample rows. */
    const market = element("section", "prices-section");
    const marketTitle = element("h2", "", "قیمت روز بازار (برگه مصالح)");
    if (!materialPricesAdapter) {
      market.append(marketTitle,
        element("p", "inline-notice", "این بخش در این نسخه از میزبان در دسترس نیست."));
      fragment.append(toolbar, ...(readOnly ? [] : [history]), market);
      return fragment;
    }
    if (marketError) {
      const failed = element("div", "state-card state-card--danger",
        formatApiErrorMessage(marketError, "دریافت قیمت روز بازار انجام نشد."));
      const again = element("button", "button button--ghost", "تلاش دوباره");
      again.type = "button";
      again.addEventListener("click", loadMarketPrices);
      market.append(marketTitle, failed, again);
    } else if (marketLoading) {
      market.append(marketTitle,
        element("div", "inline-notice", "در حال دریافت قیمت روز بازار…"));
    } else if (marketPrices === null) {
      market.append(marketTitle,
        element("div", "inline-notice", "در حال آماده‌سازی قیمت‌های روز بازار…"));
    } else {
      fragment.append(toolbar, ...(readOnly ? [] : [history]),
                      renderMaterialPrices(marketPrices.items, {
        categories: marketCategories,
        selectedCategory: marketCategory,
        readOnly,
        priceHistories: marketPriceHistories,
        /* Back to the first page whenever the category changes. Staying on page four of
           «لوله» while switching to «نبشی» -- which has twelve products -- would ask the
           server for a page that does not exist and show an empty table for a category
           that is not empty. */
        onSelectCategory: (value) => {
          marketCategory = value;
          marketPaging = { ...marketPaging, page: 1 };
          loadMarketPrices();
        },
        paging: {
          page: marketPrices.page ?? marketPaging.page,
          pageSize: marketPrices.pageSize ?? marketPaging.pageSize,
          totalItems: marketPrices.totalItems ?? marketPrices.items.length,
          onChange: (next) => { marketPaging = next; loadMarketPrices(); },
        },
      }));
      return fragment;
    }
    fragment.append(toolbar, ...(readOnly ? [] : [history]), market);
    return fragment;
  }

  /* Held here for the same reason the paging numbers are: `paint()` rebuilds the whole
     tree, so anything a component remembered would be lost on every repaint. */
  let marketPrices = null;
  let marketCategories = [];
  let marketCategory = null;
  let marketLoading = false;
  let marketError = null;
  let marketPriceHistories = new Map();
  let marketHistoryRequest = 0;
  /* SERVER paging, not a slice of something already fetched. The sheet holds 992 pipes in
     one category alone; asking for all of them to show fifty is the request this avoids,
     and it is the whole reason the page state carries a page number at all. */
  let marketPaging = { page: 1, pageSize: 50 };

  async function loadMarketPriceHistories(rows, requestId) {
    const pending = [...(rows ?? [])];
    const histories = new Map();
    /* A full page may contain fifty listings. Six workers avoid a fifty-request burst,
       while each request transfers only the five points the sparkline can display. */
    const worker = async () => {
      while (pending.length) {
        const row = pending.shift();
        if (!row?.providerItemId) continue;
        try {
          const result = await materialPricesAdapter.listPriceHistory(
            row.providerItemId, { page: 1, pageSize: 5 });
          histories.set(row.providerItemId, result.items ?? []);
        } catch {
          /* A secondary visualization failing must not hide a valid current price. */
          histories.set(row.providerItemId, []);
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(6, pending.length) }, worker));
    if (requestId !== marketHistoryRequest) return;
    marketPriceHistories = histories;
    paint();
  }

  async function loadMarketPrices() {
    if (!materialPricesAdapter) return;
    const requestId = ++marketHistoryRequest;
    marketLoading = true;
    marketError = null;
    paint();
    try {
      /* `asOf` is today in Tehran, and that is what turns freshness on: without it the
         backend labels nothing stale, because a request that does not say which day it
         means cannot say a price is old. */
      const [page, categories] = await Promise.all([
        materialPricesAdapter.listCurrentPrices({
          category: marketCategory, asOf: getTehranTodayIso(),
          page: marketPaging.page, pageSize: marketPaging.pageSize,
        }),
        materialPricesAdapter.listCategories(),
      ]);
      marketPrices = page;
      marketCategories = categories;
      marketPriceHistories = new Map();
      /* Render current prices first; their small trends arrive independently. */
      void loadMarketPriceHistories(page.items, requestId);
    } catch (error) {
      marketError = error;
      /* The rows already on screen are kept. A failed refresh must not empty a table that
         was showing real prices a moment ago. */
    } finally {
      marketLoading = false;
      paint();
    }
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, onRetry: load }));
    const target = root.querySelector(".deep-link-target");
    if (target) queueMicrotask(() => {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.focus({ preventScroll: true });
    });
  }

  load();
  return root;
}
