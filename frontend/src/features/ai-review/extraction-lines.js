import { tomanInputToIrr } from "../../shared/formatters/money.js";
import { normalizeDecimalInput } from "../../shared/validation/decimal-validation.js";

/* The invoice lines a draft proposes, and what a reviewer may do to them.
 *
 * WHY THIS EXISTS
 * The review card used to confirm every extraction as ONE line carrying the total, with
 * no quantity and no rate, and refused to attach it to anything but a general cost. That
 * refusal was not the service's: `valid_line_links` accepts an estimate line, and
 * `_calculate_lines` uses `line_amount_irr` as stated whenever it is present and never
 * looks at the quantity. The guard mirrored a rule that was not there, and its cost was
 * exact — a general cost carries no estimate line, so no activity and no WBS stage can be
 * derived for it, and the level-one chart cannot draw it. Every invoice read from a
 * document or a recording landed outside that chart.
 *
 * The reader already gives what the guard said was missing. `_candidate_fields` maps the
 * model's items to `{name, quantity, unit, unitPrice, amount}` and the same reader serves
 * the image path and the voice path — the service says so outright: «the same reader, not
 * a second one».
 *
 * WHAT IS PROPOSED AND WHAT IS CHOSEN
 * The numbers are proposed; the ATTACHMENT is chosen. Nothing here guesses which estimate
 * line a purchase belongs to — the document does not say, the recording does not say, and
 * a wrong guess would put somebody's money on another activity's chart. A line with no
 * target is not confirmable, and the card says which line is waiting.
 */

/** A decimal string, or null for anything that is not one. Blank is not a zero. */
function decimalOrNull(value) {
  const text = normalizeDecimalInput(value ?? "");
  return /^\d+(\.\d+)?$/.test(text) ? text : null;
}

/** The value a reviewer would see: their own edit when they made one, the reading otherwise. */
export function fieldValue(draft, key) {
  const field = (draft?.fields ?? []).find((item) => item.key === key);
  if (!field) return null;
  const value = field.confirmedValue ?? field.extractedValue;
  return value === undefined ? null : value;
}

/**
 * The items the reader found, normalised — or `[]`.
 *
 * A row with neither an amount nor a quantity-and-rate says nothing about money and is
 * dropped: it would reach the service as a line worth nothing and be counted as one.
 */
export function draftItems(draft) {
  const raw = fieldValue(draft, "items");
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => ({
    description: item?.name ?? item?.description ?? null,
    quantity: decimalOrNull(item?.quantity),
    unit: item?.unit ?? null,
    unitPrice: decimalOrNull(item?.unitPrice),
    /* `amount` and `totalPrice` are the same figure under two names in the contract; the
       first that states one wins, and neither is derived from the other here. */
    amount: decimalOrNull(item?.amount ?? item?.totalPrice),
  })).filter((item) => item.amount !== null || (item.quantity !== null && item.unitPrice !== null));
}

/**
 * The rows the card starts from.
 *
 * One per item the reader found. When it found none — which is every extraction whose
 * document states only a total, and may be most spoken ones — a single row carrying that
 * total, so the reviewer has something to attach rather than an empty table.
 */
export function proposedLines(draft) {
  const items = draftItems(draft);
  if (items.length) {
    return items.map((item, index) => ({
      key: `item-${index}`,
      description: item.description,
      quantity: item.quantity,
      unit: item.unit,
      unitPrice: item.unitPrice,
      amount: item.amount,
      targetId: null,
    }));
  }
  const total = decimalOrNull(fieldValue(draft, "totalAmount"));
  return [{
    key: "total",
    description: null,
    quantity: null,
    unit: null,
    unitPrice: null,
    amount: total,
    targetId: null,
  }];
}

/**
 * One row's amount in rials, or null when it states none.
 *
 * The stated amount wins over the product, and the product is only computed when the row
 * states no amount of its own. That is the service's own precedence — `_calculate_lines`
 * reads `line_amount_irr` first and never multiplies when it is present — and keeping it
 * here means the figure the reviewer sees is the figure that will be written.
 */
