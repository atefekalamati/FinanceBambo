import { createFinancePageHeader } from "../../shared/components/finance-page-header.js";
import { createPriceMappingPanel, statusChip } from "./price-mapping-panel.js";
import { createManualPriceDialog } from "./manual-price-dialog.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { SURFACES } from "../../core/config/routes.js";
import { downloadCsvFile } from "../../shared/exports/csv.js";
import { buildEstimateLinesCsv, estimateLinesFileName } from "./financial-items-csv.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { actorLabel } from "../../shared/formatters/actor.js";
import { displayCurrencyNote, formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { getRowsPerPage } from "../../shared/preferences/rows-per-page.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { getResourceTypeLabel, RESOURCE_TYPES } from "./financial-items-model.js";
import { validateActivity, validateEstimateLine, validateEstimateRevision, validateResource } from "./financial-items-validation.js";
import { describeImportPreview } from "../../shared/imports/import-preview-notice.js";
import { element } from "../../shared/dom/elements.js";
import { GoogleSheetError, requireSheetLink } from "../../shared/imports/google-sheet.js";
import { IDENTITY, PRIMARY, SECONDARY, createColumnControl, createDataTableWithControl, createPagedDataTable, defaultVisibleColumns }
  from "../../shared/components/data-table.js";
import { ABSENT, activityBlockStarts, activityLabel, assignmentCostOf, canonicalWbs, resourceLabel, resourceSourceLabel, scheduleCostOf, selectEstimateRows, selectVisibleResources, sortEstimateRows, sourceLabel, withheldRowsNotice } from "./financial-items-presentation.js";

function createTextField({ id, label, hint, inputMode = "text" }) {
  const wrapper = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const input = document.createElement("input");
  input.id = id;
  input.name = id;
  input.inputMode = inputMode;
  input.setAttribute("aria-describedby", `${id}-hint ${id}-error`);
  const hintNode = element("small", "form-hint", hint);
  hintNode.id = `${id}-hint`;
  const errorNode = element("small", "form-error");
  errorNode.id = `${id}-error`;
  errorNode.setAttribute("aria-live", "polite");
  wrapper.append(labelNode, input, hintNode, errorNode);
  return { wrapper, input, error: errorNode, label: labelNode, hint: hintNode };
}

function createSelectField({ id, label, options }) {
  const wrapper = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const select = document.createElement("select");
  select.id = id;
  select.name = id;
  const placeholder = element("option", "", "انتخاب کنید");
  placeholder.value = "";
  select.append(placeholder);
  options.forEach((option) => {
    const node = element("option", "", option.label);
    node.value = option.value;
    select.append(node);
  });
  select.setAttribute("aria-describedby", `${id}-error`);
  const errorNode = element("small", "form-error");
  errorNode.id = `${id}-error`;
  errorNode.setAttribute("aria-live", "polite");
  wrapper.append(labelNode, select, errorNode);
  return { wrapper, select, error: errorNode };
}

function setFieldError(control, errorNode, message) {
  errorNode.textContent = message;
  control.setAttribute("aria-invalid", String(Boolean(message)));
}

function createDialog(title) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog workspace-dialog";
  const heading = element("h2", "", title);
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن پنجره");
  close.addEventListener("click", () => dialog.close());
  const header = element("header", "workspace-dialog__head");
  header.append(heading, close);
  dialog.append(header);
  return dialog;
}

function replaceSelectOptions(select, options, selectedValue = "") {
  const placeholder = element("option", "", "انتخاب کنید");
  placeholder.value = "";
  select.replaceChildren(placeholder);
  options.forEach((option) => {
    const node = element("option", "", option.label);
    node.value = option.value;
    select.append(node);
  });
  select.value = selectedValue;
}

function createResourceDialog(adapter, workspace, onSaved) {
  const dialog = createDialog("ثبت قلم هزینه جدید");
  const form = element("form", "workspace-form");
  form.noValidate = true;
  const type = createSelectField({ id: "resourceType", label: "نوع قلم هزینه", options: RESOURCE_TYPES });
  const title = createTextField({ id: "resourceTitle", label: "عنوان قلم", hint: "عنوان قابل فهم برای کاربران مالی" });
  const code = createTextField({ id: "resourceCode", label: "کد قلم", hint: "کد پایدار برای جست‌وجو و ورود فایل" });
  const baseUnit = createSelectField({
    id: "resourceBaseUnit",
    label: "واحد پایه",
    options: (workspace.unitRegistry ?? []).map((unit) => ({ value: unit.code, label: `${unit.label} · ${unit.dimensionLabel}` })),
  });
  const unitHint = element("small", "form-hint", "بُعد اندازه‌گیری از واحد انتخاب‌شده و توسط سامانه تعیین می‌شود.");
  baseUnit.wrapper.append(unitHint);
  const notice = element("div", "inline-notice", "هزینه‌های عمومی پروژه مبلغ‌محور هستند و بدون واحد پایه ثبت می‌شوند.");
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت قلم هزینه");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(type.wrapper, title.wrapper, code.wrapper, baseUnit.wrapper, notice, actions);

  function syncGeneralCost() {
    const optional = type.select.value === "general_cost";
    baseUnit.select.disabled = optional;
    if (optional) baseUnit.select.value = "";
  }
  type.select.addEventListener("change", syncGeneralCost);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateResource({ type: type.select.value, title: title.input.value, code: code.input.value, baseUnit: baseUnit.select.value });
    setFieldError(type.select, type.error, validation.errors.type);
    setFieldError(title.input, title.error, validation.errors.title);
    setFieldError(code.input, code.error, validation.errors.code);
    setFieldError(baseUnit.select, baseUnit.error, validation.errors.baseUnit);
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      form.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    submit.disabled = true;
    status.textContent = "در حال ثبت قلم…";
    try {
      const workspace = await adapter.createResource(validation.values);
      dialog.close();
      form.reset();
      syncGeneralCost();
      onSaved(workspace);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
    }
  });
  dialog.append(form);
  return dialog;
}

function createActivityDialog(adapter, onSaved) {
  const dialog = createDialog("تعریف فعالیت جدید");
  const form = element("form", "workspace-form");
  form.noValidate = true;
  const title = createTextField({ id: "activityTitle", label: "عنوان فعالیت", hint: "عنوانی که در ساختار پروژه و خطوط متره نمایش داده می‌شود." });
  const wbsCode = createTextField({ id: "activityWbsCode", label: "کد ساختار شکست کار", hint: "اختیاری؛ مانند ۲.۱ یا ۳.۲" });
  const parentTask = createTextField({ id: "activityParentTask", label: "شناسه فعالیت والد", hint: "اختیاری؛ فقط اگر فعالیت باید زیرمجموعه یک فعالیت موجود باشد." });
  const notice = element("div", "inline-notice", "فعالیت در ساختار اصلی پروژه ثبت می‌شود و سپس در خط متره قابل انتخاب است.");
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت فعالیت");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(title.wrapper, wbsCode.wrapper, parentTask.wrapper, notice, actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateActivity({ title: title.input.value, wbsCode: wbsCode.input.value, parentTaskExternalId: parentTask.input.value });
    setFieldError(title.input, title.error, validation.errors.title);
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      title.input.focus();
      return;
    }
    submit.disabled = true;
    status.textContent = "در حال ثبت فعالیت…";
    try {
      const result = await adapter.createActivity(validation.values);
      dialog.close();
      onSaved(result);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
    }
  });
  dialog.append(form);
  return dialog;
}

