import { element } from "../../shared/dom/elements.js";
import { buildValueTicks } from "../../shared/charts/value-ticks.js";
import { compactMoneyScale } from "../../shared/formatters/money.js";

/**
 * Grouped columns, one pair per phase — the shape the host platform's own
 * «گزارش سطح ۱ MSP» card uses, so the two reports read as one family.
 *
 * What differs is the quantity. The host's axis is a percentage and stops at
 * 100; this one is money, so its ceiling is chosen from the figures themselves
 * on the same 1-2-5 ladder every other guide in this module uses. The label
 * above each column is that column's amount rather than a percentage, because a
 * percentage of an estimate that varies by phase is not comparable across the
 * row and the amount is.
 *
 * Bar order inside a group matches the host's markup: plan first, so in RTL it
 * sits on the right and the actual beside it on the left.
 */
export function createLevelOneChart({ rows, formatExact, ariaLabel, onSelect = null }) {
  const chart = element("div", "vbars");

  const amounts = rows.flatMap((row) => [exact(row.planIrr), exact(row.actualIrr)]).filter((value) => value !== null);
  const top = amounts.reduce((result, value) => (value > result ? value : result), 0n);
  const ticks = buildValueTicks(top, { intervals: 4, roundUp: true });
  const ceiling = ticks.length ? BigInt(ticks[ticks.length - 1].valueIrr) : 0n;
  const scale = compactMoneyScale(String(ceiling));

  chart.append(legend(scale));

  const plot = element("div", "vbars__plot");
  const axis = element("div", "vbars__y");
  // Top line first: the guide reads downwards, as the host's does.
  [...ticks].reverse().forEach((tick) => {
    const value = element("span", "vbars__tick", scale?.format(tick.valueIrr) ?? "");
    value.dataset.exact = formatExact(tick.valueIrr);
    axis.append(value);
  });

  const viewport = element("div", "vbars__viewport");
  viewport.tabIndex = 0;
  viewport.setAttribute("role", "img");
  viewport.setAttribute("aria-label", ariaLabel);
  const columns = element("div", "vbars__cols");

  rows.forEach((row) => {
    const group = element("div", "vgroup");
    if (row.overBudget) group.dataset.state = "over";
    const bars = element("div", "vgroup__bars");
    [
      ["plan", row.planIrr, "برآورد اولیه"],
      ["actual", row.actualIrr, "هزینه واقعی"],
    ].forEach(([series, value, label]) => {
      const bar = element("div", `vbar vbar--${series}`);
      bar.style.height = `${share(value, ceiling)}%`;
      bar.dataset.exact = `${label}: ${formatExact(value)}`;
      bar.append(element("em", "", scale?.format(value) ?? ""));
      bars.append(bar);
    });

    const name = row.href
      ? element("a", "vgroup__name", row.title)
      : element("span", "vgroup__name", row.title);
    // One line with an ellipsis is deliberate — nineteen stages of very
    // different name lengths would otherwise stand on nineteen different
    // floors. The title is where the whole name stays when it is cut.
    name.title = row.title;
    if (row.href) {
      name.href = row.href;
      name.title = `جزئیات ${row.title}`;
      if (onSelect) name.addEventListener("click", (event) => { event.preventDefault(); onSelect(row); });
    }
    group.append(bars, name);
    columns.append(group);
  });

  viewport.append(columns);
  plot.append(axis, viewport);
  chart.append(plot);
  return chart;
}

function legend(scale) {
  const list = element("div", "vbars__legend");
  [["actual", "هزینه واقعی"], ["plan", "برآورد اولیه"]].forEach(([series, label]) => {
    const item = element("span", "");
    item.append(element("i", `dot dot--${series}`), document.createTextNode(label));
    list.append(item);
  });
  if (scale?.unit) list.append(element("span", "vbars__unit", scale.unit));
  return list;
}

function exact(value) {
  return /^-?\d+$/.test(String(value ?? "")) ? BigInt(value) : null;
}

/** Height as a share of the axis, to the hundredth so a bar and a line agree. */
function share(value, ceiling) {
  const amount = exact(value);
  if (amount === null || amount <= 0n || ceiling <= 0n) return 0;
  return Number((amount * 10000n) / ceiling) / 100;
}
