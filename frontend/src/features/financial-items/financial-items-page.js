import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { downloadCsvFile } from "../../shared/exports/csv.js";
import { buildEstimateLinesCsv, estimateLinesFileName } from "./financial-items-csv.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatTomanFromIrr, tomanInputToIrr } from "../../shared/formatters/money.js";
import { getDisplayCurrencyLabel } from "../../shared/preferences/currency-preference.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { getResourceTypeLabel, RESOURCE_TYPES } from "./financial-items-model.js";
import { validateActivity, validateEstimateLine, validateEstimateRevision, validateResource } from "./financial-items-validation.js";
import { describeImportPreview } from "../../shared/imports/import-preview-notice.js";
import { element } from "../../shared/dom/elements.js";
import { IDENTITY, PRIMARY, SECONDARY, applyColumnVisibility, createColumnControl, createDataTable, defaultVisibleColumns }
  from "../../shared/components/data-table.js";
import { ABSENT, activityBlockStarts, activityLabel, canonicalWbs, resourceLabel, resourceSourceLabel, scheduleCostOf, selectEstimateRows, selectVisibleResources, sortEstimateRows, sourceLabel, withheldRowsNotice } from "./financial-items-presentation.js";

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
  const hint = element("small", "form-hint", "قالب دقیق ستون‌ها در منابع تعریف نشده است و پس از دریافت قرارداد سمت سرور نهایی می‌شود.");
  hint.id = "estimateImportHint";
  const error = element("small", "form-error");
  error.id = "estimateImportError";
  error.setAttribute("aria-live", "polite");
  field.append(label, input, hint, error);

  const previewButton = element("button", "button button--primary", "بررسی و نمایش پیش‌نمایش");
  previewButton.type = "submit";
  const formStatus = element("div", "form-status");
  formStatus.setAttribute("role", "status");
  formStatus.setAttribute("aria-live", "polite");
  const formActions = element("div", "form-actions");
  formActions.append(previewButton, formStatus);
  form.append(field, formActions);

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
    const file = input.files?.[0];
    error.textContent = file ? "" : "انتخاب فایل اکسل الزامی است.";
    input.setAttribute("aria-invalid", String(!file));
    if (!file) {
      input.focus();
      return;
    }
    previewButton.disabled = true;
    input.disabled = true;
    formStatus.textContent = "در حال بررسی فایل…";
    resultRegion.hidden = true;
    try {
      currentPreview = await adapter.previewEstimateImport(file);
      formStatus.textContent = currentPreview.canCommit ? "پیش‌نمایش معتبر آماده است." : "پیش‌نمایش دارای خطاست.";
      renderPreview(currentPreview);
    } catch (previewError) {
      currentPreview = null;
      error.textContent = formatApiErrorMessage(previewError);
      formStatus.textContent = "بررسی فایل انجام نشد.";
    } finally {
      previewButton.disabled = false;
      input.disabled = false;
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
    item.append(head, values, element("p", "", revision.reason), element("small", "revision-record__actor", revision.actorName || revision.actorId));
    if (revision.isOverrun) item.append(element("span", "overrun-badge", "بیشتر از برآورد اولیه"));
    wrapper.append(item);
  });
  dialog.append(wrapper);
  return dialog;
}

