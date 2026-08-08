import { hasPermission } from "../../core/auth/permissions.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";
import { getResourceTypeLabel, RESOURCE_TYPES } from "./financial-items-model.js";
import { validateEstimateLine, validateEstimateRevision, validateResource } from "./financial-items-validation.js";

const SOURCE_LABELS = Object.freeze({
  progress_feed: "خوراک پیشرفت",
  excel_import: "اکسل",
  manual_entry: "ورود دستی",
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

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

function createResourceDialog(adapter, onSaved) {
  const dialog = createDialog("ثبت قلم مالی جدید");
  const form = element("form", "workspace-form");
  form.noValidate = true;
  const type = createSelectField({ id: "resourceType", label: "نوع قلم مالی", options: RESOURCE_TYPES });
  const title = createTextField({ id: "resourceTitle", label: "عنوان قلم", hint: "عنوان قابل فهم برای کاربران مالی" });
  const code = createTextField({ id: "resourceCode", label: "کد قلم", hint: "کد پایدار برای جست‌وجو و Import" });
  const baseUnit = createTextField({ id: "resourceBaseUnit", label: "واحد پایه", hint: "مانند کیلوگرم، ساعت یا نفر-ساعت" });
  const dimension = createTextField({ id: "resourceDimension", label: "بُعد", hint: "کد نهایی ابعاد در منابع تعریف نشده؛ فعلاً عنوان متنی وارد کنید." });
  const notice = element("div", "inline-notice", "هزینه عمومی می‌تواند بدون مقدار فیزیکی، واحد پایه و بُعد ثبت شود.");
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت قلم مالی");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(type.wrapper, title.wrapper, code.wrapper, baseUnit.wrapper, dimension.wrapper, notice, actions);

  function syncGeneralCost() {
    const optional = type.select.value === "general_cost";
    [baseUnit.input, dimension.input].forEach((input) => {
      input.disabled = optional;
      if (optional) input.value = "";
    });
  }
  type.select.addEventListener("change", syncGeneralCost);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateResource({ type: type.select.value, title: title.input.value, code: code.input.value, baseUnit: baseUnit.input.value, dimension: dimension.input.value });
    setFieldError(type.select, type.error, validation.errors.type);
    setFieldError(title.input, title.error, validation.errors.title);
    setFieldError(code.input, code.error, validation.errors.code);
    setFieldError(baseUnit.input, baseUnit.error, validation.errors.baseUnit);
    setFieldError(dimension.input, dimension.error, validation.errors.dimension);
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
      status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
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
    options: workspace.activities.map((item) => ({ value: item.activityExternalId, label: `${item.wbsCode} · ${item.title}` })),
  });
  const resource = createSelectField({
    id: "lineResource",
    label: "قلم مالی",
    options: workspace.resources.map((item) => ({ value: item.resourceId, label: `${item.code} · ${item.title}` })),
  });
  const quantity = createTextField({ id: "lineOriginalQuantity", label: "مقدار اولیه", hint: "مقدار با واحد پایه قلم ثبت می‌شود.", inputMode: "decimal" });
  const relationNotice = element("div", "inline-notice", "هر فعالیت و قلم مالی یک خط مستقل است؛ استفاده همان قلم در فعالیت دیگر خط جدا می‌سازد.");
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
  form.append(activity.wrapper, resource.wrapper, quantity.wrapper, relationNotice, actions);

  function syncQuantityLabel() {
    const selected = workspace.resources.find((item) => item.resourceId === resource.select.value);
    const isGeneralCost = selected?.type === "general_cost";
    quantity.label.textContent = isGeneralCost ? "مبلغ اولیه (ریال)" : "مقدار اولیه";
    quantity.hint.textContent = isGeneralCost ? "هزینه عمومی بدون مقدار فیزیکی و با مبلغ ریال ثبت می‌شود." : `مقدار با واحد پایه ${formatUnitLabel(selected?.baseUnit)} ثبت می‌شود.`;
  }
  resource.select.addEventListener("change", syncQuantityLabel);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateEstimateLine({ activityExternalId: activity.select.value, resourceId: resource.select.value, originalQuantity: quantity.input.value });
    setFieldError(activity.select, activity.error, validation.errors.activityExternalId);
    setFieldError(resource.select, resource.error, validation.errors.resourceId);
    setFieldError(quantity.input, quantity.error, validation.errors.originalQuantity);
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
      status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
    } finally {
      submit.disabled = false;
    }
  });
  dialog.append(form);
  return dialog;
}

