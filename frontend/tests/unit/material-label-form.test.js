import assert from "node:assert/strict";
import test from "node:test";

import { installDom } from "../helpers/dom.js";

installDom();

const { FACTOR_TYPES, readLabelForm, renderLabelForm, unitSelect } =
  await import("../../src/features/prices/material-label-form.js");

/* The registry as `/unit-registry` returns it. Deliberately a short list: the test must
   not depend on how many units the backend happens to define, only that these are the
   ones the dropdown offers. */
const UNITS = [
  { code: "kg", label: "کیلوگرم", dimension: "mass" },
  { code: "m", label: "متر", dimension: "length" },
  { code: "each", label: "عدد", dimension: "count" },
];

const RESOURCES = [
  { resourceId: "res-1", title: "میلگرد آجدار", baseUnit: "kg" },
  { resourceId: "res-2", title: "لوله پلی اتیلن", baseUnit: "m" },
];

function row(changes = {}) {
  return {
    providerItemId: "item-1",
    name: "لوله پلی اتیلن ۱۱۰",
    category: "pipe",
    providerName: "Sivanland",
    sourceUnit: null,
    workflowDateJalali: "1405/06/23",
    workflowDateRaw: "۱۴۰۵/۶/۲۳",
    ...changes,
  };
}

test("every unit option comes from the backend list and nothing else", () => {
  const field = unitSelect("targetUnit", UNITS, { label: "نمایش بر حسب" });
  const options = [...field.querySelectorAll("option")].map((o) => o.value);
  assert.deepEqual(options, ["", "kg", "m", "each"]);
});

test("an empty registry disables the dropdown instead of inventing units", () => {
  const field = unitSelect("targetUnit", []);
  const select = field.querySelector("select");
  assert.equal(select.disabled, true);
  assert.match(field.textContent, /از سرور دریافت نشد/);
  // The guard that matters: no unit code appears anywhere when the backend gave none.
  for (const code of ["kg", "m", "each", "ton", "g"]) {
    assert.doesNotMatch(field.textContent, new RegExp(code));
  }
});

test("the currently selected unit is preselected", () => {
  const field = unitSelect("targetUnit", UNITS, { selected: "m" });
  const selected = [...field.querySelectorAll("option")].filter((o) => o.selected);
  assert.equal(selected.length, 1);
  assert.equal(selected[0].value, "m");
});

test("the form shows what the sheet said beside what a person may decide", () => {
  const form = renderLabelForm(row({ sourceUnit: "کیلو" }), { units: UNITS, canEdit: true });
  assert.match(form.textContent, /لوله پلی اتیلن ۱۱۰/);
  assert.match(form.textContent, /Sivanland/);
  assert.match(form.textContent, /کیلو/);
  assert.match(form.textContent, /1405\/06\/23/);
});

test("a sheet that declared no unit says so rather than showing a blank", () => {
  const form = renderLabelForm(row({ sourceUnit: null }), { units: UNITS, canEdit: true });
  assert.match(form.textContent, /اعلام نشده/);
});

test("a reader without edit permission gets every control disabled and no save button", () => {
  const form = renderLabelForm(row(), { units: UNITS, resources: RESOURCES, canEdit: false });
  const controls = [...form.querySelectorAll("input"), ...form.querySelectorAll("select")];
  assert.ok(controls.length > 0, "the form still renders its fields");
  for (const control of controls) {
    assert.equal(control.disabled, true, "a reader may look, not change");
  }
  assert.equal(form.querySelectorAll("button").length, 0, "and has nothing to press");
  assert.match(form.textContent, /دسترسی ویرایش مالی لازم است/);
});

test("an editor gets enabled controls and a save button", () => {
  const form = renderLabelForm(row(), { units: UNITS, resources: RESOURCES, canEdit: true });
  const select = form.querySelector("select");
  assert.equal(select.disabled, false);
  assert.ok(form.querySelectorAll("button").length >= 1);
});

test("the mapping is unapproved by default and says what approval means", () => {
  const form = renderLabelForm(row(), { units: UNITS, resources: RESOURCES, canEdit: true });
  const approve = form.querySelector('[name="mappingApproved"]');
  assert.equal(approve.checked, false);
  assert.match(form.textContent, /تا وقتی تأیید نشود/);
});

test("the resource dropdown offers the resources it was given, plus 'not mapped'", () => {
  const form = renderLabelForm(row(), { units: UNITS, resources: RESOURCES, canEdit: true });
  const select = form.querySelector('[name="financeResourceId"]');
  const options = [...select.querySelectorAll("option")].map((o) => o.value);
  assert.deepEqual(options, ["", "res-1", "res-2"]);
});

test("saving sends the values, and empty fields are null rather than empty strings", () => {
  const saved = [];
  const form = renderLabelForm(row(), {
    units: UNITS, resources: RESOURCES, canEdit: true, onSave: (values) => saved.push(values),
  });
  form.querySelector('[name="sourceUnit"]').value = "m";
  form.querySelector('[name="targetUnit"]').value = "m";
  form.querySelector('[name="reason"]').value = "فاکتور فروشنده متری است";
  form.querySelector('[name="mappingApproved"]').checked = true;

  const values = readLabelForm(form);
  assert.equal(values.sourceUnit, "m");
  assert.equal(values.targetUnit, "m");
  assert.equal(values.reason, "فاکتور فروشنده متری است");
  assert.equal(values.mappingApproved, true);
  assert.equal(values.label, null, "an untouched text field is null, not ''");
  assert.equal(values.displayName, null);
});

test("the form never offers a way to write a price", () => {
  const form = renderLabelForm(row(), { units: UNITS, resources: RESOURCES, canEdit: true });
  const names = [...form.querySelectorAll("input"), ...form.querySelectorAll("select")]
    .map((control) => control.name ?? "");
  for (const name of names) {
    assert.doesNotMatch(name, /price|amount|irr|toman/i,
      `${name} looks like a price field; a label is configuration, never a price`);
  }
});

test("the form says the imported row is not changed", () => {
  const form = renderLabelForm(row(), { units: UNITS, canEdit: true });
  assert.match(form.textContent, /ردیف وارد‌شده از برگه\s+تغییر نمی‌کند/);
});

test("every factor type has a Persian label and a distinct value", () => {
  const values = FACTOR_TYPES.map((entry) => entry.value);
  assert.equal(new Set(values).size, values.length);
  for (const entry of FACTOR_TYPES) {
    assert.ok(entry.label.length > 0);
    assert.match(entry.value, /^[a-z_]+$/, "the stored value stays an English identifier");
  }
});

test("the module reaches no external address", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(
    new URL("../../src/features/prices/material-label-form.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /docs\.google\.com/);
  assert.doesNotMatch(source, /\bfetch\s*\(/, "this module renders; fetching is the adapter's");
});
