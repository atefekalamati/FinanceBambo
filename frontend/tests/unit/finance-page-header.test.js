import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createFinancePageHeader } from "../../src/shared/components/finance-page-header.js";
import { SURFACES } from "../../src/core/config/routes.js";

test("internal headers contain only the unchanged h1 and the report back link", () => {
  const previous = globalThis.document;
  globalThis.document = {
    createElement(tagName) {
      return { tagName, children: [], append(...nodes) { this.children.push(...nodes); } };
    },
  };
  try {
    for (const title of ["فاکتورها", "تنظیمات مالی پروژه", "مرحله‌ای با عنوان بسیار بلند", "<script>عنوان</script>"]) {
      const header = createFinancePageHeader(title, "feature-header report-builder-page__header");
      assert.equal(header.tagName, "header");
      assert.match(header.className, /report-builder-page__header/);
      assert.match(header.className, /finance-internal-header/);
      assert.deepEqual(header.children.map((node) => node.tagName), ["h1", "a"]);
      const [heading, back] = header.children;
      assert.equal(heading.textContent, title);
      assert.equal(heading.className, undefined, "keep existing title styling");
      assert.equal(back.href, "#/finance-report");
      assert.equal(back.textContent, "بازگشت به گزارش مالی");
      assert.match(back.className, /finance-back-link/);
    }
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});

test("an operations page returns to operations while report pages keep their report home", () => {
  const previous = globalThis.document;
  globalThis.document = {
    createElement(tagName) {
      return { tagName, children: [], append(...nodes) { this.children.push(...nodes); } };
    },
  };
  try {
    const operationsBack = createFinancePageHeader("قیمت روز", "feature-header", SURFACES.OPERATIONS).children[1];
    assert.equal(operationsBack.href, "#/finance");
    assert.equal(operationsBack.textContent, "بازگشت به امور مالی");

    const reportBack = createFinancePageHeader("جدول قیمت‌ها", "feature-header", SURFACES.REPORT).children[1];
    assert.equal(reportBack.href, "#/finance-report");
    assert.equal(reportBack.textContent, "بازگشت به گزارش مالی");
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});

test("every internal finance page uses the shared header instead of a local back button", () => {
  const pages = [
    "invoices/invoices", "prices/prices", "financial-items/financial-items",
    "settings/settings", "progress/progress", "audit/audit",
    "ai-review/ai-review", "ai-review/invoice-files", "reports/reports",
    "level-one/level-one", "period-report/period-report",
    "report-builder/report-builder", "work-areas/work-areas",
  ];
  for (const page of pages) {
    const source = readFileSync(new URL(`../../src/features/${page}-page.js`, import.meta.url), "utf8");
    assert.match(source, /createFinancePageHeader\(/, page);
    assert.doesNotMatch(source, /finance-back-link|feature-header__navigation/, page);
  }
});
