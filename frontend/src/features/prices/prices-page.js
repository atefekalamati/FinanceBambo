import { hasPermission } from "../../core/auth/permissions.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { validatePriceVersion } from "./prices-validation.js";
import { getUnitDefinition, UNIT_OPTIONS, validateUnitConversion } from "./unit-conversions-validation.js";

const SCOPE_LABELS = Object.freeze({ organization: "پایه سازمان", project: "اختصاصی پروژه" });

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatTomanFromIRR(value) {
  if (value === null || value === undefined || value === "") return "—";
  const digits = String(value).replace(/^0+(?=\d)/, "") || "0";
  const whole = digits.length > 1 ? digits.slice(0, -1) : "0";
  const remainder = digits.at(-1);
  return formatDisplayNumber(remainder === "0" ? whole : `${whole}.${remainder}`);
}

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

function createUnitConversionDialog(adapter, onSaved) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog price-dialog";
  const head = element("header", "price-dialog__head");
  const title = element("h2", "", "ثبت نسخه تبدیل واحد");
  const close = element("button", "dialog-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن پنجره");
  close.addEventListener("click", () => dialog.close());
  head.append(title, close);
  const form = element("form", "price-form");
  form.noValidate = true;
  const unitOptions = UNIT_OPTIONS.map((unit) => ({ value: unit.value, label: `${unit.label} · ${unit.dimensionLabel}` }));
  const source = createSelect({ id: "conversionSourceUnit", label: "واحد مبدأ", options: unitOptions });
  const target = createSelect({ id: "conversionTargetUnit", label: "واحد مقصد", options: unitOptions });
  const factor = createInput({ id: "conversionFactor", label: "ضریب تبدیل", hint: "عدد مثبت با حداکثر شش رقم اعشار؛ برای مثال هر تن برابر ۱۰۰۰ کیلوگرم است.", inputMode: "decimal" });
  const scope = createSelect({
    id: "conversionScope",
    label: "سطح تبدیل",
    options: [
      { value: "organization", label: "تبدیل پایه سازمان" },
      { value: "project", label: "تبدیل اختصاصی پروژه" },
    ],
  });
  const effectiveDate = createPersianDatePicker({ id: "conversionEffectiveDate", label: "تاریخ اثر", value: getTehranTodayIso(), hint: "تاریخ را براساس تقویم جلالی و زمان ایران انتخاب کنید." });
  const notice = element("div", "inline-notice", "تبدیل فقط میان واحدهای هم‌بُعد مجاز است. ثبت جدید، تاریخچه قبلی را بازنویسی نمی‌کند.");
  const cancel = element("button", "button button--ghost", "لغو");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت نسخه تبدیل");
  submit.type = "submit";
  const status = element("div", "form-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const actions = element("div", "form-actions");
  actions.append(cancel, submit, status);
  form.append(source.field, target.field, factor.field, scope.field, effectiveDate.field, notice, actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const validation = validateUnitConversion({ sourceUnit: source.select.value, targetUnit: target.select.value, factor: factor.input.value, scope: scope.select.value, effectiveDate: effectiveDate.getValue() });
    source.error.textContent = validation.errors.sourceUnit;
    target.error.textContent = validation.errors.targetUnit || validation.errors.dimension;
    factor.error.textContent = validation.errors.factor;
    scope.error.textContent = validation.errors.scope;
    effectiveDate.error.textContent = validation.errors.effectiveDate;
    source.select.setAttribute("aria-invalid", String(Boolean(validation.errors.sourceUnit)));
    target.select.setAttribute("aria-invalid", String(Boolean(validation.errors.targetUnit || validation.errors.dimension)));
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
      dialog.close();
      onSaved(workspace);
    } catch (error) {
      status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });
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
  const description = element("p", "price-import-dialog__description", "فایل باید شامل کد قلم، قیمت، واحد پول، تاریخ اثر و سطح قیمت باشد. پیش‌نمایش معتبر قبل از ثبت نهایی الزامی است.");
  const form = element("form", "price-import-form");
  form.noValidate = true;
  const field = element("div", "form-field");
  const label = element("label", "form-label", "فایل اکسل قیمت‌ها");
  label.htmlFor = "priceImportFile";
  const input = document.createElement("input");
  input.id = "priceImportFile";
  input.type = "file";
  input.accept = ".xlsx,.xls";
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
    ["ردیف", "قلم مالی", "قیمت", "واحد پول", "تاریخ اثر", "سطح قیمت", "نتیجه بررسی"].forEach((labelText) => header.append(element("th", "", labelText)));
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
        element("td", "", row.currency === "IRR" ? "ریال" : row.currency === "TOMAN" ? "تومان" : "نامعتبر"),
        element("td", "", row.status === "valid" ? formatBusinessDate(row.effectiveFrom) : "نامعتبر"),
        element("td", "", SCOPE_LABELS[row.scope] ?? "نامعتبر"),
        validationCell,
      );
      body.append(record);
    });
    table.append(tableHead, body);
    wrapper.append(table);
    const notice = element("div", preview.canCommit ? "inline-notice" : "price-import-warning", preview.canCommit ? "تمام ردیف‌ها معتبرند و آماده ثبت نهایی هستند." : "فایل ثبت نشده است. خطاها را اصلاح و دوباره پیش‌نمایش بگیرید.");
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
          confirmStatus.textContent = `${commitError.message}${commitError.requestId ? ` · شناسه درخواست: ${commitError.requestId}` : ""}`;
        } finally {
          cancel.disabled = false;
          confirm.disabled = false;
        }
      });
      dialog.after(confirmation);
      confirmation.addEventListener("close", () => confirmation.remove(), { once: true });
      confirmation.showModal();
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
      error.textContent = `${previewError.message}${previewError.requestId ? ` · شناسه درخواست: ${previewError.requestId}` : ""}`;
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
    label: "قلم مالی",
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
  const amount = createInput({ id: "unitPriceIRR", label: "قیمت واحد (ریال)", hint: "عدد صحیح ریال؛ نمایش فهرست به تومان است.", inputMode: "numeric" });
  const effectiveFrom = createPersianDatePicker({ id: "priceEffectiveFrom", label: "تاریخ اثر", value: getTehranTodayIso(), hint: "تاریخ را براساس تقویم جلالی و زمان ایران انتخاب کنید." });
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
      unitPriceIRR: amount.input.value,
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
      status.textContent = `${error.message}${error.requestId ? ` · شناسه درخواست: ${error.requestId}` : ""}`;
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
    }
  });

  dialog.append(head, form);
  return dialog;
}

