import { element } from "../../shared/dom/elements.js";
import { showAccessibleDialog } from "../../shared/components/accessible-dialog.js";
import { createPersianDatePicker } from "../../shared/components/persian-date-picker.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { buildPeriodPresets, matchPreset, validatePeriod } from "../../shared/dates/reporting-periods.js";
import { REPORT_CATEGORIES, findReport, normalizeSelection, reportsByCategory } from "./report-catalog.js";
import { chevronIcon } from "./report-icons.js";

/**
 * Choosing what goes in the document.
 *
 * Two levels, the way the host platform's own builder does it: the popup opens
 * on a list of subjects, and choosing one replaces the list with that subject's
 * reports and a way back. It is not an accordion — only one category is on
 * screen at a time, so the choice is always a short list rather than a scroll
 * through every category at once.
 *
 * What is ticked survives moving between categories, because the selection is
 * held here and the level-two markup is rebuilt from it each time. A category
 * tile carries a count of what is chosen inside it, so nothing a reader picked
 * disappears from view when they go looking in another subject.
 *
 * Nothing is produced until at least one report is chosen, and the button says
 * so rather than failing after the click.
 */
export function createReportBuilderDialog({ preselected = [], onBuild }) {
  const dialog = document.createElement("dialog");
  dialog.className = "confirm-dialog report-builder-dialog";

  const selected = new Set(normalizeSelection(preselected));
  const presets = buildPeriodPresets(getTehranTodayIso());
  let period = presets.find((preset) => preset.key === "yearToDate")?.range
    ?? { from: getTehranTodayIso(), to: getTehranTodayIso() };

  const bar = element("header", "report-builder-dialog__bar");
  const barTitle = element("h2", "", "ساخت گزارش اختصاصی");
  barTitle.id = "report-builder-dialog-title";
  const close = element("button", "report-builder-dialog__close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "بستن");
  close.addEventListener("click", () => dialog.close());
  bar.append(barTitle, close);

  const panel = element("section", "report-builder-panel");
  const head = element("div", "report-builder-panel__head");
  const title = element("h3", "report-builder-panel__title");
  title.append(element("span", "report-builder-panel__star", "★"), document.createTextNode(" گزارش‌ساز هوشمند"));
  const info = element("span", "report-builder-panel__info", "i");
  info.setAttribute("role", "img");
  info.setAttribute("aria-label", "راهنما");
  info.title = "هر بخشی که انتخاب کنید یک فصل شماره‌دار از سند نهایی می‌شود؛ ترتیب فصل‌ها ثابت است.";
  head.append(title, info);
  panel.append(head, element("p", "report-builder-panel__lead", "یک دسته را انتخاب کنید، گزارش‌های آن را برگزینید، سپس گزارش اختصاصی خود را در قالب PDF بسازید."));

  const groups = element("ul", "report-builder-groups");
  const build = element("button", "button button--primary report-builder-panel__build");
  build.type = "button";
  build.append(element("span", "report-builder-panel__star", "★"), document.createTextNode(" ساخت گزارش اختصاصی"));
  const hint = element("p", "report-builder-panel__hint");

  function refresh() {
    const count = selected.size;
    build.disabled = count === 0;
    hint.textContent = count === 0
      ? "حداقل یک گزارش را برای ساخت PDF انتخاب کنید."
      : `${formatDisplayNumber(String(count))} گزارش انتخاب شده است.`;
    // The counts live on the category tiles now, not in the list above them.
    panel.querySelectorAll("[data-group-count]").forEach((badge) => {
      const chosen = reportsByCategory(badge.dataset.groupCount).filter((report) => selected.has(report.key)).length;
      badge.textContent = chosen ? formatDisplayNumber(String(chosen)) : "";
      badge.hidden = chosen === 0;
    });
  }

  /* ── The period, as its own row so the list keeps one shape ───────────── */
  const periodRow = element("li");
  const periodGroup = document.createElement("details");
  periodGroup.className = "report-builder-group";
  const periodSummary = document.createElement("summary");
  periodSummary.className = "report-builder-group__summary";
  const periodChevron = chevronIcon("forward");
  periodChevron.setAttribute("class", "report-builder-group__chevron");
  periodSummary.append(
    element("span", "report-builder-group__title", "بازه گزارش"),
    element("span", "report-builder-group__meta"),
    periodChevron,
  );
  const periodMeta = periodSummary.querySelector(".report-builder-group__meta");
  const periodBody = element("div", "report-builder-group__body");
  const presetRow = element("div", "report-builder-presets");
  const fromPicker = createPersianDatePicker({ id: "reportBuilderFrom", label: "از تاریخ", value: period.from });
  const toPicker = createPersianDatePicker({ id: "reportBuilderTo", label: "تا تاریخ", value: period.to });
  const periodError = element("p", "field-error");
  periodError.setAttribute("role", "alert");

  function syncPeriodMeta() {
    periodMeta.textContent = `${formatBusinessDate(period.from)} تا ${formatBusinessDate(period.to)}`;
    const active = matchPreset(presets, period);
    presetRow.querySelectorAll("button").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.preset === active);
    });
  }

  presets.forEach((preset) => {
    const button = element("button", "button button--small button--ghost", preset.label);
    button.type = "button";
    button.dataset.preset = preset.key;
    button.addEventListener("click", () => {
      period = { ...preset.range };
      fromPicker.setValue(period.from);
      toPicker.setValue(period.to);
      periodError.textContent = "";
      syncPeriodMeta();
    });
    presetRow.append(button);
  });
  // The picker writes its value straight into a read-only input and announces
  // nothing, so the two dates are read back when they are needed rather than
  // watched. `readPeriod` is what the build button calls before it decides.
  const readPeriod = () => {
    period = { from: fromPicker.getValue(), to: toPicker.getValue() };
    const validation = validatePeriod(period);
    periodError.textContent = validation.valid ? "" : (validation.errors.to ?? validation.errors.from ?? "");
    syncPeriodMeta();
    return validation;
  };
  periodBody.addEventListener("click", () => queueMicrotask(readPeriod));
  periodBody.append(presetRow, fromPicker.field, toPicker.field, periodError);
  periodBody.append(element("p", "report-builder-group__note", "بازه فقط بر بخش‌هایی اثر دارد که رویداد یا سند یک دوره را گزارش می‌کنند؛ شاخص‌های وضعیت همیشه در تاریخ گزارش نسخه پیشرفت محاسبه می‌شوند."));
  periodGroup.append(periodSummary, periodBody);
  periodRow.append(periodGroup);
  groups.append(periodRow);
  syncPeriodMeta();
  // The period is a setting for the whole document, not one of the subjects,
  // so it stays above them — and steps aside while a subject is open.

  /* ── Level one: the subjects ──────────────────────────────────────────── */
  const cats = element("div", "report-builder-cats");
  const level2 = element("div", "report-builder-level2");
  level2.hidden = true;
  const level2Title = element("h4", "report-builder-level2__title");
  const level2Note = element("p", "report-builder-level2__note");
  const level2Items = element("div", "report-builder-level2__items");
  const back = element("button", "report-builder-back");
  back.type = "button";
  back.setAttribute("aria-label", "بازگشت به فهرست دسته‌ها");
  const backChevron = chevronIcon("back");
  backChevron.setAttribute("class", "report-builder-back__chevron");
  back.append(backChevron, document.createTextNode(" بازگشت به دسته‌ها"));
  back.addEventListener("click", showLevelOne);
  level2.append(back, level2Title, level2Note, level2Items);

  REPORT_CATEGORIES.forEach((category) => {
    const reports = reportsByCategory(category.key);
    if (!reports.length) return;
    const tile = element("button", "report-builder-cat");
    tile.type = "button";
    tile.dataset.category = category.key;
    const badge = element("span", "report-builder-cat__badge");
    badge.dataset.groupCount = category.key;
    badge.hidden = true;
    const chevron = chevronIcon("forward");
    chevron.setAttribute("class", "report-builder-cat__chevron");
    tile.append(element("span", "report-builder-cat__title", category.title), badge, chevron);
    tile.addEventListener("click", () => openCategory(category));
    cats.append(tile);
  });

  /* ── Level two: one subject's reports ─────────────────────────────────── */
  function openCategory(category) {
    level2Title.textContent = category.title;
    level2Note.textContent = category.description;
    level2Items.replaceChildren();
    reportsByCategory(category.key).forEach((report) => {
      const option = element("label", `report-builder-option${report.unavailable ? " report-builder-option--unavailable" : ""}`);
      if (report.unavailable) option.title = report.unavailable;
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = report.key;
      box.checked = selected.has(report.key);
      box.disabled = Boolean(report.unavailable);
      box.addEventListener("change", () => {
        if (box.checked) selected.add(report.key);
        else selected.delete(report.key);
        option.classList.toggle("is-checked", box.checked);
        refresh();
      });
      option.classList.toggle("is-checked", box.checked);
      const copy = element("span", "report-builder-option__copy");
      copy.append(element("strong", "", report.title), element("small", "", report.unavailable ?? report.summary));
      option.append(box, copy);
      level2Items.append(option);
    });
    cats.hidden = true;
    periodRow.hidden = true;
    level2.hidden = false;
    back.focus();
  }

  function showLevelOne() {
    level2.hidden = true;
    cats.hidden = false;
    periodRow.hidden = false;
    refresh();
  }

  build.addEventListener("click", () => {
    if (!selected.size) return;
    const validation = readPeriod();
    if (!validation.valid) {
      showLevelOne();
      periodGroup.open = true;
      periodError.textContent = validation.errors.to ?? validation.errors.from ?? "";
      return;
    }
    dialog.close();
    onBuild({ selection: normalizeSelection([...selected]), period });
  });

  panel.append(groups, cats, level2, hint, build);
  const body = element("div", "report-builder-dialog__body");
  body.append(panel);
  dialog.append(bar, body);
  refresh();
  return dialog;
}

export function openReportBuilder({ preselected, onBuild }) {
  const dialog = createReportBuilderDialog({ preselected, onBuild });
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  showAccessibleDialog(dialog);
  return dialog;
}

export { findReport };
