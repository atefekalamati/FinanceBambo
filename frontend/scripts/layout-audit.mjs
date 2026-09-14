import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chromePath = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const baseUrl = process.env.BAMBO_AUDIT_URL ?? "http://127.0.0.1:43127";
const routes = [
  "finance/operations",
  "finance/report",
  "finance/report-prices",
  "finance/report-items",
  "finance/report-builder?sections=overview,deviation,breakdown,monthly,priceVariance,quantityVariance,invoices,auditEvents,warnings,prices,estimateLines",
  // The two that read the project at two dates. They only draw when a range is
  // chosen, so the range is part of the address the audit measures.
  // June has thirty days. The 31st was in this list and the page passed it straight
  // through to /overview, which answered 422 -- and the rejection was never handled,
  // so the run recorded an uncaught promise on whichever page came next.
  "finance/report-builder?sections=periodMetrics,periodBreakdown&from=2026-01-01&to=2026-06-30",
  // A range the calendar does not contain. June has thirty days, so this must draw the
  // refusal -- named end, usable correction path -- and must not send a request or draw a
  // report for some other range. The page used to substitute the year-to-date preset and
  // print a finished document for it.
  "finance/report-builder?sections=periodMetrics,periodBreakdown&from=2026-01-01&to=2026-06-31",
  "finance/report-settings",
  "finance/financial-items",
  "finance/prices",
  "finance/progress",
  "finance/invoices",
  "finance/invoice-files",
  "finance/ai-review",
  // reports, period-report and work-areas are withdrawn: the router sends a
  // reader who types one to their own home, so measuring them measures that
  // home twice rather than the page.
  // Both shapes the level-1 report takes: the phase list, and one phase opened.
  "finance/level-one",
  "finance/level-one?wbs=1.8",
  "finance/audit",
  "finance/settings",
];

const widths = process.env.BAMBO_AUDIT_WIDTHS
  ? process.env.BAMBO_AUDIT_WIDTHS.split(",").map(Number)
  : [1440, 1280, 1024, 900, 768, 600, 480, 390, 360, 320];
const port = 49333;
const profile = await mkdtemp(join(tmpdir(), "bambo-layout-audit-"));
// A CI runner has no usable Chrome sandbox and a small /dev/shm, and Chrome
// simply never opens its debugging port there — which is what "DevTools endpoint
// did not become ready" was. The flags that fix it should not be on by default
// on a developer's machine, so the environment asks for them.
const extraFlags = (process.env.CHROME_FLAGS ?? "").split(/\s+/).filter(Boolean);

const chrome = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  ...extraFlags,
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });

