import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chromePath = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const baseUrl = process.env.BAMBO_AUDIT_URL ?? "http://127.0.0.1:43127";
// Which cases to run, by key. Unset means all of them, so CI behaves exactly as before.
// A comma-separated list narrows the run -- useful when one case cannot render on the data
// at hand and would otherwise block every case behind it.
const onlyKeys = (process.env.BAMBO_AUDIT_ONLY ?? "")
  .split(",").map((key) => key.trim()).filter(Boolean);
const port = 49334;
const profile = await mkdtemp(join(tmpdir(), "bambo-print-audit-"));
const chrome = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: "ignore" });

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitForDebugger() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return;
    } catch {
      // Chrome is still starting.
    }
    await delay(100);
  }
  throw new Error("Chrome DevTools endpoint did not become ready.");
}

async function createPage(url) {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create print audit page: ${response.status}`);
  return response.json();
}

function connect(webSocketDebuggerUrl) {
  const socket = new WebSocket(webSocketDebuggerUrl);
  const pending = new Map();
  const exceptions = [];
  let messageId = 0;

  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
    if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  });

  const ready = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  return {
    exceptions,
    ready,
    send(method, params = {}) {
      const id = ++messageId;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() {
      socket.close();
    },
  };
}

function countPdfPages(base64) {
  const source = Buffer.from(base64, "base64").toString("latin1");
  return source.match(/\/Type\s*\/Page\b/g)?.length ?? 0;
}

const documents = [
  {
    key: "priority-followups",
    route: "report-builder?sections=completionBudget,areaCosts,unpricedItems,supplierDocuments,pendingDocuments,correctiveDocuments,estimateChanges",
    chapters: 7,
    maxPages: 24,
  },
  { key: "financial-report", route: "reports", prepare: null },
  {
    // Everything the builder can produce, in one document. Each chosen report
    // starts its own page, so the count is the guard against a section that
    // silently grew or one that stopped rendering at all.
    key: "custom-report",
    route: "report-builder?sections=overview,deviation,breakdown,monthly,priceVariance,quantityVariance,invoices,auditEvents,warnings,prices,estimateLines,sCurve,levelOne",
    prepare: null,
    chapters: 13,
    maxPages: 32,
  },
  {
    key: "suggested-six",
    route: "report-builder?sections=overview,breakdown,levelOne,sCurve,warnings,invoices",
    chapters: 6,
    maxPages: 20,
  },
  {
    key: "s-curve",
    route: "report-builder?sections=sCurve",
    chapters: 1,
    maxPages: 1,
  },
  {
    // The period report, through the surface that replaced it.
    //
    // `period-report` was withdrawn from the router -- see the comment in
    // layout-audit.mjs -- and this case used to drive it, so the audit failed on a page
    // that does not exist and the period report's print coverage was lost with it. The
    // approved workflow is the report builder with the two period sections and the range
    // in the address, which is what layout-audit measures.
    //
    // No click sequence: the builder reads the range from the URL, so there is no preset
    // to press and nothing to submit. Waiting is `chapters`, the mechanism this file
    // already has -- one chapter per chosen section, so two -- which also makes a section
    // that stopped rendering a failure rather than a shorter document.
    key: "period-report",
    route: "report-builder?sections=periodMetrics,periodBreakdown"
           + "&from=2026-09-01&to=2026-10-31",
    chapters: 2,
    settle: 4200,
    maxPages: 6,
  },
  {
    key: "invoice-detail",
    route: "invoices",
    prepare: `(() => {
      const trigger = document.querySelector('.invoices-table .button');
      if (!trigger) return false;
      trigger.click();
      return true;
    })()`,
  },
];

const results = [];

try {
  await waitForDebugger();
  const selected = onlyKeys.length
  ? documents.filter((entry) => onlyKeys.includes(entry.key))
  : documents;
if (onlyKeys.length && selected.length !== onlyKeys.length) {
  throw new Error(`BAMBO_AUDIT_ONLY names a case that does not exist: ${onlyKeys.join(",")}`);
}
for (const documentCase of selected) {
    const page = await createPage(`${baseUrl}/#/${documentCase.route}`);
    const cdp = connect(page.webSocketDebuggerUrl);
    await cdp.ready;
    await cdp.send("Runtime.enable");
    await cdp.send("Page.enable");
    await delay(1100);

    if (documentCase.chapters) {
      let rendered = false;
      for (let attempt = 0; attempt < 80; attempt += 1) {
        const result = await cdp.send("Runtime.evaluate", {
          expression: `document.querySelectorAll('.report-doc__chapter').length === ${documentCase.chapters}`,
          returnByValue: true,
        });
        if (result.result.value) { rendered = true; break; }
        await delay(150);
      }
      if (!rendered) throw new Error(`${documentCase.key}: report chapters did not load.`);
      await cdp.send("Runtime.evaluate", { expression: "document.fonts.ready", awaitPromise: true });
    }

    if (documentCase.prepare) {
      const prepared = await cdp.send("Runtime.evaluate", { expression: documentCase.prepare, returnByValue: true });
      if (!prepared.result.value) throw new Error(`Could not prepare ${documentCase.key} for printing.`);
      await delay(documentCase.settle ?? 700);
    }

    const responsive = [];
    if (documentCase.chapters) {
      for (const width of [320, 425, 768, 1366]) {
        await cdp.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false });
        const measured = await cdp.send("Runtime.evaluate", {
          expression: `({ overflow: document.documentElement.scrollWidth > innerWidth + 1,
            charts: [...document.querySelectorAll('.report-doc__curve')].every(el => el.getBoundingClientRect().right <= innerWidth + 1 && el.getBoundingClientRect().left >= -1) })`,
          returnByValue: true,
        });
        responsive.push({ width, ...measured.result.value });
        if (documentCase.key === "priority-followups") {
          const chooser = await cdp.send("Runtime.evaluate", {
            expression: `(async () => {
              const { openReportBuilder } = await import('/src/features/report-builder/report-builder-dialog.js');
              const dialog = openReportBuilder({ onBuild() {} });
              const cats = dialog.querySelector('.report-builder-cats');
              const tile = cats.querySelector('button');
              tile.click();
              dialog.querySelector('.report-builder-level2 input').click();
              dialog.querySelector('.report-builder-back').click();
              const selected = dialog.querySelector('.report-builder-level2 input').checked;
              for (let i = 0; i < 40; i++) cats.append(tile.cloneNode(true));
              cats.scrollTop = 100;
              const build = dialog.querySelector('.report-builder-panel__build').getBoundingClientRect();
              const bounds = dialog.getBoundingClientRect();
              const result = { scrolls: cats.scrollHeight > cats.clientHeight && cats.scrollTop > 0,
                selected, buildVisible: build.bottom <= bounds.bottom && build.top >= bounds.top };
              dialog.close();
              dialog.remove();
              return result;
            })()`, awaitPromise: true, returnByValue: true,
          });
          responsive[responsive.length - 1].chooser = chooser.result.value;
        }
      }
      await cdp.send("Emulation.clearDeviceMetricsOverride");
    }

    const pdf = await cdp.send("Page.printToPDF", {
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: false,
      generateTaggedPDF: true,
    });
    const pageCount = countPdfPages(pdf.data);
    results.push({ key: documentCase.key, pageCount, maxPages: documentCase.maxPages ?? 1, responsive, exceptions: [...cdp.exceptions] });
    cdp.close();
    await fetch(`http://127.0.0.1:${port}/json/close/${page.id}`);
  }
} finally {
  chrome.kill();
  await delay(300);
  // Chrome can still hold the profile on Windows; a failed cleanup must not
  // discard the audit result, which is printed after this block.
  try { await rm(profile, { recursive: true, force: true }); } catch { /* profile still locked */ }
}

// A document that must fit one page is held to one page. A period report is a
// listing, so its length follows the data; the cap is there to catch a layout
// that blows up, not to forbid a second page.
const failures = results.filter((result) => result.pageCount < 1 || result.pageCount > (result.maxPages ?? 1) || result.exceptions.length
  || result.responsive.some((size) => size.overflow || !size.charts
    || (size.chooser && (!size.chooser.scrolls || !size.chooser.selected || !size.chooser.buildVisible))));
console.log(JSON.stringify({ documents: results, failures }, null, 2));
if (failures.length) process.exitCode = 1;
