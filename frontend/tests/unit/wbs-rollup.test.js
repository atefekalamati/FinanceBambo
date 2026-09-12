import test from "node:test";
import assert from "node:assert/strict";

import { buildWbsView, childrenOf, compareWbsCodes, findNode } from "../../src/shared/reports/wbs-rollup.js";
import { buildWbsNodes, unattributedActualIrr } from "../../src/adapters/mock/wbs-fixture.js";
import { createMockReportsAdapter } from "../../src/adapters/mock/reports-adapter.js";

const context = { organizationId: "org-1", projectId: "project-1", projectName: "پروژه" };

const node = (wbsCode, estimate, actual, extra = {}) => ({
  wbsCode, title: `مرحله ${wbsCode}`, parentWbsCode: null,
  activityCount: 1, childCount: 0,
  initialEstimateIrr: String(estimate), actualCostIrr: String(actual),
  forecastFinalIrr: String(Math.max(estimate, actual)), ...extra,
});

test("phases order by their structure, not by their string", () => {
  // "1.10" sorts before "1.2" as text, which would put the tenth phase second.
  const codes = ["1.10", "1.2", "1.20", "1.3", "1.9"];
  assert.deepEqual([...codes].sort(compareWbsCodes), ["1.2", "1.3", "1.9", "1.10", "1.20"]);
});

test("a project numbering its phases with letters still gets a stable order", () => {
  assert.deepEqual(["B.1", "A.2", "A.10"].sort(compareWbsCodes), ["A.2", "A.10", "B.1"]);
});

test("a shorter code comes before the code it is a prefix of", () => {
  assert.deepEqual(["1.8.1", "1.8"].sort(compareWbsCodes), ["1.8", "1.8.1"]);
});

test("both series share one scale so the phases stay comparable", () => {
  const view = buildWbsView({ nodes: [node("1.1", 100, 50), node("1.2", 1000, 900)] });
  const [small, large] = view.rows;
  assert.equal(large.estimateMagnitude, 100, "the largest figure sets the scale");
  assert.ok(small.estimateMagnitude < 11, "a phase a tenth the size looks a tenth the size");
});

test("a phase over its estimate is marked, not merely longer", () => {
  const view = buildWbsView({ nodes: [node("1.1", 100, 140), node("1.2", 100, 60)] });
  assert.equal(view.rows[0].overBudget, true);
  assert.equal(view.rows[0].consumedPercent, "140");
  assert.equal(view.rows[1].overBudget, false);
  assert.equal(view.overBudgetCount, 1);
});

test("an overrun stays inside the chart instead of being cut off at the end", () => {
  const view = buildWbsView({ nodes: [node("1.1", 100, 400)] });
  assert.ok(view.rows[0].actualMagnitude <= 100, "the ceiling must clear the actuals too");
  assert.equal(view.rows[0].actualMagnitude, 100);
});

test("a phase with no estimate reports nothing rather than nothing spent", () => {
  const view = buildWbsView({ nodes: [node("1.1", 0, 500)] });
  assert.equal(view.rows[0].hasEstimate, false);
  assert.equal(view.rows[0].consumedPercent, null, "0٪ would claim a real budget went untouched");
  assert.equal(view.rows[0].deviationIrr, null);
});

test("a phase missing some of its lines reports a subtotal that says so", () => {
  // The service sums the lines that state a baseline and counts the ones it could not
  // include. The figure alone is a smaller number wearing the name of the whole, so the
  // row has to carry the count with it or the page has nothing to qualify it with.
  const view = buildWbsView({
    nodes: [node("1.5", 1000, 400, { missingEstimateLineCount: 62 })],
  });
  assert.equal(view.rows[0].initialEstimateIrr, "1000");
  assert.equal(view.rows[0].missingEstimateLineCount, 62);
  assert.equal(view.rows[0].estimateIsPartial, true);
});