function createEstimateImportDialog(adapter, onSaved) {
  const dialog = createDialog("ورود گروهی برآورد");
  dialog.classList.add("import-dialog");

  const description = element("p", "import-dialog__description", "فایل اکسل ابتدا فقط بررسی می‌شود. تا زمانی که تمام ردیف‌ها معتبر نباشند، هیچ خط برآوردی ثبت نخواهد شد.");
  const form = element("form", "import-form");
  form.noValidate = true;
  const field = element("div", "form-field form-field--wide");
  const label = element("label", "form-label", "فایل اکسل برآورد");
  label.htmlFor = "estimateImportFile";
  const input = document.createElement("input");
  input.id = "estimateImportFile";
  input.name = "estimateImportFile";
  input.type = "file";
  input.accept = ".xlsx,.xls";
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
    ["ردیف", "فعالیت", "قلم مالی", "مقدار", "واحد", "نتیجه بررسی"].forEach((title) => header.append(element("th", "", title)));
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

    const notice = element(
      "div",
      preview.canCommit ? "inline-notice import-notice--valid" : "overrun-warning",
      preview.canCommit ? "تمام ردیف‌ها معتبرند و فایل آماده ثبت نهایی است." : "فایل ثبت نشده است. خطاهای ردیفی را در فایل اصلاح و دوباره بارگذاری کنید.",
    );
    const commit = element("button", "button button--primary", "ثبت نهایی ردیف‌های معتبر");
    commit.type = "button";
    commit.disabled = !preview.canCommit;
    commit.addEventListener("click", () => {
      const confirmation = document.createElement("dialog");
      confirmation.className = "confirm-dialog";
      const title = element("h2", "", "تأیید ثبت نهایی برآورد");
      const message = element("p", "", `${formatDisplayNumber(String(preview.validRows))} خط برآورد با مقدار اولیه تغییرناپذیر ثبت می‌شود. آیا ادامه می‌دهید؟`);
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
          status.textContent = `${commitError.message}${commitError.requestId ? ` · شناسه درخواست: ${commitError.requestId}` : ""}`;
        } finally {
          confirm.disabled = false;
          cancel.disabled = false;
        }
      });
      dialog.after(confirmation);
      confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
      confirmation.showModal();
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
      error.textContent = `${previewError.message}${previewError.requestId ? ` · شناسه درخواست: ${previewError.requestId}` : ""}`;
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
  const unit = isGeneralCost ? "ریال" : formatUnitLabel(resource.baseUnit);
  const dialog = createDialog("ثبت بازنگری مقدار");
  const summary = element("div", "revision-summary");
  const original = element("article", "revision-summary__item");
  original.append(element("span", "", "مقدار اولیه قفل‌شده"), element("strong", "numeric", formatDisplayNumber(originalValue)), element("small", "numeric", unit));
  const current = element("article", "revision-summary__item");
  current.append(element("span", "", "مقدار اصلاح‌شده فعلی"), element("strong", "numeric", formatDisplayNumber(currentValue)), element("small", "numeric", `بازنگری ${line.revision}`));
  summary.append(original, current);

  const form = element("form", "workspace-form revision-form");
  form.noValidate = true;
  const revised = createTextField({
    id: `revisedValue-${line.lineId}`,
    label: isGeneralCost ? "مبلغ اصلاح‌شده (ریال)" : `مقدار اصلاح‌شده (${unit})`,
    hint: "مقدار اولیه تغییر نمی‌کند؛ فقط یک بازنگری جدید ثبت می‌شود.",
    inputMode: "decimal",
  });
  revised.input.value = currentValue;
  const reasonField = element("div", "form-field form-field--wide");
  const reasonLabel = element("label", "form-label", "دلیل بازنگری");
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
  const submit = element("button", "button button--primary", "تأیید و ثبت بازنگری");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(revised.wrapper, reasonField, warning, actions);

  function syncWarning() {
    const validation = validateEstimateRevision({ revisedValue: revised.input.value, reason: "valid reason" }, { isGeneralCost });
    const isOverrun = validation.values.revisedValue && validation.errors.revisedValue === "" && compareDecimalStrings(validation.values.revisedValue, originalValue) > 0;
    warning.hidden = !isOverrun;
    warning.textContent = isOverrun ? "مقدار اصلاح‌شده از مقدار اولیه بیشتر است. ثبت مسدود نمی‌شود، اما دلیل آن در Audit و تاریخچه حفظ خواهد شد." : "";
  }
  revised.input.addEventListener("input", syncWarning);
  syncWarning();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateEstimateRevision({ revisedValue: revised.input.value, reason: reason.value }, { isGeneralCost });
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
    status.textContent = "در حال ثبت بازنگری…";
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
      status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });

  dialog.append(summary, form);
  return dialog;
}