export function rowAmountIrr(row) {
  const stated = tomanInputToIrr(row?.amount ?? "");
  if (stated) return stated;
  const quantity = normalizeDecimalInput(row?.quantity ?? "");
  const rate = tomanInputToIrr(row?.unitPrice ?? "");
  if (!rate || !/^\d+(\.\d+)?$/.test(quantity)) return null;
  /* Exact: a rate is rials and a quantity may carry decimals, so the product is taken in
     integer arithmetic and rounded once, never through a float. */
  const [whole, fraction = ""] = quantity.split(".");
  const scale = 10n ** BigInt(fraction.length);
  const scaled = BigInt(whole + fraction) * BigInt(rate);
  const rounded = (scaled + scale / 2n) / scale;
  return rounded.toString();
}

/** What the rows add up to, in rials. Rows that state no amount contribute nothing. */
export function linesTotalIrr(rows) {
  return (rows ?? []).reduce((total, row) => {
    const amount = rowAmountIrr(row);
    return amount === null ? total : total + BigInt(amount);
  }, 0n).toString();
}

/**
 * Whether the rows add up to the total the reader stated, and by how much they do not.
 *
 * `null` when there is nothing to compare — no stated total, or no priced row. A note
 * about a difference between a number and an absence would be noise.
 *
 * This compares the draft against ITSELF and never against another invoice. The service
 * is explicit that two uploads cannot be assumed to describe the same document, so
 * nothing here looks outside this draft.
 */
export function reconcile(rows, draft) {
  const stated = tomanInputToIrr(fieldValue(draft, "totalAmount") ?? "");
  if (!stated) return null;
  const priced = (rows ?? []).some((row) => rowAmountIrr(row) !== null);
  if (!priced) return null;
  const sum = BigInt(linesTotalIrr(rows));
  const difference = sum - BigInt(stated);
  return { statedIrr: stated, linesIrr: sum.toString(),
           differenceIrr: (difference < 0n ? -difference : difference).toString(),
           matches: difference === 0n, over: difference > 0n };
}

/** Which rows a reviewer still has to answer for, by key. */
export function unattachedRows(rows) {
  return (rows ?? []).filter((row) => !row.targetId).map((row) => row.key);
}

/**
 * The `lines` a confirmation sends.
 *
 * `estimateLineId` travels when the chosen target has one, and that single field is what
 * puts the money on an activity — and therefore into the level-one chart, the WBS
 * subtotals and the remaining-work figures. A general cost still carries none, because it
 * genuinely belongs to no activity.
 *
 * The quantity and the rate travel only together and only when the row states both: the
 * service refuses the combination of an amount AND a computed pair, and a quantity with
 * no rate measures nothing.
 */
export function invoiceLines(rows, targets) {
  return (rows ?? []).map((row) => {
    const target = (targets ?? []).find((item) => item.targetId === row.targetId);
    if (!target) return null;
    const amount = rowAmountIrr(row);
    if (amount === null) return null;
    const quantity = normalizeDecimalInput(row.quantity ?? "");
    const rate = tomanInputToIrr(row.unitPrice ?? "");
    const quantified = target.targetType !== "general_cost"
      && /^\d+(\.\d+)?$/.test(quantity) && Boolean(rate);
    return {
      estimateLineId: target.estimateLineId ?? null,
      resourceId: target.resourceId,
      quantity: quantified ? quantity : null,
      unit: quantified ? (row.unit || target.unit || null) : null,
      unitPriceIrr: quantified ? rate : null,
      /* Sent whether or not the pair is: the service takes the stated amount first, so
         this is the figure of record and the pair beside it is what it was derived from.
         A line that sent only the pair would be re-multiplied and could disagree with the
         number the reviewer approved. */
      lineAmountIrr: amount,
      description: row.description || null,
    };
  }).filter(Boolean);
}