function renderResourceTable(resources, withheld = null) {
  const fragment = document.createDocumentFragment();
  if (withheld) fragment.append(element("p", "table-note", withheld));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table items-table");
  table.append(element("caption", "sr-only", "فهرست اقلام مالی"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["کد", "عنوان", "نوع", "واحد پایه", "منبع ورود"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  resources.forEach((resource) => {
    const row = document.createElement("tr");
    const typeCell = element("td", "items-table__type");
    typeCell.append(element("span", `type-badge type-badge--${resource.type}`, getResourceTypeLabel(resource.type)));
    row.append(
      element("td", "numeric", resource.code),
      element("td", "", resource.title),
      typeCell,
      element("td", "numeric", formatUnitLabel(resource.baseUnit)),
      element("td", "", resourceSourceLabel(resource)),
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  fragment.append(wrapper);
  return fragment;
}

/* The ten columns of ریز برآورد. Three of them are money and they are three on
   purpose: «هزینه MSP فعالیت» is what the schedule says the activity costs,
   «قیمت اولیه» is the unit price this line was estimated at and never changes,
   «قیمت روز» is the price in force today. None is computed from another and an
   empty one means unknown, not zero. */
function estimateLineColumns() {
  return [
    { key: "identity", label: "ساختار شکست کار / فعالیت", tier: IDENTITY },
    { key: "resource", label: "قلم هزینه", tier: PRIMARY },
    { key: "unit", label: "واحد", tier: SECONDARY, cellClass: "numeric" },
    { key: "originalQuantity", label: "مقدار برآورد اولیه", tier: SECONDARY, cellClass: "numeric" },
    { key: "revisedQuantity", label: "آخرین مقدار برآورد", tier: PRIMARY, cellClass: "numeric" },
    { key: "scheduleCost", label: "هزینه MSP فعالیت", tier: SECONDARY, keepOnTablet: true, cellClass: "numeric" },
    { key: "originalPrice", label: "قیمت اولیه", tier: SECONDARY, cellClass: "numeric" },
    { key: "currentPrice", label: "قیمت روز", tier: PRIMARY, cellClass: "numeric" },
    { key: "source", label: "منبع", tier: SECONDARY },
    { key: "actions", label: "عملیات", tier: SECONDARY, keepOnTablet: true, cellClass: "line-actions" },
  ];
}

function renderEstimateLineTable(lines, resources, { canEdit, onRevise, onHistory, withheld = null, focusResourceId = "", focusEstimateLineId = "", columns, visible }) {
  const resourceMap = new Map(resources.map((resource) => [resource.resourceId, resource]));
  const fragment = document.createDocumentFragment();
  if (withheld) fragment.append(element("p", "table-note", withheld));

  fragment.append(createDataTable({
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

      const resourceCell = document.createDocumentFragment();
      resourceCell.append(element("strong", "", resourceLabel(resource)),
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

      return {
        identity: "",
        resource: resourceCell,
        unit: isGeneralCost ? getDisplayCurrencyLabel() : formatUnitLabel(resource?.baseUnit),
        originalQuantity: isGeneralCost ? formatTomanFromIrr(original, { withCurrency: false }) : formatDisplayNumber(original),
        revisedQuantity: revisedCell,
        scheduleCost: "",
        originalPrice: formatTomanFromIrr(line.originalUnitPriceIRR, { withCurrency: false }),
        currentPrice: formatTomanFromIrr(line.currentUnitPriceIRR, { withCurrency: false }),
        source: sourceLabel(line),
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
export function createFinancialItemsPage({ context, adapter, surface = SURFACES.OPERATIONS, focusResourceId = "", focusEstimateLineId = "" }) {
  const root = element("div", "financial-items-page");
  const readOnly = surface === SURFACES.REPORT;
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
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const back = element("a", "button button--ghost", `بازگشت به ${SURFACE_LABELS[surface]}`);
    back.classList.add("finance-back-link");
    back.href = `#${homeRouteFor(surface)?.path ?? "/finance"}`;
    const navigation = element("div", "feature-header__navigation");
    const otherActions = element("div", "feature-header__other-actions");
    navigation.append(otherActions, back);
    const copy = element("div", "feature-header__copy");
    copy.append(
      element("span", "feature-header__eyebrow", readOnly ? "جدول اقلام و ریز برآورد" : "اقلام پروژه و ریز برآورد"),
      element("h1", "", readOnly ? "جدول اقلام و برآورد" : "اقلام و برآورد"),
      element("p", "", readOnly
        ? "هر ردیف، مقدار برآوردشده یک قلم هزینه برای یک فعالیت است. این صفحه فقط‌خواندنی است و می‌توانید از آن خروجی اکسل بگیرید."
        : "هر اتصال فعالیت و قلم هزینه یک ردیف مستقل برآورد است؛ مقدار اولیه حفظ و آخرین مقدار برآورد جداگانه نمایش داده می‌شود."),
    );
    header.append(copy, navigation);
    return header;
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
    resourcesContent.append(renderResourceTable(workspace.resources, resourcesWithheld), stats);
    resourcesSection.append(resourceHead, resourcesContent);

    const linesSection = element("section", "items-section");
    const linesHead = element("div", "items-section__head lines-section__head");
    const linesMeta = element("div", "items-section__meta");
    linesMeta.append(createColumnControl({
      name: "estimate-lines",
      columns: lineColumns,
      visible: visibleLineColumns,
      onToggle: (key, on) => {
        if (on) visibleLineColumns.add(key);
        else visibleLineColumns.delete(key);
        applyColumnVisibility(root.querySelector(".estimate-lines-table"), key, on);
      },
    }), lineActions);
    linesHead.append(element("div", "", ""), linesMeta);
    linesHead.firstElementChild.append(element("h2", "", "ریز برآورد پروژه"), element("p", "", "هر ردیف، مقدار برآوردشده یک قلم هزینه را فقط برای یک فعالیت مشخص نگه می‌دارد. استفاده همان قلم در فعالیت دیگر ردیف جدا دارد تا برآورد، اصلاحات و پیشرفت هر فعالیت مستقل و قابل پیگیری بماند؛ قیمت‌گذاری و هزینه واقعی در بخش قیمت روز و فاکتورهای تأییدشده محاسبه می‌شوند."));
    linesSection.append(linesHead, renderEstimateLineTable(workspace.estimateLines, workspace.resources, {
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
    }));

    fragment.append(linesSection, resourcesSection);
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
