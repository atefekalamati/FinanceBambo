import { element } from "../../shared/dom/elements.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";
import { formatApiErrorMessage } from "../../shared/errors/error-presentation.js";

/* The one place a person can ask the schedule to become estimate lines.
 *
 * WHY A BUTTON EXISTS AT ALL
 * Reading the file and turning it into money are two steps, and only the first ran on its
 * own. `finance_mpp_sync` writes the file's rows whenever the file changes; the mapping
 * that turns those rows into resources and estimate lines used to run only as a side
 * effect of somebody classifying a resource — and this module has no screen for that. So
 * a schedule could sit fully imported and produce nothing, which is exactly what happened
 * here: the file states 5,148,488,006 toman of task-level fixed costs and the project
 * total was short by precisely that.
 *
 * An import now maps itself. This button is for the case the automatic pass cannot cover:
 * a file that has not changed since the service learned to read something new from it —
 * and an unattended import, which names no actor and therefore writes no line at all.
 *
 * WHY IT IS SAFE TO PRESS TWICE
 * Every write the service makes is keyed on the file's own identifiers, so a second run
 * reports what it matched and inserts nothing. The panel says so in words rather than
 * assuming the reader knows, because a button that writes and gives no account of itself
 * invites nobody to press it.
 */

/** The counts, in the order a reader wants them: what the file has, then what became of it. */
export function scheduleSummary(status) {
  if (!status) return [];
  const count = (value) => formatDisplayNumber(String(value ?? 0));
  return [
    { key: "total", label: "ردیف در فایل", value: count(status.total) },
    { key: "assignmentMapped", label: "متصل به تخصیص", value: count(status.assignmentMapped) },
    /* Two different absences told apart, because different people fix them: a stage
       heading never had an assignment, while an assignment naming no resource is a gap in
       the file. The service already separates them and this keeps that separation. */
    { key: "activityOnly", label: "بدون تخصیص", value: count(status.activityOnly) },
    /* A resource is assigned here and no estimate line names it. Since the service types
       WORK resources itself (0038) nothing is expected in this state; anything that is,
       is worth a person. The old label «طبقه‌بندی‌نشده» described a decision nobody
       makes any more. */
    { key: "unclassified", label: "تخصیص بدون ردیف برآورد", value: count(status.unclassified) },
  ];
}

/** «آخرین فایل: x · وارد شده در y» — or the honest gap when nothing has been imported. */
export function provenanceLine(status) {
  if (!status?.sourceVersionId) return "هنوز هیچ برنامهٔ زمان‌بندی‌ای وارد نشده است.";
  const parts = [];
  if (status.sourceFileName) parts.push(status.sourceFileName);
  if (status.importedAt) parts.push(`وارد شده در ${formatBusinessDate(status.importedAt)}`);
  /* The file's own status date, which is a different fact from when it was imported and is
     frequently absent. Named so the two are never read as one. */
  if (status.reportingDate) parts.push(`تاریخ گزارش فایل: ${formatBusinessDate(status.reportingDate)}`);
  return parts.length ? parts.join(" · ") : "فایل بدون نام";
}

/**
 * What a run did, as a sentence.
 *
 * A run that changed nothing is the NORMAL result of a second press, and it gets a
 * sentence of its own rather than silence: the reader pressed a button and is owed an
 * answer, and «nothing needed doing» is an answer.
 */
export function remapSummary(result) {
  if (!result) return "پاسخی از سرویس دریافت نشد.";
  const count = (value) => formatDisplayNumber(String(value ?? 0));
  const made = [];
  if (result.resourcesCreated) made.push(`${count(result.resourcesCreated)} منبع`);
  if (result.linesCreated) made.push(`${count(result.linesCreated)} ردیف برآورد`);
  if (result.fixedCostLinesCreated) {
    made.push(`${count(result.fixedCostLinesCreated)} ردیف هزینه عمومی`);
  }
  const kept = count(result.linesMatched + result.fixedCostLinesMatched);
  if (!made.length) return `چیزی برای ساختن نبود؛ ${kept} ردیف از قبل موجود بود.`;
  const residue = result.fixedCostResidueRows
    ? ` ${count(result.fixedCostResidueRows)} ته‌مانده گرد‌کردن در یک ردیف جمع شد.`
    : "";
  return `${made.join(" و ")} ساخته شد؛ ${kept} ردیف از قبل موجود بود.${residue}`;
}