function createPriceTrend(resourceId, history) {
  const versions = history.filter((price) => price.resourceId === resourceId).sort((left, right) => left.effectiveFrom.localeCompare(right.effectiveFrom) || left.sequence - right.sequence).slice(-6);
  const container = element("div", "price-trend");
  if (!versions.length) {
    container.append(element("span", "missing-value", "بدون سابقه"));
    return container;
  }
  const values = versions.map((price) => BigInt(price.unitPriceIRR));
  const minimum = values.reduce((result, value) => value < result ? value : result);
  const maximum = values.reduce((result, value) => value > result ? value : result);
  const range = maximum - minimum;
  const points = values.map((value, index) => {
    const x = versions.length === 1 ? 50 : Math.round((index * 100) / (versions.length - 1));
    const y = range === 0n ? 16 : 27 - Number(((value - minimum) * 22n) / range);
    return `${x},${y}`;
  }).join(" ");
  const direction = values.at(-1) > values[0] ? "افزایشی" : values.at(-1) < values[0] ? "کاهشی" : "بدون تغییر";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 32");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `روند ${direction} در ${formatDisplayNumber(String(versions.length))} نسخه قیمت`);
  const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  polyline.setAttribute("points", points);
  polyline.setAttribute("fill", "none");
  polyline.setAttribute("vector-effect", "non-scaling-stroke");
  svg.append(polyline);
  container.append(svg, element("small", `price-trend__label price-trend__label--${direction === "افزایشی" ? "up" : direction === "کاهشی" ? "down" : "flat"}`, direction));
  return container;
}

