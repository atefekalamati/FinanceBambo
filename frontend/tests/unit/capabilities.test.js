import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { capabilitiesFor, describeAccess, FINANCE_PERMISSIONS } from "../../src/core/auth/capabilities.js";
import { buildPricesCsv, pricesFileName } from "../../src/features/prices/prices-csv.js";
import { buildEstimateLinesCsv } from "../../src/features/financial-items/financial-items-csv.js";

const featuresDir = fileURLToPath(new URL("../../src/features/", import.meta.url));
const featureFiles = readdirSync(featuresDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .flatMap((entry) => readdirSync(new URL(`../../src/features/${entry.name}/`, import.meta.url))
    .filter((name) => name.endsWith(".js"))
    .map((name) => [`${entry.name}/${name}`, readFileSync(fileURLToPath(new URL(`../../src/features/${entry.name}/${name}`, import.meta.url)), "utf8")]));

test("no feature names a permission code for itself", () => {
  // The host decides who may do what. A page that names a code has made a
  // second copy of that decision, and the two copies drift — which is how a
  // control ends up offered to an account the Backend will answer 403.
  featureFiles.forEach(([name, source]) => {
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    assert.doesNotMatch(code, /hasPermission\s*\(/, `${name} checks a permission itself instead of asking capabilitiesFor`);
    assert.doesNotMatch(code, /["'](finance|finance_report)\.[a-z]+["']/, `${name} names a permission code`);
  });
});

test("a reader has every capability except the ones that write", () => {
  const reader = capabilitiesFor({ permissionCodes: ["finance.view", "finance_report.view"] });
  assert.deepEqual(reader, {
    viewFinance: true,
    writeFinance: false,
    viewReport: true,
    issueReport: false,
    exportReport: false,
  });
  const admin = capabilitiesFor({ permissionCodes: FINANCE_PERMISSIONS.map((permission) => permission.code) });
  assert.deepEqual(Object.values(admin), [true, true, true, true, true]);
  // An absent context is not an account with rights.
  assert.deepEqual(Object.values(capabilitiesFor(null)), [false, false, false, false, false]);
});

test("the access list shows every code the module honours", () => {
  const shown = describeAccess({ permissionCodes: ["finance.edit"] });
  assert.deepEqual(shown.map((item) => item.code), FINANCE_PERMISSIONS.map((item) => item.code));
  assert.deepEqual(shown.filter((item) => item.allowed).map((item) => item.code), ["finance.edit"]);
  shown.forEach((item) => assert.match(item.label, /[؀-ۿ]/, `${item.code} has no Persian label`));
});

test("the exported price list carries the exact rial, not the number on screen", () => {
  const csv = buildPricesCsv([{
    resource: { code: "R-1", title: "سیمان", baseUnit: "kg" },
    organizationPrice: { scope: "organization", unitPriceIRR: "12345678901234567890", effectiveFrom: "1405-05-01" },
    projectPrice: null,
    currentPrice: { scope: "organization", unitPriceIRR: "12345678901234567890", effectiveFrom: "1405-05-01" },
  }]);
  // A float would have rounded this the moment it was read.
  assert.match(csv, /12345678901234567890/);
  // Excel reads the file as UTF-8 only if it starts with the byte-order mark.
  assert.ok(csv.startsWith("﻿"), "the export must open in a spreadsheet as Persian, not as mojibake");
  assert.match(csv, /\r\n/);
  assert.match(csv, /\(ریال\)/, "the header must say which unit the column holds");
  // A row with no price says so rather than leaving a cell that reads as zero.
  const empty = buildPricesCsv([{ resource: { code: "R-2", title: "ماسه", baseUnit: "kg" }, currentPrice: null }]);
  assert.match(empty, /بدون قیمت/);
  assert.doesNotMatch(empty, /,0,/);
});

test("a quantity and an amount never share a column in the estimate export", () => {
  const csv = buildEstimateLinesCsv({
    resources: [
      { resourceId: "a", code: "R-1", title: "بتن", baseUnit: "m3", type: "material" },
      { resourceId: "b", code: "G-1", title: "بیمه", baseUnit: "IRR", type: "general_cost" },
    ],
    lines: [
      { resourceId: "a", activityExternalId: "A1", wbsCode: "1.1", activityTitle: "فونداسیون", originalQuantity: "10", revisedQuantity: "12", source: "imported" },
      { resourceId: "b", activityExternalId: "A2", wbsCode: "1.2", activityTitle: "عمومی", originalAmount: "5000", revisedAmount: "5000", source: "manual" },
    ],
  });
  const rows = csv.split("\r\n").filter(Boolean);
  const header = rows[0].replace("﻿", "").split(",");
  const quantityColumn = header.indexOf("آخرین مقدار برآورد");
  const amountColumn = header.indexOf("آخرین مبلغ برآورد (ریال)");
  assert.ok(quantityColumn > 0 && amountColumn > quantityColumn);
  const quantityRow = rows[1].split(",");
  const generalRow = rows[2].split(",");
  assert.equal(quantityRow[quantityColumn], "12");
  assert.equal(quantityRow[amountColumn], "", "a quantity must not land in the money column");
  assert.equal(generalRow[amountColumn], "5000");
  assert.equal(generalRow[quantityColumn], "", "an amount must not land in the quantity column");
  // A revision is what the two columns exist to show.
  assert.equal(quantityRow[header.indexOf("اصلاح‌شده")], "بله");
  assert.equal(generalRow[header.indexOf("اصلاح‌شده")], "خیر");
});

test("a file name survives a project code with characters a file system refuses", () => {
  assert.equal(pricesFileName({ projectCode: "پروژه/۱", asOfDate: "1405-05-11" }), "finance-prices-project-1405-05-11.csv");
  assert.equal(pricesFileName({ projectCode: "BM-7", asOfDate: "1405-05-11" }), "finance-prices-BM-7-1405-05-11.csv");
});

/** The character range of every `if (canEdit) {` block in a source file. */
function editOnlyRanges(source) {
  const ranges = [];
  const marker = "if (canEdit) {";
  for (let at = source.indexOf(marker); at !== -1; at = source.indexOf(marker, at + 1)) {
    let depth = 0;
    let index = at + marker.length - 1;
    for (; index < source.length; index += 1) {
      if (source[index] === "{") depth += 1;
      else if (source[index] === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    ranges.push([at, index]);
  }
  return ranges;
}

test("reading a table and taking a copy of it are the same act", () => {
  // The export is not behind the edit permission: it hands back the rows the
  // account is already looking at. This checks where the button is built, not
  // merely that the words appear in the file.
  [["prices/prices-page.js"], ["financial-items/financial-items-page.js"]].forEach(([name]) => {
    const source = featureFiles.find((entry) => entry[0] === name)[1];
    const at = source.indexOf('element("button", "button button--ghost", "خروجی اکسل")');
    assert.ok(at > 0, `${name} offers no export`);
    editOnlyRanges(source).forEach(([from, to]) => {
      assert.ok(at < from || at > to, `${name} builds its export inside a canEdit block`);
    });
  });
});

/** Where each button carrying `label` is built in a source file. */
function buttonSites(source, label) {
  const sites = [];
  const needle = `"${label}"`;
  for (let at = source.indexOf(needle); at !== -1; at = source.indexOf(needle, at + 1)) {
    // Only the construction of a button counts; the same words are also used as
    // a dialog heading, which is not a control.
    if (source.slice(Math.max(0, at - 90), at).includes('element("button"')) sites.push(at);
  }
  return sites;
}

test("a write control is not built outside an edit gate", () => {
  // Every button that creates or changes a record is built inside a block that
  // only runs for an account with the edit permission — not merely disabled
  // inside one, and not built and then hidden.
  [
    ["financial-items/financial-items-page.js", ["خط متره جدید", "ورود گروهی برآورد", "قلم جدید", "ثبت اولین قلم"]],
    ["prices/prices-page.js", ["ثبت نسخه جدید قیمت", "ورود گروهی قیمت", "ثبت اولین قیمت"]],
  ].forEach(([name, labels]) => {
    const source = featureFiles.find((entry) => entry[0] === name)[1];
    const ranges = editOnlyRanges(source);
    labels.forEach((label) => {
      const sites = buttonSites(source, label);
      assert.ok(sites.length, `${name} no longer builds «${label}»`);
      sites.forEach((at) => {
        assert.ok(ranges.some(([from, to]) => at > from && at < to), `${name} builds «${label}» without the edit permission`);
      });
    });
  });
});

test("no write control is offered disabled with an excuse instead of withheld", () => {
  // A greyed-out button on every row is noise for an account that will never be
  // able to press one, and it invites the reading that the interface is what
  // stops them. It is not — the Backend is.
  featureFiles.forEach(([name, source]) => {
    if (name.startsWith("ai-review/")) return; // whole page is an upload; it says so once, in a notice.
    assert.doesNotMatch(source, /بدون مجوز/, `${name} still offers a disabled control with a permission excuse`);
  });
});