function summaryGrid(status) {
  const grid = element("div", "schedule-sync__counts");
  scheduleSummary(status).forEach((item) => {
    const cell = element("div", "schedule-sync__count");
    cell.append(element("strong", "numeric", item.value),
                element("span", "", item.label));
    grid.append(cell);
  });
  return grid;
}

/**
 * @param adapter     needs `getMppStatus()` and `remapMpp()`
 * @param canEdit     whether this actor may run the mapping. Reading is not gated here:
 *                    the service serves the status to anyone who may view finance.
 * @param onRemapped  called after a successful run, so the page can reload what changed
 */
export function createScheduleSyncSection({ adapter, canEdit = false, onRemapped = () => {} }) {
  const section = element("section", "settings-card settings-schedule-sync");
  const head = element("div", "settings-card__head");
  const copy = element("div", "");
  copy.append(element("h2", "", "همگام‌سازی با برنامهٔ زمان‌بندی"),
              element("p", "", "ردیف‌های فایل را به منابع و ردیف‌های برآورد تبدیل می‌کند."));
  head.append(element("div", "settings-card__icon", "⟳"), copy);

  const body = element("div", "schedule-sync__body");
  /* One region for everything the panel says back, announced politely: a reader who
     pressed the button and looked away is told when it finished. */
  const feedback = element("p", "schedule-sync__feedback");
  feedback.setAttribute("aria-live", "polite");
  const actions = element("div", "schedule-sync__actions");
  const run = element("button", "button button--primary", "بازخوانی از فایل");
  run.type = "button";

  section.append(head, body, actions, feedback);

  let status = null;
  let running = false;

  function paintBody() {
    body.replaceChildren();
    if (status === null) {
      body.append(element("p", "table-note", "در حال خواندن وضعیت…"));
      return;
    }
    body.append(element("p", "schedule-sync__provenance", provenanceLine(status)),
                summaryGrid(status));
  }

  function paintActions() {
    actions.replaceChildren();
    if (!canEdit) {
      /* Reading is allowed and running is not. Saying which, rather than hiding the
         section, is what tells a reader whose permission to ask for. */
      actions.append(element("p", "table-note",
        "برای اجرای بازخوانی، دسترسی ویرایش امور مالی لازم است."));
      return;
    }
    run.disabled = running || !status?.sourceVersionId;
    run.textContent = running ? "در حال بازخوانی…" : "بازخوانی از فایل";
    actions.append(run);
    if (!status?.sourceVersionId) {
      actions.append(element("p", "table-note",
        "تا وقتی فایلی وارد نشده، چیزی برای بازخوانی نیست."));
    }
  }

  run.addEventListener("click", async () => {
    if (running) return;
    running = true;
    feedback.className = "schedule-sync__feedback";
    feedback.textContent = "";
    paintActions();
    try {
      const result = await adapter.remapMpp();
      feedback.className = "schedule-sync__feedback schedule-sync__feedback--done";
      feedback.textContent = remapSummary(result);
      /* The counts on screen described the state BEFORE this run. Re-read them rather
         than deriving them from the result: the two come from different statements and a
         panel that computed one from the other would drift the first time either changed. */
      status = await adapter.getMppStatus();
      /* A run that created a RESOURCE has changed a list this page draws elsewhere, and
         this section cannot repaint that. Saying so is better than repainting the page
         under a reader who is still reading the sentence above. */
      if (result?.resourcesCreated) {
        feedback.textContent += " فهرست منابع تغییر کرده؛ برای دیدنش صفحه را باز کنید.";
      }
      onRemapped(result);
    } catch (error) {
      feedback.className = "schedule-sync__feedback schedule-sync__feedback--failed";
      feedback.textContent = formatApiErrorMessage(error, "بازخوانی انجام نشد.");
    } finally {
      running = false;
      paintBody();
      paintActions();
    }
  });

  paintBody();
  paintActions();

  /* The status is fetched by the section itself, so including it costs the page one line
     and no change to its own loading. A failure here leaves the section saying so instead
     of removing it: a panel that vanishes when a request fails teaches a reader that the
     feature does not exist. */
  Promise.resolve()
    .then(() => adapter.getMppStatus())
    .then((value) => { status = value; })
    .catch((error) => {
      status = null;
      feedback.className = "schedule-sync__feedback schedule-sync__feedback--failed";
      feedback.textContent = formatApiErrorMessage(error, "وضعیت برنامهٔ زمان‌بندی خوانده نشد.");
    })
    .finally(() => { paintBody(); paintActions(); });

  return section;
}
