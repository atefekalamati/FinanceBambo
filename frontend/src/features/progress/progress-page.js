import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { formatBusinessDate, formatDisplayNumber, formatSystemDateTime, formatUnitLabel } from "../../shared/formatters/display.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";
import { capabilitiesFor } from "../../core/auth/capabilities.js";
import { calculateProgressDeviation, validateProgressOverride } from "./progress-validation.js";
import { element } from "../../shared/dom/elements.js";
import { feedWarningText } from "../../shared/warnings/finance-warning-labels.js";

const STATUS_LABELS = Object.freeze({ ready: "آماده", superseded: "جایگزین‌شده" });
const RESOURCE_TYPE_LABELS = Object.freeze({ material: "مصالح", labor: "نیروی انسانی", equipment: "دستگاه و تجهیزات", general_cost: "هزینه‌های عمومی پروژه" });
const SOURCE_METHOD_LABELS = Object.freeze({
  assignment_actual: "مقدار واقعی تخصیص",
  assignment_work_percent: "درصد پیشرفت تخصیص",
  task_progress_fallback: "درصد پیشرفت فعالیت",
  manual_override: "جایگزینی دستی",
  excel_import: "ورود اکسل",
  manual_entry: "ورود دستی",
});
const qualityFormatter = new Intl.NumberFormat("fa-IR", { style: "percent", maximumFractionDigits: 0 });

function valueOrMissing(value) {
  return value === null || value === undefined ? "داده موجود نیست" : formatDisplayNumber(value);
}

function dateOrMissing(value) {
  return value ? formatBusinessDate(value) : "داده موجود نیست";
}

/**
 * What the Backend said about this assignment, first and verbatim by code.
 *
 * The feed carries a `warnings` array per assignment — PROGRESS_MISSING and
 * TASK_PROGRESS_FALLBACK — and this page used to ignore it entirely and
 * re-derive its own list from sourceMethod and quality. Reading the Backend's
 * codes means the page reports what the service decided rather than guessing at
 * it, and a code the service adds later still reaches the reader.
 *
 * Two notes are still made here, and neither is an inference about the data:
 * a manual override is not a Backend warning at all (it is a sourceMethod), and
 * the quality threshold is a display policy — the Backend publishes the number
 * and has no opinion about when it is too low.
 */
const LOW_QUALITY_THRESHOLD = 0.8;

function assignmentWarnings(assignment) {
  const warnings = (assignment.warnings ?? []).map(feedWarningText).filter(Boolean);

  if (assignment.sourceMethod === "manual_override") warnings.push("مقدار با جایگزینی دستی تعیین شده و مقدار محاسبه‌شده اصلی حفظ شده است.");
  // `quality` arrives as a decimal string; Number keeps the comparison explicit.
  const quality = Number(assignment.quality);
  if (Number.isFinite(quality) && quality < LOW_QUALITY_THRESHOLD) {
    warnings.push(`کیفیت این مقدار ${qualityFormatter.format(quality)} است و پایین‌تر از حد قابل اتکا قرار دارد.`);
  }
  const deviation = calculateProgressDeviation(assignment.actualQuantity, assignment.plannedQuantity);
  if (deviation) {
    const percent = deviation.percent === null ? "درصد انحراف به‌دلیل برآورد صفر قابل محاسبه نیست" : `${formatDisplayNumber(deviation.percent)} درصد`;
    warnings.push(`مقدار اجرا ${formatDisplayNumber(deviation.amount)} ${formatUnitLabel(assignment.unit)} بیشتر از برآورد است؛ انحراف ${percent}.`);
  }
  return warnings;
}