test("a phase with every line estimated is not marked partial", () => {
  const view = buildWbsView({ nodes: [node("1.5", 1000, 400)] });
  assert.equal(view.rows[0].missingEstimateLineCount, 0);
  assert.equal(view.rows[0].estimateIsPartial, false);
  assert.equal(view.totals.estimateIsPartial, false);
});

test("the project total counts every phase's missing lines", () => {
  const view = buildWbsView({
    nodes: [node("1.5", 1000, 400, { missingEstimateLineCount: 62 }),
            node("1.7", 2000, 900, { missingEstimateLineCount: 64 }),
            node("1.6", 500, 100)],
  });
  assert.equal(view.totals.initialEstimateIrr, "3500", "the phases that stated one still sum");
  assert.equal(view.totals.missingEstimateLineCount, 126);
  assert.equal(view.totals.estimateIsPartial, true);
});

test("a phase whose estimate is unknowable stays null rather than partial", () => {
  // Different gap, different answer: a reporting date whose estimate coverage cannot be
  // proven withholds the figure entirely, and there is no subtotal to qualify.
  const view = buildWbsView({
    nodes: [node("1.5", 0, 400, { initialEstimateIrr: null, missingEstimateLineCount: 0 })],
  });
  assert.equal(view.rows[0].initialEstimateIrr, null);
  assert.equal(view.rows[0].estimateIsPartial, false);
  assert.equal(view.totals.initialEstimateIrr, null);
  assert.equal(view.totals.estimateIsPartial, false);
});

test("an estimate that reaches no phase is carried, and named", () => {
  // The other absence. «برآورد ناقص» is lines INSIDE a phase that state no baseline; this
  // is lines that are in no phase at all, so no amount of completeness in the rows above
  // can contain them. Measured on the candidate: 40.8 million toman across 75 lines, which
  // is exactly why the page's total card and the project's own estimate disagreed.
  const view = buildWbsView({
    nodes: [node("1.5", 1000, 400), node("1.7", 2000, 900)],
    unmappedEstimateIrr: "408000000",
    unmappedEstimateLineCount: 75,
  });
  assert.equal(view.totals.unmappedEstimateIrr, "408000000");
  assert.equal(view.totals.unmappedEstimateLineCount, 75);
  assert.equal(view.totals.initialEstimateIrr, "3000",
    "the stage total stays the stages -- the unplaced amount is reported beside it");
});

test("no unplaced estimate means nothing to report, not a zero to explain", () => {
  const view = buildWbsView({ nodes: [node("1.5", 1000, 400)] });
  assert.equal(view.totals.unmappedEstimateIrr, null);
  assert.equal(view.totals.unmappedEstimateLineCount, 0);
});

test("an unplaced amount nobody could work out stays null rather than becoming zero", () => {
  // null means "nobody could say". 0 would mean "they are worth nothing", and the page
  // would then show a confident zero for money it cannot account for.
  const view = buildWbsView({
    nodes: [node("1.5", 1000, 400)],
    unmappedEstimateIrr: null,
    unmappedEstimateLineCount: 12,
  });
  assert.equal(view.totals.unmappedEstimateIrr, null);
  assert.equal(view.totals.unmappedEstimateLineCount, 12);
});

test("cost that reaches no phase is carried, not dropped", () => {
  const view = buildWbsView({
    nodes: [node("1.1", 1000, 600), node("1.2", 1000, 400)],
    unattributedActualIrr: "250",
  });
  assert.equal(view.unattributed.actualCostIrr, "250");
  // 250 of 1250 total spend
  assert.equal(view.unattributed.sharePercent, "20");
  assert.equal(view.totals.actualCostIrr, "1000", "the phases still total only what reached them");
});

test("no unattributed figure means no row, not a zero row", () => {
  assert.equal(buildWbsView({ nodes: [node("1.1", 10, 5)] }).unattributed, null);
  assert.equal(buildWbsView({ nodes: [node("1.1", 10, 5)], unattributedActualIrr: "0" }).unattributed, null);
});

