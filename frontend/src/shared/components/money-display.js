import { compactMoneyFromIrr, formatTomanFromIrr, irrToDisplayValue } from "../formatters/money.js";
import { formatDisplayNumber } from "../formatters/display.js";
import { getDisplayCurrencyLabel } from "../preferences/currency-preference.js";

/**
 * An amount, written the way this module writes amounts.
 *
 * Persian RTL puts the scale and currency before the figure — «میلیارد تومان
 * ۱٫۸۷» in source order, read as «۱٫۸۷ میلیارد تومان» — so the unit is the first
 * child and the number is a `<bdi dir="ltr">` inside it. Left to itself the
 * bidi algorithm would break a grouped number apart at its separators.
 *
 * A compacted figure carries its exact value on `data-exact` and in its
 * aria-label, and takes focus, so the full number is one hover or one tab away.
 * A value that is not an exact integer says so rather than rendering as zero:
 * nothing was calculated, and zero would claim something was.
 *
 * It lives here because two places draw money into a cell — the overview and the
 * report page's breakdown — and one of them is a shared component now.
 */
export function createTomanDisplay(value, { compact = false } = {}) {
  const display = document.createElement("span");
  display.className = "money-display";
  if (!/^-?\d+$/.test(String(value ?? ""))) {
    display.textContent = "قابل محاسبه نیست";
    return display;
  }
  const compactValue = compact ? compactMoneyFromIrr(value) : null;
  const exactValue = formatTomanFromIrr(value);
  const unit = document.createElement("span");
  unit.className = "money-display__unit";
  unit.textContent = compactValue?.unit ?? getDisplayCurrencyLabel();
  const amount = document.createElement("bdi");
  amount.className = "money-display__amount numeric";
  amount.dir = "ltr";
  amount.textContent = compactValue?.amount ?? formatDisplayNumber(irrToDisplayValue(value));
  display.append(unit, amount);
  if (compactValue?.compact) {
    display.classList.add("compact-money");
    display.dataset.exact = exactValue;
    display.setAttribute("aria-label", exactValue);
    display.tabIndex = 0;
  }
  return display;
}
