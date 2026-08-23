import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chromePath = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const baseUrl = process.env.BAMBO_AUDIT_URL ?? "http://127.0.0.1:43127";
const routes = [
  "finance",
  "financial-items",
  "prices",
  "progress",
  "invoices",
  "invoice-files",
  "ai-review",
  "reports",
  "period-report",
  "audit",
  "settings",
];

const widths = [1440, 1280, 1024, 900, 768, 600, 480, 390, 360];
const port = 49333;
const profile = await mkdtemp(join(tmpdir(), "bambo-layout-audit-"));
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

const measurementExpression = `(() => {
  const root = document.documentElement;
  const viewportWidth = root.clientWidth;
  const pageOverflow = Math.max(root.scrollWidth, document.body.scrollWidth) - viewportWidth;
  const unexpected = [...document.querySelectorAll('body *')]
    .filter((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return false;
      if (element.closest('.table-scroll, .breakdown-chart-viewport, .breakdown-table-wrapper')) return false;
      const style = getComputedStyle(element);
      if (style.position === 'fixed') return false;
      return rect.right > viewportWidth + 2 || rect.left < -2;
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
  return { viewportWidth, pageOverflow, unexpected, clippedLabels, cardOverlaps, tableFillGaps, title: document.title };
})()`;

const failures = [];

try {
  await waitForDebugger();
  for (const width of widths) {
    for (const route of routes) {
      const page = await createPage(`${baseUrl}/#/${route}`);
      const cdp = connect(page.webSocketDebuggerUrl);
      await cdp.ready;
      await cdp.send("Runtime.enable");
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width,
        height: 900,
        deviceScaleFactor: 1,
        mobile: width <= 768,
      });
      await cdp.send("Page.reload", { ignoreCache: true });
      await delay(450);
      const result = await cdp.send("Runtime.evaluate", {
        expression: measurementExpression,
        returnByValue: true,
      });
      const measurement = result.result.value;
      if (measurement.pageOverflow > 2 || measurement.unexpected.length || measurement.clippedLabels.length || measurement.cardOverlaps.length || measurement.tableFillGaps.length || cdp.exceptions.length) {
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