function createEstimateLineDialog(adapter, workspace, onSaved) {
  const dialog = createDialog("ثبت خط مستقل متره");
  const form = element("form", "workspace-form");
  form.noValidate = true;
  const activity = createSelectField({
    id: "lineActivity",
    label: "فعالیت",
    options: workspace.activities.map((item) => ({ value: item.activityExternalId, label: `${item.wbsCode || "—"} · ${item.title}` })),
  });
  const resource = createSelectField({
    id: "lineResource",
    label: "قلم هزینه",
    options: workspace.resources.map((item) => ({ value: item.resourceId, label: `${item.code} · ${item.title}` })),
  });
  const addActivity = element("button", "button button--ghost line-reference-add", "تعریف فعالیت جدید");
  addActivity.type = "button";
  const activityHelp = element("small", "form-hint", "اگر فعالیت موردنظر در ساختار پروژه نیست، همین‌جا آن را تعریف کنید.");
  activity.wrapper.append(addActivity, activityHelp);
  const addResource = element("button", "button button--ghost line-reference-add", "تعریف قلم هزینه جدید");
  addResource.type = "button";
  addResource.setAttribute("aria-describedby", "lineResourceHelp");
  const resourceHelp = element("small", "form-hint", "اگر قلم موردنظر در فهرست نیست، آن را ثبت کنید و سپس برای همین خط انتخاب کنید.");
  resourceHelp.id = "lineResourceHelp";
  resource.wrapper.append(addResource, resourceHelp);
  const quantity = createTextField({ id: "lineOriginalQuantity", label: "مقدار برآورد اولیه", hint: "مقدار با واحد پایه قلم ثبت می‌شود.", inputMode: "decimal" });
  const unitPrice = createTextField({ id: "lineOriginalUnitPrice", label: `قیمت واحد اولیه (${getDisplayCurrencyLabel()})`, hint: "قیمتی که برآورد اولیه با آن تثبیت شده است.", inputMode: "decimal" });
  const relationNotice = element("div", "inline-notice", "هر فعالیت و قلم هزینه یک ردیف مستقل برآورد است؛ استفاده همان قلم در فعالیت دیگر ردیف جدا می‌سازد.");
  const activityNotice = element("div", "inline-notice", "فعالیت‌ها از ساختار پروژه BAMBO دریافت می‌شوند؛ فعالیت جدید نیز در همان ساختار ثبت می‌شود.");
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت خط متره");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(activity.wrapper, resource.wrapper, quantity.wrapper, unitPrice.wrapper, relationNotice, activityNotice, actions);

  addResource.addEventListener("click", () => {
    const previousIds = new Set(workspace.resources.map((item) => item.resourceId));
    const resourceDialog = createResourceDialog(adapter, workspace, (nextWorkspace) => {
      workspace = nextWorkspace;
      const created = workspace.resources.find((item) => !previousIds.has(item.resourceId));
      resource.select.replaceChildren();
      const placeholder = element("option", "", "انتخاب کنید");
      placeholder.value = "";
      resource.select.append(placeholder);
      workspace.resources.forEach((item) => {
        const option = element("option", "", `${item.code} · ${item.title}`);
        option.value = item.resourceId;
        resource.select.append(option);
      });
      resource.select.value = created?.resourceId ?? "";
      syncQuantityLabel();
    });
    dialog.after(resourceDialog);
    resourceDialog.addEventListener("close", () => resourceDialog.remove(), { once: true });
    showAccessibleDialog(resourceDialog);
  });

  addActivity.addEventListener("click", () => {
    const activityDialog = createActivityDialog(adapter, ({ created, workspace: nextWorkspace }) => {
      workspace = nextWorkspace;
      replaceSelectOptions(activity.select, workspace.activities.map((item) => ({
        value: item.activityExternalId,
        label: `${item.wbsCode || "—"} · ${item.title}`,
      })), created.activityExternalId);
    });
    dialog.after(activityDialog);
    activityDialog.addEventListener("close", () => activityDialog.remove(), { once: true });
    showAccessibleDialog(activityDialog);
  });

  function syncQuantityLabel() {
    const selected = workspace.resources.find((item) => item.resourceId === resource.select.value);
    const isGeneralCost = selected?.type === "general_cost";
    quantity.label.textContent = isGeneralCost ? `مبلغ برآورد اولیه (${getDisplayCurrencyLabel()})` : "مقدار برآورد اولیه";
    quantity.hint.textContent = isGeneralCost ? `مبلغ با واحد نمایشی انتخاب‌شده وارد می‌شود و مقدار رسمی Backend همچنان ${CURRENCY_LABELS.IRR} است.` : `مقدار با واحد پایه ${formatUnitLabel(selected?.baseUnit)} ثبت می‌شود.`;
    // A general-cost line is a single amount, so it has no unit price.
    unitPrice.wrapper.hidden = isGeneralCost;
    unitPrice.label.textContent = `قیمت واحد اولیه هر ${formatUnitLabel(selected?.baseUnit)} (${getDisplayCurrencyLabel()})`;
  }
  resource.select.addEventListener("change", syncQuantityLabel);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedResource = workspace.resources.find((item) => item.resourceId === resource.select.value);
    const inputValue = selectedResource?.type === "general_cost" ? tomanInputToIrr(quantity.input.value) : quantity.input.value;
    const isGeneralCost = selectedResource?.type === "general_cost";
    const validation = validateEstimateLine(
      {
        activityExternalId: activity.select.value,
        resourceId: resource.select.value,
        originalQuantity: inputValue,
        originalUnitPriceIRR: isGeneralCost ? null : tomanInputToIrr(unitPrice.input.value),
      },
      { isGeneralCost },
    );
    setFieldError(activity.select, activity.error, validation.errors.activityExternalId);
    setFieldError(resource.select, resource.error, validation.errors.resourceId);
    setFieldError(quantity.input, quantity.error, validation.errors.originalQuantity);
    setFieldError(unitPrice.input, unitPrice.error, validation.errors.originalUnitPriceIRR);
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      form.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    submit.disabled = true;
    status.textContent = "در حال ثبت خط متره…";
    try {
      const nextWorkspace = await adapter.createEstimateLine(validation.values);
      dialog.close();
      form.reset();
      onSaved(nextWorkspace);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
    }
  });
  dialog.append(form);
  return dialog;
}

