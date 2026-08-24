/**
 * Round values for a money axis, chosen from the numbers a person would pick.
 *
 * The existing axis helper divides the largest value into equal parts, so a
 * project topping out at ۸٬۹۶۰٬۶۵۴٬۰۰۰ ریال gets lines at 2,240,163,500 and its
 * multiples — arithmetically correct and unreadable. This picks a step from the
 * 1-2-5 family instead, scaled to the project's own magnitude, so the same
 * project gets lines at ۲۰۰، ۴۰۰، ۶۰۰ و ۸۰۰ میلیون تومان and a project a
 * thousand times smaller gets lines that suit it.
 *
 * Everything is BigInt on exact integer IRR. The 1-2-5 choice normally uses
 * logarithms; the thresholds below are those comparisons rewritten as integer
 * arithmetic (√2, √10 and √50 scaled by 10,000) so no float touches money.
 */

const STEP_CHOICES = Object.freeze([
  { threshold: 70711n, multiplier: 10n },
  { threshold: 31623n, multiplier: 5n },
  { threshold: 14142n, multiplier: 2n },
  { threshold: 0n, multiplier: 1n },
]);

function exactInteger(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

/** 10 ** (digits - 1): the decade the value sits in. */
function decadeOf(value) {
  return 10n ** BigInt(String(value).length - 1);
}

/**
 * The gap between lines: the member of {1, 2, 5, 10} × 10ⁿ that lands closest
 * to an even division of `maximum` into `intervals` parts.
 */
export function chooseTickStep(maximum, intervals = 4, maximumLines = 6) {
  const top = typeof maximum === "bigint" ? maximum : exactInteger(maximum);
  if (top === null || top <= 0n || intervals < 1) return null;

  const rough = top / BigInt(intervals);
  if (rough <= 0n) return null;
  const decade = decadeOf(rough);
  // rough / decade, carried to four places so the √ thresholds stay integers.
  const fraction = (rough * 10000n) / decade;
  const choice = STEP_CHOICES.find((candidate) => fraction >= candidate.threshold);

  // The chosen step can still divide the range into more lines than the band
  // has room for — a chart 122px tall cannot carry seven labelled rows. Widen
  // through the same 1-2-5 family until the count fits rather than dropping
  // lines, so the values stay round.
  let step = choice.multiplier * decade;
  const LADDER = [1n, 2n, 5n, 10n];
  for (let guard = 0; top / step >= BigInt(maximumLines) && guard < 24; guard += 1) {
    const currentDecade = decadeOf(step);
    const rung = LADDER.indexOf(step / currentDecade);
    step = rung === -1 || rung === LADDER.length - 1
      ? step * 2n
      : LADDER[rung + 1] * currentDecade;
  }
  return step;
}

/**
 * Lines from zero upwards, never above the tallest bar.
 *
 * The axis deliberately does not round its top up past the data: the bars are
 * already drawn as a share of the largest value, and lifting the ceiling would
 * shorten every one of them. So the highest line sits at or below the tallest
 * bar, and the bars keep the heights they had.
 */
export function buildValueTicks(maximum, { intervals = 4, includeZero = true, maximumLines = 6 } = {}) {
  const top = typeof maximum === "bigint" ? maximum : exactInteger(maximum);
  if (top === null || top <= 0n) return [];

  const step = chooseTickStep(top, intervals, maximumLines);
  if (step === null) return [];

  const ticks = [];
  for (let value = includeZero ? 0n : step; value <= top; value += step) {
    ticks.push({
      valueIrr: value.toString(),
      // Share of the plot height, to the same hundredth of a percent the bars
      // are positioned with, so a line and a bar of equal value coincide.
      magnitude: Number((value * 10000n) / top) / 100,
    });
    if (ticks.length > 64) break; // a guard, not a limit any real axis reaches
  }
  return ticks;
}