function renderSnapshotList(snapshots, selectedId, onSelect) {
  const list = element("div", "progress-snapshot-list");
  snapshots.forEach((snapshot) => {
    const card = element("article", `progress-snapshot-card ${snapshot.progressSnapshotId === selectedId ? "progress-snapshot-card--selected" : ""}`);
    const head = element("div", "progress-snapshot-card__head");
    head.append(element("strong", "", `تاریخ گزارش ${formatBusinessDate(snapshot.reportingDate)}`), element("span", `snapshot-status snapshot-status--${snapshot.status}`, STATUS_LABELS[snapshot.status] ?? "وضعیت نامشخص"));
    const file = element("p", "progress-snapshot-card__file", snapshot.sourceFileNameSafe);
    const meta = element("dl", "progress-snapshot-card__meta");
    const fields = [
      ["زمان ورود", formatSystemDateTime(snapshot.importedAt)],
      ["شناسه نسخه پیشرفت پروژه", snapshot.progressSnapshotId],
      ["شناسه نسخه فایل", snapshot.sourceFileVersionId],
    ];
    fields.forEach(([label, value]) => meta.append(element("dt", "", label), element("dd", "numeric", value)));
    const button = element("button", snapshot.progressSnapshotId === selectedId ? "button button--primary" : "button button--ghost", snapshot.progressSnapshotId === selectedId ? "در حال نمایش" : "مشاهده پیشرفت اجرایی");
    button.type = "button";
    button.disabled = snapshot.progressSnapshotId === selectedId;
    button.addEventListener("click", () => onSelect(snapshot.progressSnapshotId));
    card.append(head, file, meta, button);
    list.append(card);
  });
  return list;
}

function renderSnapshotMetadata(snapshot, assignmentCount) {
  const section = element("section", "progress-metadata");
  const title = element("div", "progress-section-heading");
  title.append(element("div", "", ""), element("span", "read-only-badge", "فقط‌خواندنی"));
  title.firstElementChild.append(element("h2", "", "مشخصات نسخه انتخاب‌شده"), element("p", "", "این داده توسط ماژول گزارش پیشرفت تولید شده و در ماژول مالی قابل تغییر نیست."));
  const grid = element("dl", "progress-metadata__grid");
  const rows = [
    ["تاریخ گزارش", formatBusinessDate(snapshot.reportingDate)],
    ["وضعیت", STATUS_LABELS[snapshot.status] ?? "وضعیت نامشخص"],
    ["نام امن فایل مبدأ", snapshot.sourceFileNameSafe],
    ["تعداد تخصیص", formatDisplayNumber(String(assignmentCount))],
    ["زمان ورود", formatSystemDateTime(snapshot.importedAt)],
    ["ثبت‌کننده ورود", snapshot.importedBy],
    ["شناسه نسخه پیشرفت پروژه", snapshot.progressSnapshotId],
    ["شناسه نسخه فایل", snapshot.sourceFileVersionId],
  ];
  rows.forEach(([label, value]) => {
    const item = element("div", "progress-metadata__item");
    item.append(element("dt", "", label), element("dd", "", value));
    grid.append(item);
  });
  section.append(title, grid);
  return section;
}

function renderOverrideDetails(override) {
  if (!override) return element("span", "missing-value", "ثبت نشده");
  const details = document.createElement("details");
  details.className = "override-details";
  details.append(element("summary", "", "مشاهده جزئیات"));
  const list = element("dl", "override-details__list");
  [
    ["مقدار محاسبه‌شده", formatDisplayNumber(override.previousCalculatedValue)],
    ["مقدار جایگزین", formatDisplayNumber(override.newValue)],
    ["دلیل", override.reason],
    ["کاربر", override.userId],
    ["زمان", formatSystemDateTime(override.occurredAt)],
    ["شناسه نسخه پیشرفت پروژه", override.progressSnapshotId],
  ].forEach(([label, value]) => list.append(element("dt", "", label), element("dd", "", value)));
  details.append(list);
  return details;
}

function fieldError(message) {
  const error = element("small", "field-error", message);
  error.setAttribute("role", "alert");
  return error;
}