function createEstimateImportDialog(adapter, onSaved) {
  const dialog = createDialog("ورود متره و برآورد");
  dialog.classList.add("import-dialog");

  const description = element("p", "import-dialog__description", "فایل اکسل ابتدا فقط بررسی می‌شود. تا زمانی که تمام ردیف‌ها معتبر نباشند، هیچ ردیف برآوردی ثبت نخواهد شد.");
  const form = element("form", "import-form");
  form.noValidate = true;
  const field = element("div", "form-field form-field--wide");
  const label = element("label", "form-label", "فایل اکسل برآورد");
  label.htmlFor = "estimateImportFile";
  const input = document.createElement("input");
  input.id = "estimateImportFile";
  input.name = "estimateImportFile";
  input.type = "file";
  input.accept = ".xlsx";
  input.setAttribute("aria-describedby", "estimateImportHint estimateImportError");
  const hint = element("small", "form-hint", "ستون‌ها: resourceCode، activityExternalId، assignmentExternalId، originalQuantity و source. ستون کم یا اضافه پذیرفته نمی‌شود و source باید excel_import باشد.");
  hint.id = "estimateImportHint";
  const error = element("small", "form-error");
  error.id = "estimateImportError";
  error.setAttribute("aria-live", "polite");
  field.append(label, input, hint, error);

  // The same import, from a link instead of a disk. What is sent to the server
  // is the same .xlsx either way -- only where the bytes came from differs.
  const sheetField = element("div", "form-field form-field--wide");
  const sheetLabel = element("label", "form-label", "یا نشانی گوگل شیت");
  sheetLabel.htmlFor = "estimateImportSheet";
  const sheetInput = element("input", "app-input");
  sheetInput.id = "estimateImportSheet";
  sheetInput.type = "url";
  sheetInput.placeholder = "نشانی برگه را از نوار آدرس مرورگر کپی کنید";
  sheetInput.setAttribute("aria-describedby", "estimateSheetHint");
  const sheetHint = element("small", "form-hint", "برگه باید روی «هر کسی که لینک را دارد» باشد. اگر نشانی را از روی تب موردنظر کپی کنید، همان تب خوانده می‌شود.");
  sheetHint.id = "estimateSheetHint";
  sheetField.append(sheetLabel, sheetInput, sheetHint);

  const previewButton = element("button", "button button--primary", "بررسی و نمایش پیش‌نمایش");
  previewButton.type = "submit";
  const formStatus = element("div", "form-status");
  formStatus.setAttribute("role", "status");
  formStatus.setAttribute("aria-live", "polite");
  const formActions = element("div", "form-actions");
  formActions.append(previewButton, formStatus);
  form.append(field, sheetField, formActions);

  const resultRegion = element("section", "import-result");
  resultRegion.setAttribute("aria-live", "polite");
  resultRegion.hidden = true;
  let currentPreview = null;

  function renderPreview(preview) {
    resultRegion.replaceChildren();
    resultRegion.hidden = false;

    const summary = element("div", "import-summary");
    const summaryTitle = element("div", "");
    summaryTitle.append(
      element("h3", "", "نتیجه بررسی فایل"),
      element("p", "", `${formatDisplayNumber(String(preview.totalRows))} ردیف بررسی شد.`),
    );
    const counters = element("div", "import-summary__counters");
    counters.append(
      element("span", "import-count import-count--valid", `${formatDisplayNumber(String(preview.validRows))} معتبر`),
      element("span", `import-count ${preview.invalidRows ? "import-count--invalid" : ""}`, `${formatDisplayNumber(String(preview.invalidRows))} خطادار`),
    );
    summary.append(summaryTitle, counters);

    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table import-preview-table");
    table.append(element("caption", "sr-only", "پیش‌نمایش ردیف‌های فایل برآورد"));
    const head = document.createElement("thead");
    const header = document.createElement("tr");
    ["ردیف", "فعالیت", "قلم هزینه", "مقدار برآورد اولیه", "واحد", "نتیجه بررسی"].forEach((title) => header.append(element("th", "", title)));
    head.append(header);
    const body = document.createElement("tbody");
    preview.rows.forEach((row) => {
      const record = document.createElement("tr");
      if (row.status === "invalid") record.className = "import-row--invalid";
      const activityCell = document.createElement("td");
      activityCell.append(element("strong", "", row.activityTitle || "—"), element("small", "table-subtext numeric", row.activityExternalId || "شناسه نامعتبر"));
      const resourceCell = document.createElement("td");
      resourceCell.append(element("strong", "", row.resourceTitle || "—"), element("small", "table-subtext numeric", row.resourceCode || "کد نامعتبر"));
      const resultCell = document.createElement("td");
      if (row.errors.length) {
        const list = element("ul", "import-errors");
        row.errors.forEach((message) => list.append(element("li", "", message)));
        resultCell.append(list);
      } else {
        resultCell.append(element("span", "import-row-status import-row-status--valid", "معتبر"));
      }
      record.append(
        element("td", "numeric", formatDisplayNumber(String(row.rowNumber))),
        activityCell,
        resourceCell,
        element("td", "numeric", formatDisplayNumber(row.value)),
        element("td", "", formatUnitLabel(row.unit)),
        resultCell,
      );
      body.append(record);
    });
    table.append(head, body);
    wrapper.append(table);

    const verdict = describeImportPreview(preview, {
      readyText: "تمام ردیف‌ها معتبرند و فایل آماده ثبت نهایی است.",
      invalidText: "فایل ثبت نشده است. خطاهای ردیفی را در فایل اصلاح و دوباره بارگذاری کنید.",
    });
    const notice = element(
      "div",
      verdict.tone === "ready" ? "inline-notice import-notice--valid" : "overrun-warning",
      verdict.text,
    );
    const commit = element("button", "button button--primary", "ثبت نهایی ردیف‌های معتبر");
    commit.type = "button";
    commit.disabled = !preview.canCommit;
    commit.addEventListener("click", () => {
      const confirmation = document.createElement("dialog");
      confirmation.className = "confirm-dialog";
      const title = element("h2", "", "تأیید ثبت نهایی برآورد");
      const message = element("p", "", `${formatDisplayNumber(String(preview.validRows))} ردیف برآورد با مقدار اولیه تغییرناپذیر ثبت می‌شود. آیا ادامه می‌دهید؟`);
      const cancel = element("button", "button button--ghost", "لغو");
      cancel.type = "button";
      const confirm = element("button", "button button--primary", "تأیید و ثبت نهایی");
      confirm.type = "button";
      const status = element("div", "form-status");
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      const actions = element("div", "dialog-actions");
      actions.append(cancel, confirm);
      confirmation.append(title, message, actions, status);
      cancel.addEventListener("click", () => confirmation.close());
      confirm.addEventListener("click", async () => {
        confirm.disabled = true;
        cancel.disabled = true;
        status.textContent = "در حال ثبت نهایی…";
        try {
          const result = await adapter.commitEstimateImport({ previewId: preview.previewId });
          confirmation.close();
          dialog.close();
          onSaved(result.workspace, result.importedCount);
        } catch (commitError) {
          status.textContent = formatApiErrorMessage(commitError);
        } finally {
          confirm.disabled = false;
          cancel.disabled = false;
        }
      });
      dialog.after(confirmation);
      confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
      showAccessibleDialog(confirmation);
    });

    const actions = element("div", "import-result__actions");
    actions.append(commit);
    resultRegion.append(summary, wrapper, notice, actions);
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
    previewButton.disabled = true;
    input.disabled = true;
    sheetInput.disabled = true;
    formStatus.textContent = link && !picked ? "در حال دریافت برگه از گوگل…" : "در حال بررسی فایل…";
    resultRegion.hidden = true;
    try {
      // A picked file wins: it is the more deliberate of the two. A link goes to
      // the service, which fetches the sheet -- this page never calls Google.
      currentPreview = picked
        ? await adapter.previewEstimateImport(picked)
        : await adapter.previewEstimateImportFromLink(requireSheetLink(link));
      formStatus.textContent = currentPreview.canCommit ? "پیش‌نمایش معتبر آماده است." : "پیش‌نمایش دارای خطاست.";
      renderPreview(currentPreview);
    } catch (previewError) {
      currentPreview = null;
      error.textContent = previewError instanceof GoogleSheetError
        ? previewError.message
        : formatApiErrorMessage(previewError);
      formStatus.textContent = "بررسی فایل انجام نشد.";
    } finally {
      previewButton.disabled = false;
      input.disabled = false;
      sheetInput.disabled = false;
    }
  });

  dialog.append(description, form, resultRegion);
  return dialog;
}

