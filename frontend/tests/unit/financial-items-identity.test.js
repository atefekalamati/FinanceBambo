import test from "node:test";
import assert from "node:assert/strict";
import { mapResource } from "../../src/adapters/api/api-utils.js";
import { createApiFinancialItemsAdapter } from "../../src/adapters/api/financial-items-api-adapter.js";

/**
 * Where a Finance resource came from, and how many activities the page reads.
 *
 * `externalResourceId` cannot answer the first question on this database: an old
 * seed wrote schedule TASK uids into it, so reading it labelled legacy rows as
 * schedule data and schedule rows as hand-entered — exactly backwards.
 */

const context = { organizationId: "org-1", projectId: "project_01" };

test("labels a cost item by the schedule resource it was read from", () => {
  const mapped = mapResource({
    id: "r-1", type: "equipment", code: "MPP-R157", title: "آبپاش",
    externalResourceId: null, sourceResourceUid: 157, createdBy: "u", createdAt: "2026-01-01",
  });
  assert.equal(mapped.sourceResourceUid, 157);
  assert.equal(mapped.source, "progress_feed");
});

test("does not label a legacy row as schedule data because it carries an external id", () => {
  const mapped = mapResource({
    id: "r-2", type: "material", code: "MSP-T253", title: "برآورد مصالح مورد نیاز",
    externalResourceId: "253", sourceResourceUid: null, createdBy: "u", createdAt: "2026-01-01",
  });
  assert.equal(mapped.sourceResourceUid, null);
  assert.equal(mapped.source, "manual_entry", "the task uid in externalResourceId proves nothing about the source");
});

function stubClient(activityPages, currentPrices = []) {
  const requested = [];
  return {
    requested,
    request(path) {
      requested.push(path);
      if (path.includes("/activities?")) {
        const page = Number(new URL(`https://x${path}`).searchParams.get("page"));
        return Promise.resolve({ items: activityPages[page - 1] ?? [], page, pageSize: 200,
          totalItems: activityPages.flat().length, totalPages: activityPages.length });
      }
      if (path.endsWith("/resources")) {
        return Promise.resolve([{ id: "r-1", type: "material", code: "MPP-R1", title: "سیمان",
          baseUnit: "kg", externalResourceId: null, sourceResourceUid: 1, createdBy: "u", createdAt: "2026-01-01" }]);
      }
      if (path.endsWith("/estimate-lines")) {
        return Promise.resolve([{ id: "l-1", resourceId: "r-1", activityExternalId: "1.8.2.3",
          originalQuantity: "5", revisedQuantity: "5", source: "progress_feed", revision: 0, revisions: [] }]);
      }
      if (path.includes("/prices/current?")) return Promise.resolve(currentPrices);
      if (path.endsWith("/unit-registry")) return Promise.resolve({ items: [] });
      throw new Error(`unexpected request ${path}`);
    },
  };
}

test("reads every page of the activity catalogue, not the first two hundred", async () => {
  const first = Array.from({ length: 200 }, (unused, index) => ({
    activityExternalId: `A-${index}`, title: `فعالیت ${index}`, wbsCode: `1.${index}`, status: "active" }));
  const second = [{ activityExternalId: "1.8.2.3", title: "اجرای فونداسیون", wbsCode: "1.8.2.3", status: "active" }];
  const client = stubClient([first, second]);
  const workspace = await createApiFinancialItemsAdapter(context, client).getWorkspace();
  assert.equal(workspace.activities.length, 201);
  assert.equal(client.requested.filter((path) => path.includes("/activities?")).length, 2);
  // The line's activity lives on the second page; without it the title was lost.
  assert.equal(workspace.estimateLines[0].activityTitle, "اجرای فونداسیون");
});

test("leaves an unknown activity's title and WBS code null rather than filling them with its id", async () => {
  const client = stubClient([[]]);
  const workspace = await createApiFinancialItemsAdapter(context, client).getWorkspace();
  const [only] = workspace.estimateLines;
  assert.equal(only.activityTitle, null);
  assert.equal(only.wbsCode, null);
  assert.equal(only.activityExternalId, "1.8.2.3", "the identity itself is untouched");
});