function createOverrideDialog({ assignment, snapshotId, adapter, onSaved }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog progress-override-dialog";
  dialog.setAttribute("aria-labelledby", "progress-override-title");
  const title = element("h2", "", "ثبت جایگزینی دستی پیشرفت");
  title.id = "progress-override-title";
  const description = element("p", "", "مقدار محاسبه‌شده حذف یا بازنویسی نمی‌شود و اصلاح دستی با دلیل، انجام‌دهنده، زمان و نسخه پیشرفت پروژه ثبت خواهد شد.");
  const summary = element("dl", "progress-override-summary");
  [
    ["فعالیت", assignment.task.taskName],
    ["قلم هزینه", assignment.resourceName],
    ["مقدار محاسبه‌شده", valueOrMissing(assignment.manualOverride?.previousCalculatedValue ?? assignment.actualQuantity)],
    ["مقدار برنامه", valueOrMissing(assignment.plannedQuantity)],
    ["واحد", formatUnitLabel(assignment.unit)],
  ].forEach(([label, value]) => summary.append(element("dt", "", label), element("dd", "", value)));

  // The trail is loaded on demand: it is only meaningful once a line has been
  // overridden before, and most have not.
  const trail = element("details", "progress-override-trail");
  const trailSummary = element("summary", "", "سابقه جایگزینی‌های این ردیف");
  const trailBody = element("div", "progress-override-trail__body", "برای مشاهده باز کنید.");
  trail.append(trailSummary, trailBody);
  let trailLoaded = false;
  trail.addEventListener("toggle", async () => {
    if (!trail.open || trailLoaded) return;
    trailLoaded = true;
    trailBody.textContent = "در حال دریافت سابقه…";
    try {
      const history = await adapter.getOverrideHistory({
        assignmentExternalId: assignment.assignmentExternalId,
        activityExternalId: assignment.task?.activityCode ?? null,
      });
      if (!history.length) {
        trailBody.textContent = "برای این ردیف جایگزینی دستی ثبت نشده است.";
        return;
      }
      const list = element("ol", "progress-override-trail__list");
      history.forEach((entry) => {
        const item = document.createElement("li");
        item.append(
          element("strong", "numeric", `${formatDisplayNumber(entry.previousCalculatedValue ?? "—")} ← ${formatDisplayNumber(entry.newValue)}`),
          element("span", "", entry.reason || "بدون دلیل ثبت‌شده"),
          element("small", "", `${entry.userId ?? "کاربر نامشخص"} · ${entry.occurredAt ? formatSystemDateTime(entry.occurredAt) : "زمان نامشخص"}`),
        );
        list.append(item);
      });
      trailBody.replaceChildren(list);
    } catch (error) {
      trailLoaded = false;
      trailBody.textContent = formatApiErrorMessage(error, "دریافت سابقه جایگزینی انجام نشد.");
    }
  });

  const form = element("form", "progress-override-form");
  form.noValidate = true;
  const valueField = element("label", "form-field");
  valueField.append(element("span", "", "مقدار جایگزین"));
  const valueInput = element("input", "app-input numeric");
  valueInput.name = "overrideValue";
  valueInput.inputMode = "decimal";
  valueInput.autocomplete = "off";
  valueInput.setAttribute("aria-describedby", "progress-override-value-help");
  const valueHelp = element("small", "field-help", "عدد مثبت با حداکثر چهار رقم اعشار");
  valueHelp.id = "progress-override-value-help";
  valueField.append(valueInput, valueHelp);
  const reasonField = element("label", "form-field");
  reasonField.append(element("span", "", "دلیل اصلاح دستی"));
  const reasonInput = element("textarea", "app-textarea");
  reasonInput.name = "reason";
  reasonInput.rows = 4;
  reasonInput.maxLength = 500;
  reasonField.append(reasonInput);
  const warning = element("div", "inline-notice progress-override-warning");
  warning.hidden = true;
  warning.setAttribute("role", "alert");
  const result = element("div", "form-message");
  result.setAttribute("aria-live", "polite");
  const actions = element("div", "dialog-actions");
  const cancel = element("button", "button button--ghost", "انصراف");
  cancel.type = "button";
  cancel.addEventListener("click", () => dialog.close());
  const submit = element("button", "button button--primary", "ثبت جایگزینی");
  submit.type = "submit";
  actions.append(cancel, submit);
  form.append(valueField, reasonField, warning, result, actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    valueField.querySelector(".field-error")?.remove();
    reasonField.querySelector(".field-error")?.remove();
    result.textContent = "";
    const validation = validateProgressOverride({ value: valueInput.value, reason: reasonInput.value, plannedQuantity: assignment.plannedQuantity });
    if (validation.errors.value) valueField.append(fieldError(validation.errors.value));
    if (validation.errors.reason) reasonField.append(fieldError(validation.errors.reason));
    warning.hidden = !validation.exceedsPlan;
    if (validation.exceedsPlan) {
      const percent = validation.deviation.percent === null ? "قابل محاسبه نیست" : `${formatDisplayNumber(validation.deviation.percent)} درصد`;
      warning.textContent = `مقدار واردشده ${formatDisplayNumber(validation.deviation.amount)} ${formatUnitLabel(assignment.unit)} بیشتر از برآورد است و انحراف ${percent} خواهد بود. ثبت مسدود نمی‌شود و دلیل در تاریخچه تغییرات حفظ خواهد شد.`;
    } else {
      warning.textContent = "";
    }
    if (!validation.valid) return;

    submit.disabled = true;
    cancel.disabled = true;
    submit.textContent = "در حال ثبت…";
    try {
      const response = await adapter.createOverride({
        progressSnapshotId: snapshotId,
        assignmentExternalId: assignment.assignmentExternalId,
        activityExternalId: assignment.task?.activityCode ?? null,
        overrideValue: validation.value,
        reason: validation.reason,
      });
      dialog.close();
      onSaved(response.feed);
    } catch (error) {
      result.textContent = formatApiErrorMessage(error, "ثبت جایگزینی انجام نشد.");
      result.className = "form-message form-message--error";
    } finally {
      submit.disabled = false;
      cancel.disabled = false;
      submit.textContent = "ثبت جایگزینی";
    }
  });

  dialog.append(title, description, summary, trail, form);
  return dialog;
}