function createRevisionDialog(adapter, line, resource, onSaved) {
  const isGeneralCost = resource.type === "general_cost";
  const originalValue = line.originalQuantity ?? line.originalAmount;
  const currentValue = line.revisedQuantity ?? line.revisedAmount;
  const unit = isGeneralCost ? getDisplayCurrencyLabel() : formatUnitLabel(resource.baseUnit);
  const dialog = createDialog("ثبت اصلاح مقدار برآورد");
  const summary = element("div", "revision-summary");
  const original = element("article", "revision-summary__item");
  original.append(element("span", "", "مقدار برآورد اولیه قفل‌شده"), element("strong", "numeric", isGeneralCost ? formatTomanFromIrr(originalValue, { withCurrency: false }) : formatDisplayNumber(originalValue)), element("small", "numeric", unit));
  const current = element("article", "revision-summary__item");
  current.append(element("span", "", "آخرین مقدار برآورد"), element("strong", "numeric", isGeneralCost ? formatTomanFromIrr(currentValue, { withCurrency: false }) : formatDisplayNumber(currentValue)), element("small", "numeric", `اصلاح ${line.revision}`));
  summary.append(original, current);

  const form = element("form", "workspace-form revision-form");
  form.noValidate = true;
  const revised = createTextField({
    id: `revisedValue-${line.lineId}`,
    label: isGeneralCost ? `آخرین مبلغ برآورد (${getDisplayCurrencyLabel()})` : `آخرین مقدار برآورد (${unit})`,
    hint: "مقدار برآورد اولیه تغییر نمی‌کند؛ فقط یک اصلاح جدید ثبت می‌شود.",
    inputMode: "decimal",
  });
  revised.input.value = isGeneralCost ? (formatTomanFromIrr(currentValue, { withCurrency: false }).replaceAll("٬", "").replace("٫", ".")) : currentValue;
  const reasonField = element("div", "form-field form-field--wide");
  const reasonLabel = element("label", "form-label", "دلیل اصلاح");
  reasonLabel.htmlFor = `revisionReason-${line.lineId}`;
  const reason = document.createElement("textarea");
  reason.id = `revisionReason-${line.lineId}`;
  reason.rows = 3;
  reason.placeholder = "برای مثال: اصلاح متره براساس نقشه اجرایی مصوب";
  reason.setAttribute("aria-describedby", `revisionReasonError-${line.lineId}`);
  const reasonError = element("small", "form-error");
  reasonError.id = `revisionReasonError-${line.lineId}`;
  reasonError.setAttribute("aria-live", "polite");
  reasonField.append(reasonLabel, reason, reasonError);
  const warning = element("div", "overrun-warning");
  warning.hidden = true;
  warning.setAttribute("role", "status");
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "تأیید و ثبت اصلاح");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(revised.wrapper, reasonField, warning, actions);

  function syncWarning() {
    const validation = validateEstimateRevision({ revisedValue: isGeneralCost ? tomanInputToIrr(revised.input.value) : revised.input.value, reason: "valid reason" }, { isGeneralCost });
    const isOverrun = validation.values.revisedValue && validation.errors.revisedValue === "" && compareDecimalStrings(validation.values.revisedValue, originalValue) > 0;
    warning.hidden = !isOverrun;
    warning.textContent = isOverrun ? "آخرین مقدار برآورد از مقدار اولیه بیشتر است. ثبت مسدود نمی‌شود، اما دلیل آن در تاریخچه تغییرات حفظ خواهد شد." : "";
  }
  revised.input.addEventListener("input", syncWarning);
  syncWarning();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateEstimateRevision({ revisedValue: isGeneralCost ? tomanInputToIrr(revised.input.value) : revised.input.value, reason: reason.value }, { isGeneralCost });
    if (validation.valid && compareDecimalStrings(validation.values.revisedValue, currentValue) === 0) {
      validation.valid = false;
      validation.errors.revisedValue = "مقدار جدید باید با مقدار فعلی متفاوت باشد.";
    }
    setFieldError(revised.input, revised.error, validation.errors.revisedValue);
    setFieldError(reason, reasonError, validation.errors.reason);
    if (!validation.valid) {
      status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
      form.querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    submit.disabled = true;
    cancel.disabled = true;
    status.textContent = "در حال ثبت اصلاح…";
    try {
      const workspace = await adapter.reviseEstimateLine({
        lineId: line.lineId,
        revisedValue: validation.values.revisedValue,
        reason: validation.values.reason,
        expectedRevision: line.revision,
      });
      dialog.close();
      onSaved(workspace);
    } catch (error) {
      status.textContent = formatApiErrorMessage(error);
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });

  dialog.append(summary, form);
  return dialog;
}