function createRevisionHistoryDialog(line, resource) {
  const dialog = createDialog("تاریخچه بازنگری خط متره");
  const identity = element("div", "revision-identity");
  identity.append(element("strong", "", `${line.activityTitle} · ${resource.title}`), element("small", "numeric", `${line.wbsCode} · ${resource.code}`));
  dialog.append(identity);
  if (!line.revisions.length) {
    dialog.append(element("div", "inline-notice", "برای این خط هنوز بازنگری ثبت نشده و مقدار اصلاح‌شده با مقدار اولیه برابر است."));
    return dialog;
  }

  const wrapper = element("div", "revision-list");
  line.revisions.forEach((revision) => {
    const item = element("article", `revision-record ${revision.isOverrun ? "revision-record--overrun" : ""}`);
    const head = element("div", "revision-record__head");
    head.append(element("strong", "", `بازنگری ${revision.revisionNumber}`), element("time", "", formatSystemDateTime(revision.occurredAt)));
    const values = element("div", "revision-record__values");
    values.append(element("span", "", `از ${formatDisplayNumber(revision.previousValue)} به ${formatDisplayNumber(revision.newValue)}`), element("small", "", resource.type === "general_cost" ? "ریال" : formatUnitLabel(resource.baseUnit)));
    item.append(head, values, element("p", "", revision.reason), element("small", "revision-record__actor", revision.actorName || revision.actorId));
    if (revision.isOverrun) item.append(element("span", "overrun-badge", "بیشتر از مقدار اولیه"));
    wrapper.append(item);
  });
  dialog.append(wrapper);
  return dialog;
}

