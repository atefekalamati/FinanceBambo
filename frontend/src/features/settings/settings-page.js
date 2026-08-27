import { capabilitiesFor, describeAccess } from "../../core/auth/capabilities.js";
import { SURFACES, SURFACE_LABELS, homeRouteFor } from "../../core/config/routes.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { formatArea, formatBusinessDate, formatDisplayNumber, formatSystemDateTime } from "../../shared/formatters/display.js";
import { getDisplayCurrencyCode, getDisplayCurrencyLabel, setDisplayCurrencyCode } from "../../shared/preferences/currency-preference.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { createUnitConversionForm, renderConversionHistory, renderCurrentConversions } from "../prices/prices-page.js";
import { isConfigurableConversionDirection } from "../prices/unit-conversions-validation.js";
import { validateSettingsRevision } from "./settings-validation.js";
import { element, tableCaption, tableHead } from "../../shared/dom/elements.js";

function createField({ id, label, type = "text", value = "", hint, inputMode, required = false }) {
  const field = element("div", "form-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = id;
  const input = document.createElement("input");
  input.id = id;
  input.name = id;
  input.type = type;
  input.value = value;
  input.required = required;
  if (inputMode) input.inputMode = inputMode;
  input.setAttribute("aria-describedby", `${id}-hint ${id}-error`);
  const hintNode = element("small", "form-hint", hint);
  hintNode.id = `${id}-hint`;
  const errorNode = element("small", "form-error");
  errorNode.id = `${id}-error`;
  errorNode.setAttribute("aria-live", "polite");
  field.append(labelNode, input, hintNode, errorNode);
  return { field, input, error: errorNode };
}

/**
 * The append-only trail comes from GET /settings/revisions. Each row pairs a
 * revision with the area it replaced, so the original value stays visible
 * alongside every correction (FR-001).
 */
function createRevisionTable(revisions = []) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table settings-history");
  table.append(
    tableCaption("تاریخچه بازنگری زیربنای کل پروژه"),
    tableHead(["بازنگری", "تاریخ اعمال", "مقدار قبلی", "مقدار جدید", "دلیل", "ثبت‌کننده", "زمان ثبت"]),
  );
  const body = document.createElement("tbody");
  revisions.forEach((revision) => {
    const row = document.createElement("tr");
    row.append(
      element("td", "numeric", formatDisplayNumber(String(revision.revisionNumber))),
      element("td", "", revision.effectiveDate ? formatBusinessDate(revision.effectiveDate) : "—"),
      element("td", "numeric", revision.previousValue ? formatArea(revision.previousValue) : "ثبت اولیه"),
      element("td", "numeric", formatArea(revision.newValue)),
      element("td", "", revision.reason || "بدون دلیل ثبت‌شده"),
      element("td", "numeric", revision.actorName || revision.actorId || "نامشخص"),
      element("td", "", revision.occurredAt ? formatSystemDateTime(revision.occurredAt) : "—"),
    );
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function createRevisionHistory(data) {
  const wrapper = element("div", "settings-revision-current");
  const revisions = data.revisions ?? [];
  if (!revisions.length) {
    wrapper.append(element("p", "inline-notice", "هنوز بازنگری‌ای برای زیربنای کل ثبت نشده است."));
    return wrapper;
  }
  wrapper.append(createRevisionTable(revisions));
  return wrapper;
}

/**
 * One page, two surfaces.
 *
 * On امور مالی it is the whole thing: the gross built area every per-square-metre
 * figure divides by, the working unit conversions, and the append-only trail of
 * both — settings that change what the project's numbers come out as.
 *
 * On گزارش مالی it is only what changes nothing: which currency to read amounts
 * in, and what this account is allowed to do. That is a choice about what is
 * worth offering, not a permission check — the Backend still refuses a PATCH
 * from an account without `finance.edit`, whichever surface asked.
 */
export function createSettingsPage({ context, adapter, pricesAdapter, surface = SURFACES.OPERATIONS, onSettingsUpdated = () => {} }) {
  const readerOnly = surface === SURFACES.REPORT;
  const root = element("div", `settings-page${readerOnly ? " settings-page--reader" : ""}`);
  let state = createRequestState(REQUEST_STATUS.LOADING);
  let settings = null;
  let conversionWorkspace = null;
  let conversionError = null;
  let conversionEditorOpen = false;

  async function load() {
    // The reader-only view is built entirely from the currency preference held
    // in this browser and the permissions the host already granted. It asks the
    // service for nothing, so nothing the service answers can stop it — not a
    // project whose gross built area was never recorded, and not a 403 on a
    // settings record it does not read.
    if (readerOnly) {
      settings = null;
      conversionWorkspace = null;
      conversionError = null;
      state = createRequestState(REQUEST_STATUS.SUCCESS, null);
      paint();
      return;
    }
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const [settingsResult, conversionsResult] = await Promise.allSettled([
        adapter.getSettings(),
        pricesAdapter.getPrices(),
      ]);
      if (settingsResult.status === "rejected") throw settingsResult.reason;
      settings = settingsResult.value;
      if (conversionsResult.status === "fulfilled") {
        conversionWorkspace = conversionsResult.value;
        conversionError = null;
      } else {
        conversionWorkspace = null;
        conversionError = conversionsResult.reason;
      }
      state = createRequestState(settings ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, settings);
    } catch (error) {
      state = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const home = homeRouteFor(surface);
    const back = element("a", "button button--ghost", `بازگشت به ${SURFACE_LABELS[surface] ?? "امور مالی"}`);
    back.classList.add("finance-back-link");
    back.href = `#${home?.path ?? "/finance"}`;
    const navigation = element("div", "feature-header__navigation");
    const otherActions = element("div", "feature-header__other-actions");
    navigation.append(otherActions, back);
    const copy = element("div", "feature-header__copy");
    const eyebrow = element("span", "feature-header__eyebrow", readerOnly ? "نمایش گزارش مالی" : "پیکربندی پروژه جاری");
    const title = element("h1", "", readerOnly ? "تنظیمات نمایش" : "تنظیمات مالی پروژه");
    copy.append(eyebrow, title, element("p", "", readerOnly
      ? "واحدی که مبالغ با آن نمایش داده می‌شوند را انتخاب کنید و ببینید این حساب چه دسترسی‌های مالی دارد. این تنظیمات هیچ عددی از پروژه را تغییر نمی‌دهند."
      : "قواعد پایه محاسبات مالی، نحوه نمایش پول، زیربنا و تبدیل واحدهای پروژه را از یک محل مدیریت کنید."));
    header.append(copy, navigation);
    return header;
  }

  function renderEmpty() {
    const card = element("section", "state-card settings-empty");
    card.append(element("h2", "", "تنظیمات مالی هنوز ثبت نشده است"), element("p", "", `برای شروع، زیربنای کل پروژه را ثبت کنید. واحد پول رسمی به‌صورت ثابت ${CURRENCY_LABELS.IRR} خواهد بود.`));
    // There is no settings row yet, so the Backend has had no chance to send a
    // canEdit verdict — GET /settings answers 404. The host permission is all
    // there is to go on, and it is the conservative half of the policy.
    if (mayReviseArea(null)) {
      const button = element("button", "button button--primary", "ثبت اولین تنظیمات");
      button.type = "button";
      button.addEventListener("click", () => root.replaceChildren(renderHeader(), renderEditor(null)));
      card.append(button);
    } else {
      card.append(element("p", "inline-notice", "ثبت زیربنای کل نیازمند مجوز ویرایش اطلاعات مالی است."));
    }
    return card;
  }

  function renderCurrencyPolicy() {
    const section = element("section", "settings-card currency-policy");
    const title = element("div", "settings-card__head");
    title.append(element("div", "settings-card__icon", "﷼"), element("div", "", ""));
    title.lastElementChild.append(element("h2", "", "واحد نمایش مبالغ"), element("p", "", "واحدی را انتخاب کنید که مبالغ در تمام بخش‌های مالی با آن نمایش داده شوند."));
    const grid = element("div", "currency-grid");
    const selectedCode = getDisplayCurrencyCode();
    [["TOMAN", "تومان", "نمایش ساده‌تر و پیش‌فرض سامانه"], ["IRR", "ریال", "نمایش مبلغ رسمی بدون تبدیل"]].forEach(([code, label, description]) => {
      const option = element("button", `currency-item currency-choice${selectedCode === code ? " currency-item--active" : ""}`);
      option.type = "button";
      option.setAttribute("role", "radio");
      option.setAttribute("aria-checked", String(selectedCode === code));
      option.append(element("span", "currency-item__label", selectedCode === code ? "انتخاب‌شده" : "انتخاب واحد"), element("strong", "", label), element("small", "", description));
      option.addEventListener("click", () => {
        if (getDisplayCurrencyCode() !== code) setDisplayCurrencyCode(code);
      });
      grid.append(option);
    });
    grid.setAttribute("role", "radiogroup");
    grid.setAttribute("aria-label", "انتخاب واحد نمایش مبالغ مالی");
    section.append(title, grid);
    return section;
  }

  function renderAccessSummary() {
    const section = element("section", "settings-card settings-access");
    const head = element("div", "settings-card__head");
    head.append(element("div", "settings-card__icon", "✓"), element("div", "", ""));
    head.lastElementChild.append(
      element("h2", "", "دسترسی‌های مالی شما"),
      element("p", "", "این بخش فقط وضعیت دسترسی‌های دریافتی از سیستم اصلی BAMBO را نمایش می‌دهد."),
    );
    const list = element("ul", "settings-access__list");
    // Read back from the one place the host's codes are named, so a code the
    // module starts honouring cannot be missing from the list that claims to
    // show this account everything it may do.
    describeAccess(context).forEach(({ label, allowed }) => {
      const item = element("li", `settings-access__item settings-access__item--${allowed ? "allowed" : "denied"}`);
      item.append(element("span", "", label), element("strong", "", allowed ? "فعال" : "غیرفعال"));
      list.append(item);
    });
    section.append(head, list);
    return section;
  }

  function renderUnitConversions() {
    const section = element("section", "settings-card settings-conversions");
    section.id = "unit-conversions";
    const head = element("div", "settings-card__head settings-card__head--actions");
    const copy = element("div", "settings-card__head-copy");
    copy.append(
      element("h2", "", "قواعد تبدیل واحد پروژه"),
      element("p", "", "اینجا فقط قواعد کاری متغیر، مانند ساعت هر روز دستگاه یا نفرروز، تعریف می‌شوند. تبدیل‌های ثابت وزن و طول قابل تغییر نیستند و هر قاعده فقط میان واحدهای هم‌بُعد اعمال می‌شود."),
    );
    head.append(element("div", "settings-card__icon", "↔"), copy);
    const editorHost = element("div", "settings-conversions__editor-host");
    if (capabilitiesFor(context).writeFinance) {
      const add = element("button", "button button--primary", "تعریف تبدیل کاری");
      add.type = "button";
      add.addEventListener("click", () => {
        conversionEditorOpen = !conversionEditorOpen;
        paint();
      });
      head.append(add);
    }
    if (conversionEditorOpen) {
      editorHost.append(createUnitConversionForm(pricesAdapter, conversionWorkspace, (next) => {
        conversionWorkspace = next;
        conversionEditorOpen = false;
        paint();
      }, () => {
        conversionEditorOpen = false;
        paint();
      }));
    }
    const configurableConversions = (conversionWorkspace?.currentConversions ?? []).filter((item) => isConfigurableConversionDirection(item.sourceUnit, item.targetUnit));
    const configurableHistory = (conversionWorkspace?.conversionHistory ?? []).filter((item) => isConfigurableConversionDirection(item.sourceUnit, item.targetUnit));
    const current = element("div", "settings-conversions__current");
    current.append(element("h3", "", "قواعد کاری فعال پروژه"));
    if (conversionError) {
      const error = element("div", "settings-conversions__error inline-notice");
      error.append(element("strong", "", "دریافت قواعد تبدیل انجام نشد."), element("span", "", conversionError.message ?? "ارتباط با سرویس تبدیل واحد برقرار نشد."));
      const retry = element("button", "button button--ghost", "تلاش مجدد");
      retry.type = "button";
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        try {
          conversionWorkspace = await pricesAdapter.getPrices();
          conversionError = null;
          paint();
        } catch (errorValue) {
          conversionError = errorValue;
          paint();
        }
      });
      error.append(retry);
      current.append(error);
    } else if (configurableConversions.length) current.append(renderCurrentConversions(configurableConversions));
    else current.append(element("p", "settings-empty-copy", "قاعده کاری قابل تنظیمی برای این پروژه ثبت نشده است."));
    const history = document.createElement("details");
    history.className = "settings-conversions__history";
    history.append(element("summary", "", "مشاهده تاریخچه نسخه‌های تبدیل واحد"));
    if (conversionError) history.hidden = true;
    else if (configurableHistory.length) history.append(renderConversionHistory(configurableHistory));
    else history.append(element("p", "settings-empty-copy", "تاریخچه‌ای برای تبدیل واحد وجود ندارد."));
    section.append(head, editorHost, current, history);
    return section;
  }

  function renderEditor(current) {
    const section = element("section", "settings-card settings-editor");
    const head = element("div", "settings-card__head");
    head.append(element("div", "settings-card__icon", "م²"), element("div", "", ""));
    head.lastElementChild.append(element("h2", "", current ? "اصلاح زیربنای کل" : "ثبت زیربنای کل"), element("p", "", current ? `مقدار فعلی: ${formatArea(current.grossBuiltArea)} · بازنگری ${formatDisplayNumber(String(current.revision))}` : "مقدار مثبت و دقیق زیربنای کل پروژه را وارد کنید."));

    const form = element("form", "settings-form");
    form.noValidate = true;
    const area = createField({ id: "grossBuiltArea", label: "زیربنای کل (مترمربع)", value: current?.grossBuiltArea ?? "", hint: "عدد مثبت با حداکثر چهار رقم اعشار؛ ارقام فارسی نیز پذیرفته می‌شوند.", inputMode: "decimal", required: true });
    const date = createPersianDatePicker({ id: "effectiveDate", label: "تاریخ اعمال تغییر", value: getTehranTodayIso(), hint: "تاریخ را براساس تقویم جلالی و زمان ایران انتخاب کنید." });
    const reasonField = element("div", "form-field form-field--wide");
    const reasonLabel = element("label", "form-label", "دلیل تغییر");
    reasonLabel.htmlFor = "reason";
    const reason = document.createElement("textarea");
    reason.id = "reason";
    reason.name = "reason";
    reason.rows = 3;
    reason.required = true;
    reason.placeholder = current ? "برای مثال: اصلاح زیربنا براساس نقشه مصوب جدید" : "برای مثال: ثبت اولیه براساس نقشه مصوب پروژه";
    reason.setAttribute("aria-describedby", "reason-hint reason-error");
    const reasonHint = element("small", "form-hint", "دلیل در تاریخچه مالی ذخیره می‌شود و بعداً قابل حذف نیست.");
    reasonHint.id = "reason-hint";
    const reasonError = element("small", "form-error");
    reasonError.id = "reason-error";
    reasonError.setAttribute("aria-live", "polite");
    reasonField.append(reasonLabel, reason, reasonHint, reasonError);

    const status = element("div", "form-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const submit = element("button", "button button--primary", current ? "ثبت بازنگری جدید" : "ثبت تنظیمات");
    submit.type = "submit";
    const actions = element("div", "form-actions");
    actions.append(submit, status);
    form.append(area.field, date.field, reasonField, actions);

    const dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog";
    dialog.setAttribute("aria-labelledby", "settings-confirm-title");
    const dialogTitle = element("h2", "", "تأیید تغییر زیربنا");
    dialogTitle.id = "settings-confirm-title";
    const dialogMessage = element("p", "", "این تغییر به‌صورت بازنگری جدید ثبت می‌شود و نسخه‌های ثبت‌شده قبلی گزارش‌ها را تغییر نمی‌دهد.");
    const dialogActions = element("div", "dialog-actions");
    const cancel = element("button", "button button--ghost", "لغو");
    cancel.type = "button";
    const confirm = element("button", "button button--primary", "تأیید و ثبت");
    confirm.type = "button";
    dialogActions.append(cancel, confirm);
    dialog.append(dialogTitle, dialogMessage, dialogActions);

    let pendingValues = null;
    function showErrors(errors) {
      area.error.textContent = errors.grossBuiltArea;
      date.error.textContent = errors.effectiveDate;
      reasonError.textContent = errors.reason;
      area.input.setAttribute("aria-invalid", String(Boolean(errors.grossBuiltArea)));
      date.input.setAttribute("aria-invalid", String(Boolean(errors.effectiveDate)));
      reason.setAttribute("aria-invalid", String(Boolean(errors.reason)));
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const validation = validateSettingsRevision({ grossBuiltArea: area.input.value, effectiveDate: date.getValue(), reason: reason.value });
      showErrors(validation.errors);
      if (!validation.valid) {
        status.textContent = "لطفاً خطاهای فرم را اصلاح کنید.";
        form.querySelector('[aria-invalid="true"]')?.focus();
        return;
      }
      pendingValues = validation.values;
      showAccessibleDialog(dialog);
    });
    cancel.addEventListener("click", () => dialog.close());
    confirm.addEventListener("click", async () => {
      if (!pendingValues) return;
      confirm.disabled = true;
      cancel.disabled = true;
      status.textContent = "در حال ثبت بازنگری…";
      try {
        settings = await adapter.updateGrossBuiltArea({ ...pendingValues, expectedRevision: current?.revision ?? 0 });
        state = createRequestState(REQUEST_STATUS.SUCCESS, settings);
        dialog.close();
        onSettingsUpdated(settings);
        paint();
      } catch (error) {
        dialog.close();
        status.textContent = formatApiErrorMessage(error);
      } finally {
        confirm.disabled = false;
        cancel.disabled = false;
      }
    });

    section.append(head, form, dialog);
    return section;
  }

  /**
   * The Backend ships `canEdit` on FinanceSettingsResponse so the UI does not
   * have to reimplement its role policy and then disagree with it — offering a
   * form the PATCH would refuse. Its verdict wins whenever it gives one; null
   * means the adapter in front of us did not answer, so the host permission
   * still decides.
   */
  function mayReviseArea(data) {
    return data?.canEdit ?? capabilitiesFor(context).writeFinance;
  }

  function renderRevisionDenied(current) {
    const section = element("section", "settings-card settings-editor settings-editor--denied");
    const head = element("div", "settings-card__head");
    head.append(element("div", "settings-card__icon", "م²"), element("div", "", ""));
    head.lastElementChild.append(
      element("h2", "", "اصلاح زیربنای کل"),
      element("p", "", current
        ? `مقدار فعلی: ${formatArea(current.grossBuiltArea)} · بازنگری ${formatDisplayNumber(String(current.revision))}`
        : "زیربنای کل هنوز ثبت نشده است."),
    );
    const notice = element("p", "inline-notice", "حساب شما اجازه اصلاح زیربنای کل این پروژه را ندارد؛ این مقدار و تاریخچه آن فقط برای مشاهده است.");
    section.append(head, notice);
    return section;
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();
    // Nothing below this point is reachable without a settings record, and the
    // reader-only view does not have one.
    if (readerOnly) {
      const readerGrid = element("div", "settings-primary-grid");
      readerGrid.append(renderCurrencyPolicy(), renderAccessSummary());
      fragment.append(readerGrid);
      return fragment;
    }
    const overview = element("section", "settings-overview");
    const areaCard = element("article", "settings-overview__item");
    areaCard.append(element("span", "", "زیربنای کل فعلی"), element("strong", "numeric", formatArea(data.grossBuiltArea)), element("small", "", `بازنگری ${data.revision}`));
    const currencyCard = element("article", "settings-overview__item");
    currencyCard.append(element("span", "", "واحد نمایش مبالغ"), element("strong", "", getDisplayCurrencyLabel()), element("small", "", "قابل تغییر برای تمام بخش‌های مالی"));
    const conversionCard = element("article", "settings-overview__item");
    const configurableCount = (conversionWorkspace?.currentConversions ?? []).filter((item) => isConfigurableConversionDirection(item.sourceUnit, item.targetUnit)).length;
    conversionCard.append(element("span", "", "قواعد کاری فعال"), element("strong", "numeric", formatDisplayNumber(String(configurableCount))), element("small", "", "قواعد قابل تنظیم سازمان و پروژه"));
    const latestSettingsDate = [
      data.revisions?.[0]?.effectiveDate ?? data.effectiveFrom,
      ...(conversionWorkspace?.conversionHistory ?? []).map((item) => item.effectiveDate),
    ].filter(Boolean).sort((left, right) => right.localeCompare(left))[0] ?? null;
    const revisionCard = element("article", "settings-overview__item");
    revisionCard.append(element("span", "", "آخرین تغییر تنظیمات"), element("strong", "", latestSettingsDate ? formatBusinessDate(latestSettingsDate) : "بدون تغییر"), element("small", "", "زیربنا یا قواعد تبدیل واحد"));
    overview.append(areaCard, currencyCard, conversionCard, revisionCard);

    const history = element("section", "settings-card settings-history-card");
    const historyHead = element("div", "settings-card__head");
    historyHead.append(element("div", "settings-card__icon", "↺"), element("div", "", ""));
    historyHead.lastElementChild.append(element("h2", "", "تاریخچه تغییر زیربنا"), element("p", "", "مقدار اولیه و همه اصلاحات ثبت‌شده به‌صورت تغییرناپذیر نمایش داده می‌شوند."));
    history.append(historyHead, createRevisionHistory(data));
    const primaryGrid = element("div", "settings-primary-grid");
    primaryGrid.append(renderCurrencyPolicy(), renderAccessSummary());
    const editor = mayReviseArea(data) ? renderEditor(data) : renderRevisionDenied(data);
    fragment.append(overview, primaryGrid, editor, renderUnitConversions(), history);
    return fragment;
  }

  function paint() {
    // The Backend serves GET /settings and GET /settings/revisions to
    // finance.view and asks for the edit permission only on PATCH, so reading
    // is gated on reading. Whether the form is offered is a separate question,
    // and `canEdit` answers it.
    const contentState = capabilitiesFor(context).viewFinance ? state : createRequestState(REQUEST_STATUS.DENIED);
    root.replaceChildren(renderHeader(), renderPageState(contentState, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