function createRevisionHistoryDialog(line, resource) {
  const dialog = createDialog("تاریخچه اصلاحات ردیف برآورد");
  const identity = element("div", "revision-identity");
  identity.append(element("strong", "", `${activityLabel(line)} · ${resourceLabel(resource)}`),
                  element("small", "numeric", `${canonicalWbs(line)} · ${resource?.code ?? ABSENT}`));
  dialog.append(identity);
  if (!line.revisions.length) {
    dialog.append(element("div", "inline-notice", "برای این ردیف هنوز اصلاحی ثبت نشده و آخرین مقدار برآورد با مقدار اولیه برابر است."));
    return dialog;
  }

  const wrapper = element("div", "revision-list");
  line.revisions.forEach((revision) => {
    const item = element("article", `revision-record ${revision.isOverrun ? "revision-record--overrun" : ""}`);
    const head = element("div", "revision-record__head");
    head.append(element("strong", "", `اصلاح ${revision.revisionNumber}`), element("time", "", formatSystemDateTime(revision.occurredAt)));
    const values = element("div", "revision-record__values");
    values.append(element("span", "", resource.type === "general_cost" ? `از ${formatTomanFromIrr(revision.previousValue)} به ${formatTomanFromIrr(revision.newValue)}` : `از ${formatDisplayNumber(revision.previousValue)} به ${formatDisplayNumber(revision.newValue)}`), element("small", "", resource.type === "general_cost" ? getDisplayCurrencyLabel() : formatUnitLabel(resource.baseUnit)));
    item.append(head, values, element("p", "", revision.reason), element("small", "revision-record__actor", actorLabel(revision.actorName, revision.actorId)));
    if (revision.isOverrun) item.append(element("span", "overrun-badge", "بیشتر از برآورد اولیه"));
    wrapper.append(item);
  });
  dialog.append(wrapper);
  return dialog;
}

/* The code is the identity: it is what an item is referred to by everywhere else
   in the module, and the title is what it is called. */
const RESOURCE_COLUMNS = Object.freeze([
  { key: "identity", label: "کد", tier: IDENTITY },
  { key: "title", label: "عنوان", tier: PRIMARY },
  { key: "type", label: "نوع", tier: PRIMARY, cellClass: "items-table__type" },
  { key: "unit", label: "واحد پایه", tier: SECONDARY, keepOnTablet: true, cellClass: "numeric" },
  { key: "source", label: "منبع ورود", tier: SECONDARY },
]);
const visibleResourceColumns = defaultVisibleColumns(RESOURCE_COLUMNS);

function renderResourceTable(resources, withheld = null, paging) {
  const fragment = document.createDocumentFragment();
  if (withheld) fragment.append(element("p", "table-note", withheld));
  fragment.append(createDataTableWithControl({
    name: "resources",
    page: paging.page,
    pageSize: paging.pageSize,
    onChange: paging.onChange,
    paginationLabel: "صفحه‌بندی اقلام مالی",
    className: "items-table",
    caption: "فهرست اقلام مالی",
    scrollLabel: "جدول اقلام مالی پروژه",
    columns: RESOURCE_COLUMNS,
    visible: visibleResourceColumns,
    rows: resources,
    cells: (resource) => ({
      identity: resource.code,
      title: resource.title,
      type: element("span", `type-badge type-badge--${resource.type}`, getResourceTypeLabel(resource.type)),
      unit: formatUnitLabel(resource.baseUnit),
      source: resourceSourceLabel(resource),
    }),
  }));
  return fragment;
}

/* The columns of ریز برآورد.
 *
 * THE TWO UNIT COLUMNS ARE THE POINT
 * «واحد فایل MSP» is what the schedule measures this line in; «واحد شیت قیمت» is what the
 * market quotes its price in. They are two different statements and the gap between them
 * is exactly what stops a daily price from being computed -- so they sit side by side,
 * and the cell that reconciles them is the one between.
 *
 * ONE QUANTITY COLUMN, NOT TWO
 * The original and the revised used to be separate columns, which spent two columns saying
 * the same thing on every row that has never been revised -- which today is all 835 of
 * them. One column now carries the latest figure and marks it when it is a revision.
 *
 * THREE MONEY COLUMNS AND THEY ARE THREE ON PURPOSE: «هزینه برآورد» is what the schedule
 * says this assignment costs, «قیمت اولیه» is the unit price it was estimated at and never
 * changes, «قیمت روز» is today's. None is computed from another and an empty one means
 * unknown, not zero. */
function estimateLineColumns() {
  return [
    // The pinned column answers "what is this row": the activity on a summary
    // row, the cost item on one of its items. They never appear together -- a
    // summary row has no item and an item row has no activity -- so one column
    // holds both and «قلم هزینه» is not a column of its own any more.
    { key: "identity", label: "فعالیت و قلم هزینه", tier: IDENTITY },
    { key: "mspUnit", label: "واحد فایل MSP", tier: SECONDARY, cellClass: "numeric" },
    { key: "sheetUnit", label: "واحد شیت قیمت", tier: SECONDARY, cellClass: "numeric" },
    { key: "revisedQuantity", label: "مقدار برآورد", tier: PRIMARY, cellClass: "numeric" },
    { key: "scheduleCost", label: "هزینه برآورد", tier: SECONDARY, keepOnTablet: true, cellClass: "numeric" },
    { key: "originalPrice", label: "قیمت اولیه", tier: SECONDARY, cellClass: "numeric" },
    { key: "currentPrice", label: "قیمت روز", tier: PRIMARY, cellClass: "numeric" },
    { key: "source", label: "منبع", tier: SECONDARY },
    { key: "actions", label: "عملیات", tier: SECONDARY, keepOnTablet: true, cellClass: "line-actions" },
  ];
}

/* The unit the SCHEDULE measures this line in.
 *
 * Not the Finance resource's base unit, which is what this column used to show: that is a
 * property of the cost item in the catalogue, while this is what the MS Project file says
 * about THIS assignment. They can differ, and when they do it is the file's that the
 * daily-price arithmetic has to land in.
 *
 * Empty on two rows in three, and not because the import failed. MS Project keeps the
 * resource's initials in the field this comes from -- a single Persian letter for most
 * rows of a real schedule -- and the importer records a unit only where the text is
 * actually one. So "no unit" here is a fact about the file, and the cell says so rather
 * than showing a dash that reads as a rendering fault. */
function mspUnitCell(line, resource, isGeneralCost) {
  if (isGeneralCost) return getDisplayCurrencyLabel();
  const unit = line.mppUnit ?? null;
  if (unit) return formatUnitLabel(unit);
  const cell = document.createDocumentFragment();
  cell.append(element("span", "missing-value", "در فایل ثبت نشده"));
  /* The catalogue's own unit, offered as context rather than as a substitute: somebody
     choosing the official unit needs to know what the item is normally measured in. */
  if (resource?.baseUnit) {
    cell.append(element("span", "cell-secondary",
      `واحد قلم: ${formatUnitLabel(resource.baseUnit)}`));
  }
  return cell;
}

/* The unit the PRICE SHEET quotes this product in, and the way to reconcile it.
 *
 * Known only once the line is linked to a listing -- before that there is no sheet price
 * and so no sheet unit. Today the sheet states one for rebar and for nothing else, so most
 * linked rows land on «واحد قیمت مبدأ مشخص نیست»; that is the sheet's gap, not this page's,
 * and it is named plainly so nobody looks for the fault here.
 *
 * When both units are known and do not meet, the button to define the crossing is IN THIS
 * CELL. It is where the person is looking when they find out, and sending them to a
 * settings page means asking them to carry two unit codes and a product in their head. */