function renderResourceTable(resources) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table items-table");
  table.append(element("caption", "sr-only", "فهرست اقلام مالی"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["کد", "عنوان", "نوع", "واحد پایه", "بُعد", "منبع ورود"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  resources.forEach((resource) => {
    const row = document.createElement("tr");
    const typeCell = document.createElement("td");
    typeCell.append(element("span", `type-badge type-badge--${resource.type}`, getResourceTypeLabel(resource.type)));
    row.append(
      element("td", "numeric", resource.code),
      element("td", "", resource.title),
      typeCell,
      element("td", "numeric", formatUnitLabel(resource.baseUnit)),
      element("td", "", resource.dimension ?? "مبلغی"),
      element("td", "", SOURCE_LABELS[resource.source] ?? "منبع تعریف‌نشده"),
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function renderEstimateLineTable(lines, resources, { canEdit, onRevise, onHistory }) {
  const resourceMap = new Map(resources.map((resource) => [resource.resourceId, resource]));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table estimate-lines-table");
  table.append(element("caption", "sr-only", "خطوط مستقل فعالیت و قلم مالی"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["ساختار شکست کار / فعالیت", "قلم مالی", "واحد", "مقدار/مبلغ اولیه", "مقدار/مبلغ اصلاح‌شده", "منبع", "عملیات"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  lines.forEach((line) => {
    const resource = resourceMap.get(line.resourceId);
    const isGeneralCost = resource?.type === "general_cost";
    const original = isGeneralCost ? line.originalAmount : line.originalQuantity;
    const revised = isGeneralCost ? line.revisedAmount : line.revisedQuantity;
    const changed = original !== revised;
    const row = document.createElement("tr");
    const activityCell = document.createElement("td");
    activityCell.append(element("strong", "", line.activityTitle), element("small", "table-subtext numeric", `${line.wbsCode} · ${line.activityExternalId}`));
    const resourceCell = document.createElement("td");
    resourceCell.append(element("strong", "", resource?.title ?? "—"), element("small", "table-subtext numeric", resource?.code ?? "—"));
    const revisedCell = element("td", `numeric ${changed ? "value-changed" : ""}`, formatDisplayNumber(revised));
    if (changed) revisedCell.append(element("span", "change-badge", "اصلاح‌شده"));
    const actionsCell = element("td", "line-actions");
    const history = element("button", "table-action", "تاریخچه");
    history.type = "button";
    history.addEventListener("click", () => onHistory(line, resource));
    actionsCell.append(history);
    if (canEdit) {
      const revise = element("button", "table-action table-action--primary", "بازنگری");
      revise.type = "button";
      revise.addEventListener("click", () => onRevise(line, resource));
      actionsCell.append(revise);
    }
    row.append(
      activityCell,
      resourceCell,
      element("td", "numeric", isGeneralCost ? "ریال" : formatUnitLabel(resource?.baseUnit)),
      element("td", "numeric", formatDisplayNumber(original)),
      revisedCell,
      element("td", "", SOURCE_LABELS[line.source] ?? "منبع تعریف‌نشده"),
      actionsCell,
    );
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function createFinancialItemsPage({ context, adapter }) {
  const root = element("div", "financial-items-page");
  const canEdit = hasPermission(context, "finance.edit");
  let state = createRequestState(REQUEST_STATUS.LOADING);

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
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.href = "#/finance";
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "اقلام مالی و خطوط برآورد"), element("h1", "", "اقلام و متره"), element("p", "", "هر اتصال فعالیت و قلم مالی یک خط مستقل است؛ مقادیر اولیه حفظ و مقدار اصلاح‌شده جداگانه نمایش داده می‌شود."));
    header.append(copy, back);
    return header;
  }

  function renderEmpty() {
    const card = element("section", "state-card items-empty");
    card.append(element("h2", "", "هنوز قلم مالی ثبت نشده است"), element("p", "", canEdit ? "اولین قلم مالی را ثبت کنید و سپس آن را به یک فعالیت متصل کنید." : "برای این پروژه هنوز اقلام و متره‌ای قابل نمایش نیست."));
    if (canEdit) {
      const button = element("button", "button button--primary", "ثبت اولین قلم");
      button.type = "button";
      button.addEventListener("click", async () => {
        const workspace = await adapter.getWorkspace();
        const dialog = createResourceDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      });
      card.append(button);
    }
    return card;
  }

  function renderContent(workspace) {
    const fragment = document.createDocumentFragment();
    const counts = new Map(RESOURCE_TYPES.map((type) => [type.value, 0]));
    workspace.resources.forEach((resource) => counts.set(resource.type, (counts.get(resource.type) ?? 0) + 1));
    const stats = element("section", "item-type-grid");
    RESOURCE_TYPES.forEach((type) => {
      const card = element("article", `item-type-card item-type-card--${type.value}`);
      card.append(element("span", "", type.label), element("strong", "numeric", formatDisplayNumber(String(counts.get(type.value) ?? 0))), element("small", "", "قلم ثبت‌شده"));
      stats.append(card);
    });

    const toolbar = element("div", "items-toolbar");
    const summary = element("p", "", `${formatDisplayNumber(String(workspace.resources.length))} قلم مالی · ${formatDisplayNumber(String(workspace.estimateLines.length))} خط مستقل متره`);
    toolbar.append(summary);
    if (canEdit) {
      const addResource = element("button", "button button--ghost", "قلم جدید");
      addResource.type = "button";
      const addLine = element("button", "button button--primary", "خط متره جدید");
      addLine.type = "button";
      const importEstimate = element("button", "button button--ghost", "ورود گروهی برآورد");
      importEstimate.type = "button";
      addResource.addEventListener("click", () => {
        const dialog = createResourceDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      });
      addLine.addEventListener("click", () => {
        const dialog = createEstimateLineDialog(adapter, workspace, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      });
      importEstimate.addEventListener("click", () => {
        const dialog = createEstimateImportDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      });
      const actions = element("div", "items-toolbar__actions");
      actions.append(addResource, addLine, importEstimate);
      toolbar.append(actions);
    }

    const resourcesSection = element("section", "items-section");
    const resourceHead = element("div", "items-section__head");
    resourceHead.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(workspace.resources.length))));
    resourceHead.firstElementChild.append(element("h2", "", "کاتالوگ اقلام مالی"), element("p", "", "چهار نوع قلم، واحد پایه و بُعد هر قلم"));
    resourcesSection.append(resourceHead, renderResourceTable(workspace.resources));

    const linesSection = element("section", "items-section");
    const linesHead = element("div", "items-section__head");
    linesHead.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(workspace.estimateLines.length))));
    linesHead.firstElementChild.append(element("h2", "", "خطوط مستقل فعالیت و قلم مالی"), element("p", "", "تکرار یک قلم در دو فعالیت، دو خط مستقل با شناسه جدا می‌سازد."));
    linesSection.append(linesHead, renderEstimateLineTable(workspace.estimateLines, workspace.resources, {
      canEdit,
      onRevise: (line, resource) => {
        const dialog = createRevisionDialog(adapter, line, resource, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      },
      onHistory: (line, resource) => {
        const dialog = createRevisionHistoryDialog(line, resource);
        root.append(dialog);
        dialog.showModal();
      },
    }));

    fragment.append(stats, toolbar, resourcesSection, linesSection);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
