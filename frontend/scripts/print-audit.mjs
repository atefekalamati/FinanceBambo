import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chromePath = process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const baseUrl = process.env.BAMBO_AUDIT_URL ?? "http://127.0.0.1:43127";
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
  { key: "financial-report", route: "reports", prepare: null },
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
  for (const documentCase of documents) {
    const page = await createPage(`${baseUrl}/#/${documentCase.route}`);
    const cdp = connect(page.webSocketDebuggerUrl);
    await cdp.ready;
    await cdp.send("Runtime.enable");
    await cdp.send("Page.enable");
    await delay(1100);

    if (documentCase.prepare) {
      const prepared = await cdp.send("Runtime.evaluate", { expression: documentCase.prepare, returnByValue: true });
      if (!prepared.result.value) throw new Error(`Could not prepare ${documentCase.key} for printing.`);
      await delay(700);
    }

    const pdf = await cdp.send("Page.printToPDF", {
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: false,
      generateTaggedPDF: true,
    });
    const pageCount = countPdfPages(pdf.data);
    results.push({ key: documentCase.key, pageCount, exceptions: [...cdp.exceptions] });
    cdp.close();
    await fetch(`http://127.0.0.1:${port}/json/close/${page.id}`);
  }
} finally {
  chrome.kill();
  await delay(300);
  await rm(profile, { recursive: true, force: true });
}

const failures = results.filter((result) => result.pageCount !== 1 || result.exceptions.length);
console.log(JSON.stringify({ documents: results, failures }, null, 2));
if (failures.length) process.exitCode = 1;