function renderAssignments(assignments, { canOverride, onOverride }) {
  const wrapper = element("div", "table-scroll");
  const table = element("table", "data-table progress-feed-table");
  table.append(element("caption", "sr-only", "اطلاعات فقط‌خواندنی پیشرفت اجرایی و تخصیص‌های مالی"));
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  ["فعالیت", "قلم هزینه", "واحد", "مقادیر برنامه، انجام‌شده و باقی‌مانده", "کار برنامه، انجام‌شده و باقی‌مانده", "درصدهای پیشرفت", "مبنای محاسبه و کیفیت", "بازه فعالیت", "اصلاح دستی مقدار"].forEach((label) => header.append(element("th", "", label)));
  head.append(header);
  const body = document.createElement("tbody");
  assignments.forEach((assignment) => {
    const row = document.createElement("tr");
    const task = document.createElement("td");
    task.append(element("strong", "", assignment.task.taskName), element("small", "table-subtext numeric", `${assignment.task.wbsCode ?? "ساختار شکست موجود نیست"} · ${assignment.task.activityCode ?? "کد فعالیت موجود نیست"}`), element("small", "table-subtext numeric", `شناسه فعالیت: ${assignment.task.taskExternalId}`), element("small", "table-subtext numeric", `فعالیت والد: ${assignment.task.parentTaskExternalId ?? "ندارد"}`));
    const resource = document.createElement("td");
    resource.append(element("strong", "", assignment.resourceName), element("small", "table-subtext", RESOURCE_TYPE_LABELS[assignment.resourceType] ?? "نوع نامشخص"), element("small", "table-subtext numeric", `قلم: ${assignment.resourceExternalId}`), element("small", "table-subtext numeric", `تخصیص: ${assignment.assignmentExternalId}`));
    const quantities = element("dl", "feed-values");
    [["برنامه", assignment.plannedQuantity], ["واقعی", assignment.actualQuantity], ["باقی‌مانده", assignment.remainingQuantity]].forEach(([label, value]) => quantities.append(element("dt", "", label), element("dd", value === null ? "missing-value" : "numeric", valueOrMissing(value))));
    const work = element("dl", "feed-values");
    [["برنامه", assignment.plannedWork], ["واقعی", assignment.actualWork], ["باقی‌مانده", assignment.remainingWork]].forEach(([label, value]) => work.append(element("dt", "", label), element("dd", value === null ? "missing-value" : "numeric", valueOrMissing(value))));
    const percents = element("dl", "feed-values");
    [["تخصیص", assignment.assignmentWorkCompletePercent], ["فعالیت", assignment.task.taskProgressPercent]].forEach(([label, value]) => percents.append(element("dt", "", label), element("dd", value === null ? "missing-value" : "numeric", value === null ? "داده موجود نیست" : `${formatDisplayNumber(value)} درصد`)));
    const source = document.createElement("td");
    source.append(element("strong", "", SOURCE_METHOD_LABELS[assignment.sourceMethod] ?? "روش نامشخص"), element("small", "quality-badge", `کیفیت ${qualityFormatter.format(assignment.quality)}`));
    const warnings = assignmentWarnings(assignment);
    if (warnings.length) {
      const list = element("ul", "feed-warnings");
      warnings.forEach((warning) => list.append(element("li", "", warning)));
      source.append(list);
    }
    const dates = element("dl", "feed-values");
    dates.append(element("dt", "", "شروع"), element("dd", assignment.task.taskStart ? "" : "missing-value", dateOrMissing(assignment.task.taskStart)), element("dt", "", "پایان"), element("dd", assignment.task.taskFinish ? "" : "missing-value", dateOrMissing(assignment.task.taskFinish)));
    const override = document.createElement("td");
    override.append(renderOverrideDetails(assignment.manualOverride));
    // A disabled button on every row of a long table is noise for an account
    // that will never be able to press one, and it invites the reading that the
    // interface is what stops them. The row still shows the reported quantity
    // and any override already recorded on it.
    if (canOverride && assignment.actualQuantity !== null && assignment.resourceType !== "general_cost") {
      const button = element("button", "button button--small button--ghost progress-override-button", "اصلاح دستی مقدار");
      button.type = "button";
      button.addEventListener("click", () => onOverride(assignment));
      override.append(button);
    }
    row.append(task, resource, element("td", "", formatUnitLabel(assignment.unit)), element("td", "", ""), element("td", "", ""), element("td", "", ""), source, element("td", "", ""), override);
    row.children[3].append(quantities);
    row.children[4].append(work);
    row.children[5].append(percents);
    row.children[7].append(dates);
    body.append(row);
  });
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function createProgressPage({ context, adapter }) {
  const root = element("div", "progress-page");
  let snapshotsState = createRequestState(REQUEST_STATUS.LOADING);
  let feedState = createRequestState(REQUEST_STATUS.IDLE);
  let selectedId = null;
  const canOverride = capabilitiesFor(context).writeFinance;

  async function selectSnapshot(snapshotId) {
    selectedId = snapshotId;
    feedState = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const feed = await adapter.getFeed(snapshotId);
      feedState = createRequestState(feed.assignments.length ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, feed);
    } catch (error) {
      feedState = createRequestState(REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  async function load() {
    snapshotsState = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      const snapshots = await adapter.getSnapshots();
      snapshotsState = createRequestState(snapshots.length ? REQUEST_STATUS.SUCCESS : REQUEST_STATUS.EMPTY, snapshots);
      if (snapshots.length) await selectSnapshot(snapshots[0].progressSnapshotId);
    } catch (error) {
      snapshotsState = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
      paint();
    }
  }

  function renderHeader() {
    const header = element("header", "feature-header");
    const copy = element("div", "feature-header__copy");
    copy.append(element("span", "feature-header__eyebrow", "پیشرفت اجرایی پروژه"), element("h1", "", "نسخه‌های پیشرفت پروژه"), element("p", "", "نسخه‌های ثبت‌شده گزارش پیشرفت و تخصیص‌های فعالیت و قلم هزینه را به‌صورت فقط‌خواندنی مشاهده کنید."));
    const back = element("a", "button button--ghost", "بازگشت به امور مالی");
    back.classList.add("finance-back-link");
    back.href = "#/finance";
    const navigation = element("div", "feature-header__navigation");
    const otherActions = element("div", "feature-header__other-actions");
    navigation.append(otherActions, back);
    header.append(copy, navigation);
    return header;
  }

  function renderEmpty() {
    const card = element("section", "state-card progress-empty");
    card.append(element("h2", "", "نسخه پیشرفت پروژه موجود نیست"), element("p", "", "ماژول مالی فایل برنامه را مستقیماً باز نمی‌کند. پس از انتشار نسخه توسط گزارش پیشرفت، اطلاعات فقط‌خواندنی پیشرفت اجرایی اینجا نمایش داده می‌شود."));
    return card;
  }

  function renderFeed(feed) {
    const fragment = document.createDocumentFragment();
    fragment.append(renderSnapshotMetadata(feed.snapshot, feed.assignments.length));
    const section = element("section", "progress-feed-section");
    const head = element("div", "progress-section-heading");
    head.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(feed.assignments.length))));
    head.firstElementChild.append(element("h2", "", "تخصیص‌های مالی"), element("p", "", "هر اتصال فعالیت و قلم هزینه یک ردیف مستقل است؛ مقدار ثبت‌نشده هرگز به صفر تبدیل نمی‌شود."));
    section.append(head, renderAssignments(feed.assignments, {
      canOverride,
      onOverride: (assignment) => {
        const dialog = createOverrideDialog({
          assignment,
          snapshotId: feed.snapshot.progressSnapshotId,
          adapter,
          onSaved: (nextFeed) => {
            feedState = createRequestState(REQUEST_STATUS.SUCCESS, nextFeed);
            paint();
          },
        });
        root.append(dialog);
        showAccessibleDialog(dialog);
      },
    }));
    fragment.append(section);
    return fragment;
  }

  function renderContent(items) {
    const fragment = document.createDocumentFragment();
    const notice = element("div", "inline-notice progress-readonly-notice", "این صفحه فقط مصرف‌کننده Feed نسخه‌دار است؛ هیچ فایل ام‌پی‌پی در ماژول مالی Parse و هیچ داده‌ای در گزارش پیشرفت ویرایش نمی‌شود.");
    const snapshots = element("section", "progress-snapshots-section");
    const heading = element("div", "progress-section-heading");
    heading.append(element("div", "", ""), element("span", "section-count numeric", formatDisplayNumber(String(items.length))));
    heading.firstElementChild.append(element("h2", "", "فهرست نسخه‌های پیشرفت"), element("p", "", "نسخه موردنظر را برای مشاهده مشخصات و اطلاعات تخصیص‌ها انتخاب کنید."));
    snapshots.append(heading, renderSnapshotList(items, selectedId, selectSnapshot));
    const feed = element("div", "progress-feed-state");
    if (feedState.status !== REQUEST_STATUS.IDLE) feed.append(renderPageState(feedState, { renderContent: renderFeed, renderEmpty: () => element("section", "state-card", "این نسخه تخصیص مالی ندارد."), onRetry: () => selectSnapshot(selectedId) }));
    fragment.append(notice, snapshots, feed);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderHeader(), renderPageState(snapshotsState, { renderContent, renderEmpty, onRetry: load }));
  }

  load();
  return root;
}