function sheetUnitCell(line, priced, isGeneralCost, { canEdit, onMapPrice, resource }) {
  if (isGeneralCost) return ABSENT;
  if (!priced || !priced.componentCount) {
    return element("span", "missing-value", "هنوز به قیمت روز وصل نشده");
  }
  const cell = document.createDocumentFragment();
  if (priced.sourcePriceUnit) cell.append(element("span", "", formatUnitLabel(priced.sourcePriceUnit)));

  /* Only the statuses a unit decision can answer. «قیمت روز معتبر نیست» is a different
     problem and a conversion rule would not fix it, so no button is offered there. */
  const UNIT_TROUBLE = new Set(["unknown_source_unit", "needs_factor", "needs_unit"]);
  if (UNIT_TROUBLE.has(priced.status)) {
    cell.append(element("span", "cell-secondary", priced.statusLabel ?? ""));
    if (canEdit && onMapPrice) {
      const fix = element("button", "table-action table-action--map-price", "تبدیل واحد");
      fix.type = "button";
      fix.dataset.action = "fix-unit";
      fix.addEventListener("click", () => onMapPrice(line, resource));
      cell.append(fix);
    }
  }
  return cell;
}

/* What «قیمت روز» shows once an item is linked to a market listing.
 *
 * What this line costs per day at today's prices: the SUM of the materials somebody said
 * it consumes. «کانال‌کنی» is 500 cubic metres of trenching and consumes rebar and pipe and
 * brick; the cell shows what all of them come to, not one of them.
 *
 * An unresolved row shows the reason and NO number. That is the whole point: «نیازمند
 * ضریب تبدیل» and «۰» look nothing alike to a reader, and only one of them is true.
 *
 * A PARTLY priced row shows both -- the total of what resolved AND how much of the list it
 * came from. The total is real and incomplete, and a sum presented without that count
 * looks finished, which is the more dangerous of the two mistakes. */
function dailyPriceCell(line, priced, isGeneralCost, { canEdit, onManualPrice, resource } = {}) {
  const fallback = formatTomanFromIrr(line.currentUnitPriceIRR, { withCurrency: false });
  if (!priced || isGeneralCost) return fallback;
  const cell = document.createDocumentFragment();
  /* The service's own label for an unlinked row still says «افزودن مصالح», from the days
     when a line held several materials. One row of one table must not carry two
     vocabularies for the same state, so the wording is corrected here until the service
     changes it. Everything else passes through as it arrives. */
  const UNLINKED = "needs_components";
  if (priced.status !== "ready") {
    cell.append(statusChip(priced.status,
      priced.status === UNLINKED ? "وصل نشده" : priced.statusLabel));
  }
  if (priced.dailyItemCostIRR !== null) {
    cell.append(element("span", "",
      formatTomanFromIrr(priced.dailyItemCostIRR, { withCurrency: false })));
    if (priced.unresolvedComponentCount) {
      cell.append(element("span", "cell-secondary",
        `${formatDisplayNumber(priced.readyComponentCount)} از ${formatDisplayNumber(priced.componentCount)} قلم مصالح`));
    }
  } else if (line.currentUnitPriceIRR !== null && line.currentUnitPriceIRR !== undefined) {
    /* The line's own Finance price still shows when it has one: the daily-price link is
       unresolved, which says nothing about the price somebody entered by hand. */
    cell.append(element("span", "cell-secondary", fallback));
  }
  cell.append(manualPriceButton(line, isGeneralCost, { canEdit, onManualPrice, resource }));
  return cell;
}

/* Entering the price by hand, on every row.
 *
 * Some items will never be on the sheet. «برچیدن جدول» is 3,538 metres of demolition and
 * no supplier quotes it; waiting for the market to cover it would leave that row, and the
 * report total above it, blank for good. So the admin can state the rate themselves, and
 * the row stops being a hole in the customer's report.
 *
 * Offered whether or not the row is linked, because both states need it: an unlinked row
 * has nothing else, and a linked one may still need correcting. The label says which of
 * the two is happening, so pressing it is never a guess. */
function manualPriceButton(line, isGeneralCost, { canEdit, onManualPrice, resource } = {}) {
  if (isGeneralCost || !canEdit || !onManualPrice) return document.createDocumentFragment();
  const hasManual = line.currentUnitPriceIRR !== null && line.currentUnitPriceIRR !== undefined;
  const button = element("button", "table-action table-action--manual-price",
                         hasManual ? "ویرایش قیمت روز" : "ثبت دستی قیمت روز");
  button.type = "button";
  button.dataset.action = "manual-price";
  button.addEventListener("click", () => onManualPrice(line, resource));
  return button;
}

