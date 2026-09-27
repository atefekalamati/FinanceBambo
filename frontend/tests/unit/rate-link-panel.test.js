import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { installDom } from "../helpers/dom.js";

installDom();

const { createPriceMappingPanel } =
  await import("../../src/features/financial-items/price-mapping-panel.js");

/* A CREW OR A MACHINE LINKS TO A RATE.
 *
 * Asked for 2026-09-27: «اتصال به قیمت روز» for hourly rows too, with a «نیرو و تجهیزات»
 * chip offering the rates set in settings, beside «ویرایش نرخ ساعتی» -- and the newest
 * decision wins. The panel is the same one; what an hourly row saves is a rate link.
 */

const CRANE_RATE = {
  providerItemId: "res-crane", externalId: null, name: "جرثقیل ۳۰ تن",
  category: "work", categoryLabel: "نیرو و تجهیزات", providerName: null,
  providerId: null, sourceUnitCode: "hour", currentPriceIRR: "5650000", active: true,
  specs: {}, specColumns: [],
};

function stub() {
  const calls = { candidates: [], linked: [] };
  let link = null;
  return {
    calls,
    async filters() {
      return { categories: [{ category: "rebar", label: "میلگرد", itemCount: 311 },
                            { category: "work", label: "نیرو و تجهیزات", itemCount: 3 }],
               providers: [], productTypes: [], units: [] };
    },
    async candidates(filters) {
      calls.candidates.push(filters);
      return { items: filters.category === "work" ? [CRANE_RATE] : [], page: 1, pageSize: 25, totalItems: 1 };
    },
    async connectionFor() {
      return { line: { estimateLineId: "line-1", mspUnit: "hour", mspQuantity: "60" },
               connection: null,
               total: { estimateLineId: "line-1", status: link ? "resource_price_ready" : "needs_components",
                        statusLabel: "", reason: null, dailyItemCostIRR: link ? "339000000" : null } };
    },
    async rateLinkFor() { return link; },
    async linkRate(lineId, payload) {
      calls.linked.push(payload);
      link = { id: "rl-1", estimateLineId: lineId, rateResourceId: payload.rateResourceId,
               rateResourceTitle: "جرثقیل ۳۰ تن", reason: payload.reason, linkedAt: "2026-09-27T10:00:00Z",
               inForce: true, currentUnitPriceIRR: "5650000", priceUnit: "hour" };
      return link;
    },
    async preview() { throw new Error("a rate needs no preview"); },
    async connect() { throw new Error("a rate is not a listing"); },
  };
}

async function settle(turns = 10) {
  for (let i = 0; i < turns; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}
const button = (root, label) => [...root.querySelectorAll("button")].find((n) => n.textContent === label);

const MACHINE_LINE = { lineId: "line-1", activityExternalId: "1.8.1.7.3" };
const MACHINE = { title: "ترک میکسر", type: "work", baseUnit: "hour" };

test("an hourly row opens on the rates, links to one, and the panel shows the link in force", async () => {
  const adapter = stub();
  let saved = 0;
  const panel = createPriceMappingPanel({ line: MACHINE_LINE, resource: MACHINE, adapter, canEdit: true,
                                          onSaved: () => { saved += 1; } });
  await settle();
  assert.ok(button(panel, "اتصال به نرخ"), "the button says what an hourly row links to");
  assert.match(panel.textContent, /به نرخی وصل نشده است/);
  button(panel, "اتصال به نرخ").click();
  await settle();
  assert.equal(adapter.calls.candidates.at(-1).category, "work", "the rates, before any filter is touched");
  const pick = [...panel.querySelectorAll(".price-candidate button")].find((n) => n.textContent === "انتخاب");
  pick.click();
  await settle();
  /* No unit to choose: a rate is already per the row's own unit. */
  assert.equal(panel.querySelector("[name=selectedUnit]").disabled, true);
  assert.match(panel.textContent, /به ازای ساعت/);
  const save = button(panel, "ثبت اتصال");
  assert.equal(save.disabled, false);
  save.click();
  await settle();
  assert.match(panel.textContent, /دلیل ثبت این اتصال الزامی است/, "a reason is required");
  panel.querySelector("[name=reason]").value = "نرخ جرثقیل از تنظیمات";
  save.click();
  await settle();
  assert.deepEqual(adapter.calls.linked, [{ rateResourceId: "res-crane", reason: "نرخ جرثقیل از تنظیمات" }]);
  assert.equal(saved, 1, "the row behind the panel refreshes");
  const card = panel.querySelector(".price-component--rate-link");
  assert.ok(card, "the link is drawn like a linked listing");
  assert.match(card.textContent, /جرثقیل ۳۰ تن/);
  assert.match(card.textContent, /نرخ متصل در حال استفاده است/);
  assert.ok(button(panel, "اتصال به نرخ"), "linking again stays possible: it is how a typed rate is set aside");
});

test("a link a later typed rate set aside is shown as such, not hidden", async () => {
  const adapter = stub();
  await adapter.linkRate("line-1", { rateResourceId: "res-crane", reason: "r" });
  adapter.rateLinkFor = async () => ({ id: "rl-1", estimateLineId: "line-1", rateResourceId: "res-crane",
    rateResourceTitle: "جرثقیل ۳۰ تن", reason: "r", inForce: false, currentUnitPriceIRR: null, priceUnit: "hour" });
  const panel = createPriceMappingPanel({ line: MACHINE_LINE, resource: MACHINE, adapter, canEdit: true });
  await settle();
  const card = panel.querySelector(".price-component--rate-link");
  assert.ok(card.classList.contains("price-component--superseded"));
  assert.match(card.textContent, /جای این اتصال را گرفته است/);
});

test("a material row is untouched: it still opens on listings and saves a component", async () => {
  const adapter = stub();
  const panel = createPriceMappingPanel({ line: { lineId: "line-2" }, resource: { title: "آرماتور", type: "material" },
                                          adapter, canEdit: true });
  await settle();
  assert.ok(button(panel, "اتصال به قیمت روز"));
  button(panel, "اتصال به قیمت روز").click();
  await settle();
  assert.equal(adapter.calls.candidates.at(-1).category, undefined);
});

test("the items table offers the link to hourly rows and names a linked rate", () => {
  const source = readFileSync(
    fileURLToPath(new URL("../../src/features/financial-items/financial-items-page.js", import.meta.url)), "utf8");
  const branch = source.split('dataset.action = "map-price"')[0].split("\n").slice(-14).join("\n");
  assert.doesNotMatch(branch, /!isHourlyRate\(resource\)/, "the guard of 2026-09-27 (morning) is gone");
  assert.match(branch, /"اتصال به نرخ"/);
  assert.match(branch, /"تغییر نرخ متصل"/);
  assert.match(source, /HOURLY_RATE_WORDING\.linked/);
});
