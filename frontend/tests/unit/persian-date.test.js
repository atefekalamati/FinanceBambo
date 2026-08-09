import test from "node:test";
import assert from "node:assert/strict";
import { getPersianMonthDays, gregorianIsoToPersian, persianToGregorianIso } from "../../src/shared/dates/persian-date.js";

test("converts between Gregorian ISO and Persian calendar dates", () => {
  assert.deepEqual(gregorianIsoToPersian("2026-08-08"), { year: 1405, month: 5, day: 17 });
  assert.equal(persianToGregorianIso(1405, 5, 17), "2026-08-08");
  assert.equal(persianToGregorianIso(1405, 1, 1), "2026-03-21");
});

test("returns correct Persian leap and common month lengths", () => {
  assert.equal(getPersianMonthDays(1403, 12).length, 30);
  assert.equal(getPersianMonthDays(1404, 12).length, 29);
  assert.equal(persianToGregorianIso(1404, 12, 30), null);
});

test("rejects invalid Persian and Gregorian dates", () => {
  assert.equal(gregorianIsoToPersian("2026-02-30"), null);
  assert.equal(persianToGregorianIso(1405, 13, 1), null);
  assert.equal(persianToGregorianIso(1405, 1, 32), null);
});