// Kept so a failure to start can say why. Discarded otherwise — Chrome is
// chatty on stderr even when it is perfectly happy.
let chromeStderr = "";
chrome.stderr?.on("data", (chunk) => { chromeStderr += chunk; });
let chromeExit = null;
chrome.on("exit", (code, signal) => { chromeExit = signal ?? code; });

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitForDebugger() {
  // Thirty seconds, not five. A warm Chrome on a developer's machine answers in
  // under a second, so the old 50 x 100ms was never reached locally — but a cold
  // start on a loaded CI runner takes ten or more, and the audit failed there
  // roughly every other run while passing every run here.
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (chromeExit !== null) {
      throw new Error(`Chrome exited before its debugging port opened (${chromeExit}).
${chromeStderr.trim()}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return;
    } catch {
      // Chrome is still starting.
    }
    await delay(250);
  }
  throw new Error(
    `Chrome DevTools endpoint did not become ready within 30s.
` +
    `path: ${chromePath}
flags: ${extraFlags.join(" ") || "(none)"}
${chromeStderr.trim()}`,
  );
}

/**
 * Refuse to measure a page the router did not open.
 *
 * A route it does not recognise, or one this account may not reach, lands on the default
 * route -- and a fallback page has no overflow and throws no exceptions, so it passes
 * every check here while proving nothing about the page named. The router rewrites
 * `location.hash` to what it actually opened, so asking for that is enough and needs no
 * per-page selector.
 */
async function assertPageIdentity(cdp, route) {
  const wanted = route.split("?")[0].replace(/^#?\/?/, "");
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const result = await cdp.send("Runtime.evaluate", {
      expression: "location.hash.replace(/^#\\/?/, '').split('?')[0]",
      returnByValue: true,
    });
    const opened = result.result.value ?? "";
    if (opened === wanted) return opened;
    if (opened && opened !== wanted && attempt > 8) {
      throw new Error(
        `asked for ${wanted} and the router opened ${opened} -- a fallback, not the page`);
    }
    await delay(150);
  }
  throw new Error(`${wanted}: the router never settled on a route`);
}

async function createPage(url) {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  });
  if (!response.ok) throw new Error(`Could not create audit page: ${response.status}`);
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
    if (message.method === "Runtime.exceptionThrown") {
      exceptions.push(message.params.exceptionDetails.text);
    }
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

/** Resolves once the module has rendered, or after `timeout` either way. */
async function waitForRender(cdp, timeout = 8000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const probe = await cdp.send("Runtime.evaluate", {
      expression: `(() => document.readyState === "complete"
        && !!document.querySelector("#finance-module-root")?.firstElementChild)()`,
      returnByValue: true,
    });
    if (probe.result?.value === true) {
      // One more frame, so the render that just landed has been laid out.
      await delay(120);
      return true;
    }
    await delay(100);
  }
  return false;
}

const measurementExpression = `(() => {
  const root = document.documentElement;
  const viewportWidth = root.clientWidth;
  const pageOverflow = Math.max(root.scrollWidth, document.body.scrollWidth) - viewportWidth;
  // A row of a wide table sits outside the viewport and is not a defect: the reader
  // scrolls the table to it. That was already forgiven, but by NAME -- '.table-scroll' and
  // '.breakdown-table-wrapper' -- and a name only forgives the containers somebody
  // remembered to list. The level-one chart is the same kind of container (overflow-x:auto,
  // a styled scrollbar, scroll-snap, its own tab stop) and was not on the list, so all
  // thirteen phase groups were reported as escaping the page at every width while
  // pageOverflow stayed 0 and every group was reachable by scrolling.
  //
  // So the test is now the property that made those two safe rather than their names: is
  // this inside something that actually scrolls on this axis. A container that CLIPS
  // without scrolling still fails, which is the case worth catching -- content nobody can
  // reach. Fixed elements are exempt as before; they are positioned against the viewport.
  const reachableByScrolling = (element) => {
    for (let node = element.parentElement; node && node !== document.body; node = node.parentElement) {
      const overflowX = getComputedStyle(node).overflowX;
      if ((overflowX === 'auto' || overflowX === 'scroll') && node.scrollWidth > node.clientWidth + 1) {
        return true;
      }
    }
    return false;
  };
  const unexpected = [...document.querySelectorAll('body *')]
    .filter((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return false;
      const style = getComputedStyle(element);
      if (style.position === 'fixed') return false;
      if (rect.right <= viewportWidth + 2 && rect.left >= -2) return false;
      return !reachableByScrolling(element);
    })
    .slice(0, 12)
    .map((element) => ({
      tag: element.tagName.toLowerCase(),
      className: String(element.className).slice(0, 100),
      text: String(element.textContent).trim().replace(/\\s+/g, ' ').slice(0, 70),
      rect: (() => { const value = element.getBoundingClientRect(); return { left: value.left, right: value.right, width: value.width }; })(),
    }));
  const clippedLabels = [...document.querySelectorAll('h1, h2, h3, label, legend, th, .summary-card__value')]
    .filter((element) => element.scrollWidth > element.clientWidth + 2 && getComputedStyle(element).overflowX === 'hidden')
    .slice(0, 12)
    .map((element) => ({ tag: element.tagName.toLowerCase(), className: String(element.className), text: element.textContent.trim().slice(0, 70) }));
  const cardOverlaps = [];
  const cardParents = new Set([...document.querySelectorAll('.summary-card')].map((card) => card.parentElement));
  cardParents.forEach((parent) => {
    const cards = [...parent.children].filter((child) => child.matches?.('.summary-card'));
    cards.forEach((card, index) => {
      const first = card.getBoundingClientRect();
      cards.slice(index + 1).forEach((otherCard) => {
        const second = otherCard.getBoundingClientRect();
        const overlapWidth = Math.min(first.right, second.right) - Math.max(first.left, second.left);
        const overlapHeight = Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
        if (overlapWidth > 1 && overlapHeight > 1) {
          cardOverlaps.push({
            first: card.dataset.metric ?? card.className,
            second: otherCard.dataset.metric ?? otherCard.className,
            overlapWidth,
            overlapHeight,
          });
        }
      });
    });
  });
  const tableFillGaps = [...document.querySelectorAll('.data-table')]
    .map((table) => {
      const wrapper = table.closest('.table-scroll');
      if (!wrapper) return null;
      const tableRect = table.getBoundingClientRect();
      const availableWidth = wrapper.clientWidth;
      const gap = availableWidth - tableRect.width;
      if (gap <= 2) return null;
      return {
        className: String(table.className),
        availableWidth,
        tableWidth: tableRect.width,
        gap,
      };
    })
    .filter(Boolean)
    .slice(0, 12);
  const headerIssues = [...document.querySelectorAll('.finance-internal-header')].flatMap((header) => {
    const [title, back] = header.children;
    if (header.children.length !== 2 || title?.tagName !== 'H1' || back?.tagName !== 'A') {
      return [{ issue: 'header must contain only an h1 and a back link' }];
    }
    const headingRect = title.getBoundingClientRect();
    const backRect = back.getBoundingClientRect();
    const headerRect = header.getBoundingClientRect();
    const sameRow = Math.abs((headingRect.top + headingRect.bottom) / 2 - (backRect.top + backRect.bottom) / 2) < 2;
    const separated = backRect.right <= headingRect.left + 1;
    const contained = backRect.left >= headerRect.left - 1 && headingRect.right <= headerRect.right + 1;
    const unclipped = title.scrollWidth <= title.clientWidth + 2 && back.scrollWidth <= back.clientWidth + 2;
    return sameRow && separated && contained && unclipped ? [] : [{ issue: 'header alignment or overflow', sameRow, separated, contained, unclipped }];
  });
  return { viewportWidth, pageOverflow, unexpected, clippedLabels, cardOverlaps, tableFillGaps, headerIssues, title: document.title };
})()`;

const failures = [];

try {
  await waitForDebugger();
  for (const width of widths) {
    for (const route of routes) {
      // `#finance/...`, not `#/finance/...`. The router writes the first form and matches
      // only that; the extra slash fails every match and lands on the default route, which
      // is how this audit spent its runs measuring the fallback page and reporting success.
      const page = await createPage(`${baseUrl}/#${route}`);
      const cdp = connect(page.webSocketDebuggerUrl);
      await cdp.ready;
      await cdp.send("Runtime.enable");
      // Before anything is measured: is this the page that was asked for?
      await assertPageIdentity(cdp, route);
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width,
        height: 900,
        deviceScaleFactor: 1,
        mobile: width <= 768,
      });
      await cdp.send("Page.reload", { ignoreCache: true });
      // Not a fixed pause. A reload replaces the document, and an evaluate that
      // lands mid-swap finds documentElement itself null — which crashed this
      // script on whichever route happened to be slow that run, and would
      // otherwise have skipped it while still counting it as a run. Wait for the
      // module to have actually rendered, then measure.
      await waitForRender(cdp);
      const result = await cdp.send("Runtime.evaluate", {
        expression: measurementExpression,
        returnByValue: true,
      });
      const measurement = result.result.value;
      if (measurement.pageOverflow > 2 || measurement.unexpected.length || measurement.clippedLabels.length || measurement.cardOverlaps.length || measurement.tableFillGaps.length || measurement.headerIssues.length || cdp.exceptions.length) {
        failures.push({ width, route, measurement, exceptions: cdp.exceptions });
      }
      cdp.close();
      await fetch(`http://127.0.0.1:${port}/json/close/${page.id}`);
    }
  }
} finally {
  chrome.kill();
  await delay(800);
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 250 });
}

console.log(JSON.stringify({ runs: routes.length * widths.length, failures }, null, 2));
if (failures.length) process.exitCode = 1;