function renderEstimateLineTable(lines, resources, { canEdit, onRevise, onHistory, withheld = null, focusResourceId = "", focusEstimateLineId = "", columns, visible, paging, priceStatuses = new Map(), onMapPrice = null, onManualPrice = null }) {
  const resourceMap = new Map(resources.map((resource) => [resource.resourceId, resource]));
  const fragment = document.createDocumentFragment();
  if (withheld) fragment.append(element("p", "table-note", withheld));
  // «هزینه MSP فعالیت», «قیمت اولیه» and «قیمت روز» are formatted without a currency word
  // so the column stays a column of numbers. Said once here instead, in the note style the
  // table already uses, and read from the display-currency preference rather than typed --
  // the reader can switch to rials and this follows.
  fragment.append(element("p", "table-note", displayCurrencyNote()));

  fragment.append(createPagedDataTable({
    name: "estimate-lines",
    page: paging.page,
    pageSize: paging.pageSize,
    onChange: paging.onChange,
    paginationLabel: "صفحه‌بندی ریز برآورد",
    className: "estimate-lines-table",
    caption: "ریز برآورد پروژه",
    scrollLabel: "جدول ریز برآورد پروژه",
    columns,
    rows: lines,
    visible,
    rowAttributes: (line) => {
      const isTarget = focusEstimateLineId
        ? line.lineId === focusEstimateLineId
        : Boolean(focusResourceId && line.resourceId === focusResourceId);
      return isTarget ? { className: "deep-link-target", tabIndex: -1 } : null;
    },
    // One row per activity, its items folded underneath. Read flat, the activity
    // was named once and then five rows said nothing about what they belonged to.
    group: {
      key: (line) => canonicalWbs(line) + "|" + activityLabel(line),
      countLabel: "قلم",
      showColumnLabelsWhenOpen: true,
      cells: (rows) => {
        const first = rows[0];
        const name = document.createDocumentFragment();
        name.append(element("strong", "", activityLabel(first)),
                    element("small", "table-subtext numeric", canonicalWbs(first)));
        return {
          identity: name,
          // The schedule's figure belongs to the activity, so it is written on
          // the activity's own row rather than repeated down its items.
          scheduleCost: formatTomanFromIrr(scheduleCostOf(first), { withCurrency: false }),
        };
      },
    },
    cells: (line) => {
      const resource = resourceMap.get(line.resourceId);
      const isGeneralCost = resource?.type === "general_cost";
      const original = isGeneralCost ? line.originalAmount : line.originalQuantity;
      const revised = isGeneralCost ? line.revisedAmount : line.revisedQuantity;

      // Was the «قلم هزینه» cell; it is the identity of an item row now.
      const identity = document.createDocumentFragment();
      identity.append(element("strong", "", resourceLabel(resource)),
                      element("small", "table-subtext numeric", resource?.code ?? ABSENT));

      const revisedCell = element("span", original !== revised ? "value-changed" : "",
        isGeneralCost ? formatTomanFromIrr(revised, { withCurrency: false }) : formatDisplayNumber(revised));
      if (original !== revised) revisedCell.append(element("span", "change-badge", "اصلاح‌شده"));

      const actions = document.createDocumentFragment();
      const history = element("button", "table-action", "تاریخچه");
      history.type = "button";
      history.addEventListener("click", () => onHistory(line, resource));
      actions.append(history);
      if (canEdit) {
        const revise = element("button", "table-action table-action--primary", "اصلاح مقدار");
        revise.type = "button";
        revise.addEventListener("click", () => onRevise(line, resource));
        actions.append(revise);
      }

      /* The daily-price link. Four columns gain content from it and none is added: the
         sheet's unit in «واحد شیت قیمت», this line's daily cost in «قیمت روز», the chosen
         listing in «منبع», and the action here. The table's shape is what people navigate
         by. */
      const priced = priceStatuses.get(line.lineId) ?? null;
      if (onMapPrice && !isGeneralCost) {
        const label = priced?.componentCount ? "تغییر محصول" : "اتصال به قیمت روز";
        const map = element("button", "table-action table-action--map-price", label);
        map.type = "button";
        map.dataset.action = "map-price";
        map.addEventListener("click", () => onMapPrice(line, resource));
        actions.append(map);
      }

      return {
        identity,
        mspUnit: mspUnitCell(line, resource, isGeneralCost),
        sheetUnit: sheetUnitCell(line, priced, isGeneralCost, { canEdit, onMapPrice, resource }),
        revisedQuantity: revisedCell,
        scheduleCost: formatTomanFromIrr(assignmentCostOf(line), { withCurrency: false }),
        originalPrice: formatTomanFromIrr(line.originalUnitPriceIRR, { withCurrency: false }),
        currentPrice: dailyPriceCell(line, priced, isGeneralCost,
                                     { canEdit, onManualPrice, resource }),
        /* One material names its product; several say how many there are. Listing three
           product names in a table cell is unreadable, and naming only the first would be
           a lie about what priced the row. */
        source: priced?.sourceSummary
          ?? (priced?.productName
            ? `${priced.providerName ?? "—"} · ${priced.productName}`
            : sourceLabel(line)),
        actions,
      };
    },
  }));
  return fragment;
}

/**
 * Items and the estimate, on both surfaces.
 *
 * On امور مالی it is the working page: new items, new metre lines, bulk entry,
 * quantity revisions. On گزارش مالی it is the same table with nothing to press,
 * and that follows from the route rather than from the account — an
 * administrator reading the report gets the read-only table too. One mode per
 * route is a thing you can reason about; one mode per account is not.
 */
