import test from "node:test";
import assert from "node:assert/strict";
import { REPORT_SECTIONS } from "../../src/features/report-builder/report-sections.js";

// Minimal document for pure renderers; layout and pagination run in Chrome too.
class RenderNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.style = { setProperty() {} }; }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return (this.value ?? "") + this.children.map((child) => child.textContent).join(" "); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  append(...children) { this.children.push(...children); }
}

function withDocument(run) {
  const previousDocument = globalThis.document;
  const previousNode = globalThis.Node;
  globalThis.Node = RenderNode;
  globalThis.document = {
    createElement: (tag) => new RenderNode(tag),
    createElementNS: (ns, tag) => new RenderNode(tag),
    createTextNode: (text) => Object.assign(new RenderNode("text"), { textContent: text }),
  };
  try { run(); } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
    if (previousNode === undefined) delete globalThis.Node;
    else globalThis.Node = previousNode;
  }
}

const flatten = (nodes) => nodes.flatMap((node) => [node, ...flatten(node.children)]);
const text = (nodes) => nodes.map((node) => node.textContent).join(" ");
const month = (persianMonth, actualCostIrr, estimateIrr = null) => ({ persianYear: 1405, persianMonth, actualCostIrr, estimateIrr });

test("S curve renders actual only without plan, including zero and negative amounts", () => withDocument(() => {
  for (const amounts of [["0", "0"], ["10", "-30"], [null, "10"]]) {
    const nodes = REPORT_SECTIONS.sCurve({ monthly: { months: amounts.map((value, i) => month(i + 1, value)) } });
    const paths = flatten(nodes).filter((node) => node.tag === "path");
    assert.equal(paths.length, 1);
    assert.doesNotMatch(paths[0].attributes.d, /NaN|Infinity/);
    assert.match(text(nodes), /برنامه مالی ماهانه کامل در دسترس نیست/);
    assert.match(text(nodes), /لزوماً جمع از آغاز پروژه نیستند/);
  }
}));

test("a complete plan gets a distinct dashed series, never a fabricated one", () => withDocument(() => {
  const nodes = REPORT_SECTIONS.sCurve({ monthly: { months: [month(1, "10", "20"), month(2, "40", "30")] } });
  assert.equal(flatten(nodes).filter((node) => node.tag === "path").length, 2);
  assert.ok(flatten(nodes).some((node) => node.attributes.class?.includes("line--planned")));
  assert.doesNotMatch(text(nodes), /خط برنامه و انحراف از برنامه رسم یا محاسبه نشده/);
}));

test("WBS renders unavailable and null values honestly with allocation details", () => withDocument(() => {
  assert.match(text(REPORT_SECTIONS.levelOne({ wbs: { available: false } })), /داده نمایشی جایگزین نشده/);
  const nodes = REPORT_SECTIONS.levelOne({ wbs: {
    available: true, nodes: [{ wbsCode: "1", title: "<img src=x>", initialEstimateIrr: "100", actualCostIrr: "80", forecastFinalIrr: null, calculationStatus: "incomplete" }],
    unattributedActualIrr: "10", unmappedWbsActualIrr: "20", totals: { actualCostIrr: "110" },
  } });
  assert.match(text(nodes), /قابل محاسبه نیست/);
  assert.match(text(nodes), /هزینه ردیف‌های فاقد نگاشت معتبر WBS/);
  assert.match(text(nodes), /ناقص/);
  assert.ok(!flatten(nodes).some((node) => node.tag === "img"), "untrusted titles stay text");
}));

test("quality does not assert success when quality data is absent", () => withDocument(() => {
  const unknown = text(REPORT_SECTIONS.warnings({ overview: {} }));
  assert.match(unknown, /اعلام نشده/);
  assert.match(unknown, /جزئیات کیفیت پیشرفت از سرویس دریافت نشده/);
  const incomplete = text(REPORT_SECTIONS.warnings({ overview: { calculationStatus: "incomplete", incompleteMetricKeys: ["forecastFinalCostIrr"], progressQuality: { complete: false } } }));
  assert.match(incomplete, /شاخص‌های ناقص: پیش‌بینی هزینه نهایی/);
  assert.match(incomplete, /نیازمند بررسی/);
}));

test("document register uses invoice dates, retains draft and reversal, and explains financial scope", () => withDocument(() => {
  const nodes = REPORT_SECTIONS.invoices({ period: { from: "2026-08-01", to: "2026-08-31" }, invoices: { items: [
    { invoiceId: "1", invoiceNumber: "IN-PERIOD", invoiceDate: "2026-08-01", invoiceStatus: "draft", finalAmountIRR: "100" },
    { invoiceId: "2", invoiceNumber: "REVERSAL", invoiceDate: "2026-08-31", invoiceStatus: "voided", source: "reversal", originalInvoiceId: "ORIGINAL", finalAmountIRR: "100" },
    { invoiceId: "3", invoiceNumber: "OUTSIDE", invoiceDate: "2026-07-31", invoiceStatus: "confirmed", finalAmountIRR: "100" },
  ] } });
  assert.match(text(nodes), /IN-PERIOD/);
  assert.match(text(nodes), /REVERSAL/);
  assert.match(text(nodes), /ORIGINAL/);
  assert.doesNotMatch(text(nodes), /OUTSIDE/);
  assert.match(text(nodes), /جمع ساده مبالغ آن هزینه واقعی پروژه نیست/);
}));

test("new report renderers have explanatory empty states", () => withDocument(() => {
  for (const key of ["sCurve", "levelOne", "warnings", "invoices", "completionBudget", "areaCosts", "unpricedItems", "supplierDocuments", "pendingDocuments", "correctiveDocuments", "estimateChanges"]) {
    assert.ok(text(REPORT_SECTIONS[key]({})).length > 20);
  }
}));

test("breakdown does not print chart-helper zero defaults as missing forecast or actual", () => withDocument(() => {
  const nodes = REPORT_SECTIONS.breakdown({ overview: { breakdown: [{
    resourceType: "material", initialEstimateIrr: "100", actualCostIrr: null, forecastFinalIrr: null,
  }] } });
  const cells = flatten(nodes).filter((node) => node.tag === "td");
  assert.equal(cells[2].textContent, "قابل محاسبه نیست");
  assert.equal(cells[3].textContent, "قابل مقایسه نیست");
  assert.equal(cells[4].textContent, "قابل محاسبه نیست");
}));
