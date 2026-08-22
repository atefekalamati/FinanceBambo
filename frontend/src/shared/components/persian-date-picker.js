import { getPersianMonthDays, getTehranTodayIso, gregorianIsoToPersian, persianToGregorianIso } from "../dates/persian-date.js";
import { showAccessibleDialog } from "./accessible-dialog.js";
import { element } from "../dom/elements.js";

const MONTH_NAMES = Object.freeze(["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]);
const WEEKDAYS = Object.freeze(["ش", "ی", "د", "س", "چ", "پ", "ج"]);
const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

function digits(value) {
  return String(value).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
}

function displayDate(iso) {
  const value = gregorianIsoToPersian(iso);
  if (!value) return "";
  return digits(`${value.year}/${String(value.month).padStart(2, "0")}/${String(value.day).padStart(2, "0")}`);
}

export function createPersianDatePicker({ id, label, value = "", hint = "تاریخ را از تقویم جلالی انتخاب کنید." }) {
  const field = element("div", "form-field persian-date-field");
  const labelNode = element("label", "form-label", label);
  labelNode.htmlFor = `${id}Display`;
  const control = element("div", "persian-date-control");
  const input = document.createElement("input");
  input.id = `${id}Display`;
  input.type = "text";
  input.readOnly = true;
  input.placeholder = "انتخاب تاریخ شمسی";
  input.value = displayDate(value);
  const open = element("button", "persian-date-trigger", "انتخاب تاریخ");
  open.type = "button";
  open.setAttribute("aria-haspopup", "dialog");
  const hintNode = element("small", "form-hint", hint);
  hintNode.id = `${id}Hint`;
  const error = element("small", "form-error");
  error.id = `${id}Error`;
  error.setAttribute("aria-live", "polite");
  input.setAttribute("aria-describedby", `${hintNode.id} ${error.id}`);
  control.append(input, open);
  field.append(labelNode, control, hintNode, error);

  let isoValue = value;
  let visibleMonth = gregorianIsoToPersian(value || getTehranTodayIso());

  function setValue(nextValue) {
    isoValue = nextValue;
    input.value = displayDate(nextValue);
    input.setAttribute("aria-invalid", "false");
    error.textContent = "";
  }

  function showCalendar() {
    const dialog = document.createElement("dialog");
    dialog.className = "persian-calendar-dialog";
    dialog.setAttribute("aria-label", "انتخاب تاریخ جلالی");
    const header = element("header", "persian-calendar__header");
    const previous = element("button", "persian-calendar__nav", "ماه بعد");
    previous.type = "button";
    const heading = element("strong", "persian-calendar__title");
    const next = element("button", "persian-calendar__nav", "ماه قبل");
    next.type = "button";
    header.append(previous, heading, next);
    const weekdays = element("div", "persian-calendar__weekdays");
    WEEKDAYS.forEach((weekday) => weekdays.append(element("span", "", weekday)));
    const grid = element("div", "persian-calendar__grid");
    const footer = element("footer", "persian-calendar__footer");
    const today = element("button", "button button--ghost", "امروز");
    today.type = "button";
    const close = element("button", "button button--ghost", "بستن");
    close.type = "button";
    footer.append(today, close);
    dialog.append(header, weekdays, grid, footer);

    function moveMonth(delta) {
      visibleMonth.month += delta;
      if (visibleMonth.month < 1) {
        visibleMonth.month = 12;
        visibleMonth.year -= 1;
      }
      if (visibleMonth.month > 12) {
        visibleMonth.month = 1;
        visibleMonth.year += 1;
      }
      renderMonth();
    }

    function renderMonth() {
      const month = getPersianMonthDays(visibleMonth.year, visibleMonth.month);
      heading.textContent = `${MONTH_NAMES[visibleMonth.month - 1]} ${digits(visibleMonth.year)}`;
      grid.replaceChildren();
      for (let index = 0; index < month.firstWeekdayOffset; index += 1) grid.append(element("span", "persian-calendar__blank"));
      for (let day = 1; day <= month.length; day += 1) {
        const dayIso = persianToGregorianIso(visibleMonth.year, visibleMonth.month, day);
        const button = element("button", "persian-calendar__day", digits(day));
        button.type = "button";
        button.setAttribute("aria-label", `${digits(day)} ${MONTH_NAMES[visibleMonth.month - 1]} ${digits(visibleMonth.year)}`);
        if (dayIso === isoValue) button.classList.add("persian-calendar__day--selected");
        if (dayIso === getTehranTodayIso()) button.classList.add("persian-calendar__day--today");
        button.addEventListener("click", () => {
          setValue(dayIso);
          dialog.close();
          input.focus();
        });
        grid.append(button);
      }
    }

    previous.addEventListener("click", () => moveMonth(1));
    next.addEventListener("click", () => moveMonth(-1));
    today.addEventListener("click", () => {
      setValue(getTehranTodayIso());
      dialog.close();
      input.focus();
    });
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.body.append(dialog);
    renderMonth();
    showAccessibleDialog(dialog, {
      opener: document.activeElement,
      initialFocus: () => dialog.querySelector(".persian-calendar__day--selected, .persian-calendar__day--today, .persian-calendar__day"),
    });
  }

  input.addEventListener("click", showCalendar);
  open.addEventListener("click", showCalendar);

  return {
    field,
    input,
    error,
    getValue: () => isoValue,
    setValue,
    focus: () => input.focus(),
  };
}