export function createFinancialItemsPage({ context, adapter, priceMappingAdapter = null, pricesAdapter = null, surface = SURFACES.OPERATIONS, focusResourceId = "", focusEstimateLineId = "" }) {
  const root = element("div", "financial-items-page");
  const readOnly = surface === SURFACES.REPORT;
  /* Which market listing prices each line, and what that makes it cost today.
     Kept beside the workspace rather than inside it: the estimate is one module's data
     and the daily price is another's, and a page that merged them would have to reload
     both to refresh either. Empty until it arrives, and a row with no entry simply shows
     what it showed before -- the table must render before this call returns. */
  let priceStatuses = new Map();
  /* The price panel while it is open. Held because `paint()` replaces the page's children
     and the panel is one of them: the daily-price statuses refresh after every material is
     saved, so a repaint took the open panel out of the document halfway through a list.
     The panel disappeared after the first material, and the next click landed on a row
     action instead of on the panel -- which is how a material was entered against a line
     nobody had opened. */
  let openPricePanel = null;
  /* One page number per table. Held here rather than inside the component
     because `paint()` rebuilds the whole tree: a component that remembered its
     own page would lose it on every repaint. */
  let resourcePaging = { page: 1, pageSize: getRowsPerPage("resources") };
  let linePaging = { page: 1, pageSize: getRowsPerPage("estimate-lines") };
  const canEdit = !readOnly && capabilitiesFor(context).writeFinance;
  let state = createRequestState(REQUEST_STATUS.LOADING);
  // Lives with the page: paint() rebuilds the tree, so a choice held inside a
  // render would last only until the next one.
  const lineColumns = estimateLineColumns();
  const visibleLineColumns = defaultVisibleColumns(lineColumns);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const workspace = await adapter.getWorkspace();
      state = createRequestState(workspace.resources.length || workspace.estimateLines.length ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, workspace);
    } catch (error) {
      state = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
    loadPriceStatuses();
  }

  /* Fetched AFTER the table is on screen, and never awaited by `load`.
     The estimate is the page; the daily-price link is an annotation on it. If this call
     is slow or fails, the estimate still renders exactly as it did before the feature
     existed -- a failure here must not be able to empty the table. */
  async function loadPriceStatuses() {
    if (!priceMappingAdapter) return;
    try {
      const rows = await priceMappingAdapter.statuses();
      priceStatuses = new Map(rows.map((row) => [row.estimateLineId, row]));
      paint();
    } catch (error) {
      /* Left as it was. The row then shows its own price and no mapping status, which is
         the truthful state: we do not know, rather than nothing is mapped. */
    }
  }

  function renderHeader() {
    return createFinancePageHeader(readOnly ? "جدول اقلام و برآورد" : "اقلام و برآورد", "feature-header", surface);
  }

  function renderEmpty() {
    const card = element("section", "state-card items-empty");
    card.append(element("h2", "", "هنوز قلم هزینه‌ای ثبت نشده است"), element("p", "", canEdit ? "اولین قلم هزینه را ثبت کنید و سپس آن را به یک فعالیت متصل کنید." : "برای این پروژه هنوز اقلام و برآوردی قابل نمایش نیست."));
    if (canEdit) {
      const button = element("button", "button button--primary", "ثبت اولین قلم");
      button.type = "button";
      button.addEventListener("click", async () => {
        const workspace = await adapter.getWorkspace();
        const dialog = createResourceDialog(adapter, workspace, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      });
      card.append(button);
    }
    return card;
  }

  function renderContent(fullWorkspace) {
    // Everything below reads the presented workspace, so the table, the counts,
    // the pickers and the export agree on one set of rows. `fullWorkspace` still
    // holds the withheld rows; they are hidden here, not removed from anywhere.
    const visibleResources = selectVisibleResources(fullWorkspace.resources);
    const visibleLines = selectEstimateRows(fullWorkspace.estimateLines, fullWorkspace.resources);
    // Sorted once, here, so the table and the export are the same document in
    // two formats rather than two orderings of one dataset.
    const orderedLines = sortEstimateRows(visibleLines.rows, fullWorkspace.resources);
    const workspace = { ...fullWorkspace, resources: visibleResources.rows, estimateLines: orderedLines };
    const linesWithheld = withheldRowsNotice(visibleLines);
    const resourcesWithheld = withheldRowsNotice({ hiddenLegacyCount: visibleResources.hiddenLegacyCount });
    const fragment = document.createDocumentFragment();
    const counts = new Map(RESOURCE_TYPES.map((type) => [type.value, 0]));
    workspace.resources.forEach((resource) => counts.set(resource.type, (counts.get(resource.type) ?? 0) + 1));
    const stats = element("section", "item-type-grid");
    RESOURCE_TYPES.forEach((type) => {
      const card = element("article", `item-type-card item-type-card--${type.value}`);
      card.append(element("span", "", type.label), element("strong", "numeric", formatDisplayNumber(String(counts.get(type.value) ?? 0))), element("small", "", "قلم ثبت‌شده"));
      stats.append(card);
    });

    const lineActions = element("div", "items-section__actions");
    // Reading the estimate and taking a copy of it are the same act; only
    // changing it is privileged.
    const exportCsv = element("button", "button button--ghost", "خروجی اکسل");
    exportCsv.type = "button";
    exportCsv.addEventListener("click", () => {
      downloadCsvFile(
        buildEstimateLinesCsv({ lines: workspace.estimateLines, resources: workspace.resources }),
        estimateLinesFileName({ projectCode: context.projectCode }),
      );
    });
    lineActions.append(exportCsv);
    if (canEdit) {
      const addLine = element("button", "button button--primary", "خط متره جدید");
      addLine.type = "button";
      const importEstimate = element("button", "button button--ghost", "ورود گروهی برآورد");
      importEstimate.type = "button";
      addLine.addEventListener("click", () => {
        const dialog = createEstimateLineDialog(adapter, workspace, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      });
      importEstimate.addEventListener("click", () => {
        const dialog = createEstimateImportDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      });
      lineActions.append(addLine, importEstimate);
    }

    const resourcesSection = element("details", "items-section resources-disclosure");
    const resourceHead = element("summary", "items-section__head resources-disclosure__summary");
    const resourceMeta = element("div", "resources-disclosure__meta");
    if (canEdit) {
      const addResource = element("button", "button button--ghost resources-disclosure__add", "قلم جدید");
      addResource.type = "button";
      addResource.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const dialog = createResourceDialog(adapter, workspace, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      });
      resourceMeta.append(addResource);
    }
    resourceHead.append(element("div", "", ""), resourceMeta);
    resourceHead.firstElementChild.append(element("h2", "", "فهرست اقلام پروژه"), element("p", "", "فهرست چهار نوع قلم هزینه و واحد پایه هر قلم"));
    const resourcesContent = element("div", "resources-disclosure__content");
    resourcesContent.append(renderResourceTable(workspace.resources, resourcesWithheld, {
      ...resourcePaging,
      onChange: (next) => { resourcePaging = next; paint(); },
    }), stats);
    resourcesSection.append(resourceHead, resourcesContent);

    const linesSection = element("section", "items-section");
    const linesHead = element("div", "items-section__head lines-section__head");
    const linesMeta = element("div", "items-section__meta");
    linesMeta.append(createColumnControl({
      name: "estimate-lines",
      columns: lineColumns,
      visible: visibleLineColumns,
      table: () => root.querySelector(".estimate-lines-table"),
    }), lineActions);
    linesHead.append(element("div", "", ""), linesMeta);
    linesHead.firstElementChild.append(element("h2", "", "ریز برآورد پروژه"), element("p", "", "هر ردیف، مقدار برآوردشده یک قلم هزینه را فقط برای یک فعالیت مشخص نگه می‌دارد. استفاده همان قلم در فعالیت دیگر ردیف جدا دارد تا برآورد، اصلاحات و پیشرفت هر فعالیت مستقل و قابل پیگیری بماند؛ قیمت‌گذاری و هزینه واقعی در بخش قیمت روز و فاکتورهای تأییدشده محاسبه می‌شوند."));
    linesSection.append(linesHead, renderEstimateLineTable(workspace.estimateLines, workspace.resources, {
      paging: { ...linePaging, onChange: (next) => { linePaging = next; paint(); } },
      canEdit,
      withheld: linesWithheld,
      focusResourceId,
      focusEstimateLineId,
      columns: lineColumns,
      visible: visibleLineColumns,
      onRevise: (line, resource) => {
        const dialog = createRevisionDialog(adapter, line, resource, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      },
      onHistory: (line, resource) => {
        const dialog = createRevisionHistoryDialog(line, resource);
        root.append(dialog);
        showAccessibleDialog(dialog);
      },
      priceStatuses,
      onMapPrice: priceMappingAdapter ? (line, resource) => {
        const panel = createPriceMappingPanel({
          line, resource, adapter: priceMappingAdapter, canEdit,
          /* The panel STAYS OPEN after a material is saved. A line is priced from a list,
             and closing after the first entry would make adding the second a fresh trip
             through the table. The row behind it refreshes so the total stays honest. */
          onSaved: () => loadPriceStatuses(),
          onClose: () => { openPricePanel = null; panel.remove(); },
        });
        openPricePanel = panel;
        root.append(panel);
        showAccessibleDialog(panel);
      } : null,
      /* Stating the rate by hand, for the items the market will never quote. Reloads the
         whole workspace rather than only the price statuses: what this writes is a price
         VERSION on the cost item, and the item's price is part of the workspace. */
      onManualPrice: pricesAdapter ? (line, resource) => {
        const dialog = createManualPriceDialog({
          line, resource, adapter: pricesAdapter,
          current: line.currentUnitPriceIRR ?? null,
          onSaved: () => load(),
          onClose: () => dialog.element.remove(),
        });
        dialog.open();
      } : null,
    }));

    fragment.append(linesSection, resourcesSection);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
    /* Re-SHOWN, not merely re-appended: a dialog removed from the document leaves the top
       layer, and putting the node back gives a panel with no backdrop and no focus trap. */
    if (openPricePanel) {
      const wasOpen = openPricePanel.open;
      if (wasOpen) openPricePanel.close();
      root.append(openPricePanel);
      if (wasOpen) showAccessibleDialog(openPricePanel);
    }
    const target = root.querySelector(".deep-link-target");
    if (target) queueMicrotask(() => {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.focus({ preventScroll: true });
    });
  }

  load();
  return root;
}