test("money is never rounded on its way to the report", () => {
  const view = buildWbsView({ nodes: [node("1.1", 987654321987, 123456789123)] });
  assert.equal(view.rows[0].initialEstimateIrr, "987654321987");
  assert.equal(view.rows[0].actualCostIrr, "123456789123");
  assert.equal(view.rows[0].deviationIrr, "-864197532864");
});

test("an empty structure produces nothing to draw rather than a broken chart", () => {
  const view = buildWbsView({ nodes: [] });
  assert.equal(view.isEmpty, true);
  assert.deepEqual(view.rows, []);
  assert.equal(view.totals, null);
});

test("children are found by their parent, and roots by having none", () => {
  const nodes = [node("1.8", 10, 5), { ...node("1.8.1", 4, 2), parentWbsCode: "1.8" }];
  assert.deepEqual(childrenOf(nodes, null).map((row) => row.wbsCode), ["1.8"]);
  assert.deepEqual(childrenOf(nodes, "1.8").map((row) => row.wbsCode), ["1.8.1"]);
  assert.equal(findNode(nodes, "1.8.1").title, "مرحله 1.8.1");
});

test("the reference dataset names the project's real phases and reconciles", () => {
  const nodes = buildWbsNodes();
  const roots = nodes.filter((row) => row.parentWbsCode === null);
  assert.equal(roots.length, 19);
  assert.equal(roots[0].wbsCode, "1.2");
  assert.ok(roots.some((row) => row.title === "اجرای سازه بتنی" && row.activityCount === 158));

  // Split by weight without losing a rial: the phases sum to the project's own
  // برآورد اولیه, or the level-1 report and the overview would disagree.
  const total = roots.reduce((sum, row) => sum + BigInt(row.initialEstimateIrr), 0n);
  assert.equal(String(total), "18650000000");

  // And each phase's children sum to that phase.
  const parent = roots.find((row) => row.wbsCode === "1.8");
  const children = nodes.filter((row) => row.parentWbsCode === "1.8");
  assert.equal(children.length, parent.childCount);
  assert.equal(
    String(children.reduce((sum, row) => sum + BigInt(row.initialEstimateIrr), 0n)),
    parent.initialEstimateIrr);
});

test("the reference dataset shows the case the report exists for", () => {
  const view = buildWbsView({ nodes: buildWbsNodes().filter((row) => row.parentWbsCode === null) });
  assert.ok(view.overBudgetCount > 0, "at least one phase must be over its estimate");
  assert.ok(BigInt(view.totals.actualCostIrr) < BigInt(view.totals.initialEstimateIrr),
    "while the project as a whole is still under — which is why the breakdown matters");
});

test("unattributed cost is a share of what reached the phases, not of nothing", () => {
  const nodes = buildWbsNodes();
  assert.ok(BigInt(unattributedActualIrr(nodes)) > 0n);
});

test("the mock adapter answers the shape the endpoint is specified to answer", async () => {
  const adapter = createMockReportsAdapter(context);
  const top = await adapter.getWbsRollup({ reportingDate: "2026-08-20" });
  assert.equal(top.available, true);
  assert.ok(top.nodes.every((row) => row.parentWbsCode === null), "level 1 only");
  assert.ok(top.unattributedActualIrr, "the top level carries the unattributed figure");

  const children = await adapter.getWbsRollup({ reportingDate: "2026-08-20", parentWbsCode: "1.8" });
  assert.ok(children.nodes.length > 0);
  assert.ok(children.nodes.every((row) => row.parentWbsCode === "1.8"));
  assert.equal(children.unattributedActualIrr, null,
    "a phase's children account for all of it, so claiming it again would double-count");
});

test("the mock reports empty and error states like every other adapter", async () => {
  assert.deepEqual((await createMockReportsAdapter(context, { initialState: "empty" }).getWbsRollup({})).nodes, []);
  await assert.rejects(
    createMockReportsAdapter(context, { initialState: "error" }).getWbsRollup({}),
    (error) => error.code === "WBS_ROLLUP_UNAVAILABLE");
});