function renderCurrentPrices(items, history) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table current-prices-table");
  table.append(element("caption", "sr-only", "فهرست قیمت جاری اقلام مالی"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["قلم مالی", "واحد پایه", "قیمت پایه سازمان", "قیمت اختصاصی پروژه", "قیمت جاری", "روند نسخه‌ها", "مبنای قیمت جاری", "تاریخ اثر"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  items.forEach((item) => {
    const row = document.createElement("tr");
    const resource = document.createElement("td");
    resource.append(element("strong", "", item.resource.title), element("small", "table-subtext numeric", item.resource.code));
    const currentScope = item.currentPrice ? SCOPE_LABELS[item.currentPrice.scope] : "بدون قیمت";
    row.append(
      resource,
      element("td", "", formatUnitLabel(item.resource.baseUnit)),
      element("td", "numeric", item.organizationPrice ? `${formatTomanFromIRR(item.organizationPrice.unitPriceIRR)} تومان` : "—"),
      element("td", "numeric", item.projectPrice ? `${formatTomanFromIRR(item.projectPrice.unitPriceIRR)} تومان` : "—"),
      element("td", "numeric price-current", item.currentPrice ? `${formatTomanFromIRR(item.currentPrice.unitPriceIRR)} تومان` : "ثبت نشده"),
      element("td", "", ""),
      element("td", "", currentScope),
      element("td", "", item.currentPrice ? formatBusinessDate(item.currentPrice.effectiveFrom) : "—"),
    );
    row.children[5].append(createPriceTrend(item.resource.resourceId, history));
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function renderPriceFilters(filters, onApply, onReset) {
  const form = element("form", "price-list-filters");
  const search = element("input", "app-input");
  search.type = "search";
  search.value = filters.query;
  search.placeholder = "جست‌وجوی عنوان یا کد قلم مالی";
  search.setAttribute("aria-label", "جست‌وجوی قلم مالی");
  const scope = element("select", "app-select");
  scope.setAttribute("aria-label", "فیلتر مبنای قیمت جاری");
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

function renderPriceSummary(workspace) {
  const grid = element("section", "price-summary-grid");
  grid.setAttribute("aria-label", "خلاصه وضعیت قیمت‌ها");
  const projectOverrides = workspace.currentPrices.filter((item) => item.projectPrice).length;
  const missingPrices = workspace.currentPrices.filter((item) => !item.currentPrice).length;
  const versionedResources = new Set(workspace.history.map((price) => price.resourceId)).size;
  [
    ["قیمت اختصاصی فعال", projectOverrides, "قلم دارای قیمت مقدم پروژه"],
    ["قیمت نیازمند تکمیل", missingPrices, "قلم بدون قیمت معتبر جاری"],
    ["پوشش تاریخچه قیمت", versionedResources, `از ${formatDisplayNumber(String(workspace.currentPrices.length))} قلم مالی`],
  ].forEach(([title, value, description]) => {
    const card = element("article", "price-summary-card");
    card.append(element("h3", "", title), element("strong", "numeric", formatDisplayNumber(String(value))), element("p", "", description));
    grid.append(card);
  });
  return grid;
}

function renderHistory(history, currentPrices) {
  const resourceMap = new Map(currentPrices.map((item) => [item.resource.resourceId, item.resource]));
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table price-history-table");
  table.append(element("caption", "sr-only", "تاریخچه تغییرناپذیر قیمت‌ها"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["قلم مالی", "سطح", "قیمت واحد", "واحد پول", "تاریخ اثر", "ثبت‌کننده", "زمان ثبت"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  history.forEach((price) => {
    const resource = resourceMap.get(price.resourceId);
    const row = document.createElement("tr");
    row.append(
      element("td", "", resource?.title ?? "قلم حذف‌شده"),
      element("td", "", SCOPE_LABELS[price.scope] ?? "سطح نامشخص"),
      element("td", "numeric", `${formatTomanFromIRR(price.unitPriceIRR)} تومان`),
      element("td", "", "ریال"),
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

function renderCurrentConversions(items) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table current-conversions-table");
  table.append(element("caption", "sr-only", "فهرست تبدیل‌های واحد جاری"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["تبدیل", "بُعد", "ضریب پایه سازمان", "ضریب اختصاصی پروژه", "ضریب جاری", "مبنای جاری", "تاریخ اثر"].forEach((label) => header.append(element("th", "", label)));
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

function renderConversionHistory(history) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table conversion-history-table");
  table.append(element("caption", "sr-only", "تاریخچه نسخه‌های تبدیل واحد"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["واحد مبدأ", "واحد مقصد", "بُعد", "ضریب", "سطح", "تاریخ اثر", "ثبت‌کننده", "زمان ثبت"].forEach((label) => header.append(element("th", "", label)));
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

export function createPricesPage({ context, adapter }) {
  const root = element("div", "prices-page");
  const canEdit = hasPermission(context, "finance.edit");
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let listFilters = { query: "", scope: "all" };

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
    copy.append(element("span", "feature-header__eyebrow", "قیمت جاری و تاریخچه"), element("h1", "", "قیمت‌های مالی"), element("p", "", "قیمت پایه سازمان و قیمت اختصاصی پروژه را بدون بازنویسی نسخه‌های قبلی مدیریت کنید."));
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.href = "#/finance";
    header.append(copy, back);
    return header;
  }

  function openEditor(workspace) {
    const dialog = createPriceDialog(adapter, workspace.currentPrices, (next) => {
      state = createRequestState(REQUEST_STATUS.SUCCESS, next);
      paint();
    });
    root.append(dialog);
    dialog.showModal();
  }

  function openConversionEditor() {
    const dialog = createUnitConversionDialog(adapter, (next) => {
      state = createRequestState(REQUEST_STATUS.SUCCESS, next);
      paint();
    });
    root.append(dialog);
    dialog.showModal();
  }

  function renderEmpty() {
    const card = element("section", "state-card prices-empty");
    card.append(element("h2", "", "هنوز قیمتی ثبت نشده است"), element("p", "", canEdit ? "اولین قیمت پایه سازمان یا قیمت اختصاصی پروژه را ثبت کنید." : "برای اقلام این پروژه هنوز قیمت قابل نمایشی وجود ندارد."));
    if (canEdit) {
      const button = element("button", "button button--primary", "ثبت اولین قیمت");
      button.type = "button";
      button.addEventListener("click", async () => openEditor(await adapter.getPrices()));
      const conversionButton = element("button", "button button--ghost", "ثبت اولین تبدیل واحد");
      conversionButton.type = "button";
      conversionButton.addEventListener("click", openConversionEditor);
      card.append(button, conversionButton);
    }
    return card;
  }

  function renderContent(workspace) {
    const fragment = document.createDocumentFragment();
    const toolbar = element("div", "prices-toolbar");
    toolbar.append(element("p", "", "قیمت جاری، آخرین قیمت معتبر است و قیمت اختصاصی پروژه بر قیمت پایه سازمان اولویت دارد."));
    if (canEdit) {
      const addConversion = element("button", "button button--ghost", "ثبت تبدیل واحد");
      addConversion.type = "button";
      addConversion.addEventListener("click", openConversionEditor);
      const importPrices = element("button", "button button--ghost", "ورود گروهی قیمت");
      importPrices.type = "button";
      importPrices.addEventListener("click", () => {
        const dialog = createPriceImportDialog(adapter, (next) => {
          state = createRequestState(REQUEST_STATUS.SUCCESS, next);
          paint();
        });
        root.append(dialog);
        dialog.showModal();
      });
      const add = element("button", "button button--primary", "ثبت نسخه جدید قیمت");
      add.type = "button";
      add.addEventListener("click", () => openEditor(workspace));
      const toolbarActions = element("div", "prices-toolbar__actions");
      toolbarActions.append(addConversion, importPrices, add);
      toolbar.append(toolbarActions);
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
    currentHeading.append(element("div", "", ""), element("span", "section-count numeric", `${formatDisplayNumber(String(filteredPrices.length))} قلم`));
    currentHeading.firstElementChild.append(element("h2", "", "قیمت جاری اقلام"), element("p", "prices-section__hint", "قیمت‌ها به تومان نمایش داده می‌شوند و نمودار کوچک، روند نسخه‌های ثبت‌شده هر قلم را نشان می‌دهد."));
    current.append(currentHeading, filters);
    if (filteredPrices.length) current.append(renderCurrentPrices(filteredPrices, workspace.history));
    else current.append(element("div", "state-card price-filter-empty", "قلمی مطابق فیلترهای انتخاب‌شده پیدا نشد."));
    const history = element("section", "prices-section");
    history.append(element("h2", "", "تاریخچه قیمت‌ها"), element("p", "prices-section__hint", "تمام نسخه‌ها فقط‌خواندنی هستند و ثبت جدید، رکورد قبلی را تغییر نمی‌دهد."), renderHistory(workspace.history, workspace.currentPrices));
    const conversions = element("section", "prices-section");
    conversions.append(element("h2", "", "تبدیل واحد جاری"), element("p", "prices-section__hint", "تبدیل اختصاصی پروژه بر تبدیل پایه سازمان مقدم است و فقط میان واحدهای هم‌بُعد اعمال می‌شود."), renderCurrentConversions(workspace.currentConversions));
    const conversionHistory = element("section", "prices-section");
    conversionHistory.append(element("h2", "", "تاریخچه تبدیل واحد"), element("p", "prices-section__hint", "هر ثبت یک نسخه جدید است و نسخه‌های قبلی برای ممیزی حفظ می‌شوند."), renderConversionHistory(workspace.conversionHistory));
    fragment.append(toolbar, current, renderPriceSummary(workspace), conversions, history, conversionHistory);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(state, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
