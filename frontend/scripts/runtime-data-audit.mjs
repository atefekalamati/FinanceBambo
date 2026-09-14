// Does the page the host mounts fetch demo data? Asked of a browser, not of the source.
//
// Three static guards already say this cannot happen: bootstrap.js has no static import of
// `src/adapters/mock`, the packager does not follow `import()` when it builds the host's
// package, and `host.html` carries no `data-finance-runtime`. Each of them reads the code.
// This one reads the network: it opens the page and counts what the browser actually asked
// the server for. The difference matters because the failure being guarded against -- the
// production page fetching demo adapters -- is a fact about requests, and a refactor can
// satisfy every static check and still make one.
//
// Two pages, and the second is what keeps the first honest. `host.html` must fetch none.
// `index.html` is the standalone preview and must fetch them all: a run where BOTH are zero
// means the probe stopped working, not that the module got safer.
//
//   npm run audit:runtime            # expects a static server on 43127
//   BAMBO_AUDIT_URL=... npm run audit:runtime
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Forward slashes, which Windows accepts, because backslashes here were silently wrong:
// "C:\Program Files\..." in a JS string is not a path, it is "C:Program Files..." -- \P,
// \G, \C and \A are not escapes, so JavaScript drops each backslash without complaining.
// The default therefore named a file that cannot exist, Chrome never started, and the run
// failed with "Chrome opened no page target" -- which reads like a browser problem. Anyone
// who had CHROME_PATH set never saw it.
const chromePath = process.env.CHROME_PATH
  ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const baseUrl = process.env.BAMBO_AUDIT_URL ?? "http://127.0.0.1:43127";
const debugPort = Number(process.env.BAMBO_AUDIT_DEBUG_PORT ?? 43128);
const DEMO = /\/adapters\/mock\//;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function visit(page, portOffset) {
  // Its own port per page. Sharing one meant the second launch could find the first
  // browser's target before it had gone, and the run then reported one page's requests
  // under the other page's name -- a measurement that looks like a result.
  const port = debugPort + portOffset;
  const profile = await mkdtemp(join(tmpdir(), "bambo-runtime-"));
  const chrome = spawn(chromePath, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`,
    ...(process.env.CHROME_FLAGS ?? "").split(/\s+/).filter(Boolean),
    "about:blank",
  ], { stdio: "ignore" });

  try {
    // The PAGE target, not the browser one: a browser-level session reports no Network
    // events for a page, and this probe would then report zero requests for every page and
    // pass forever.
    let target;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        target = list.find((entry) => entry.type === "page" && entry.webSocketDebuggerUrl);
        if (target) break;
      } catch { /* not listening yet */ }
      await sleep(250);
    }
    if (!target) throw new Error("Chrome opened no page target");

    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });

    let id = 0;
    const pending = new Map();
    const requests = [];
    const failures = [];
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== undefined) { pending.get(message.id)?.(message); pending.delete(message.id); return; }
      if (message.method === "Network.requestWillBeSent") requests.push(message.params.request.url);
      if (message.method === "Runtime.exceptionThrown") {
        failures.push(message.params.exceptionDetails.exception?.description
          ?? message.params.exceptionDetails.text);
      }
    });
    const send = (method, params = {}) => new Promise((resolve) => {
      const next = ++id;
      pending.set(next, resolve);
      socket.send(JSON.stringify({ id: next, method, params }));
    });

    await send("Network.enable");
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Page.navigate", { url: `${baseUrl}/${page}` });

    // Wait for the NETWORK to go quiet, not for a number of seconds to pass.
    //
    // A fixed 5s sleep made this audit report what the machine was fast enough to finish
    // rather than what the page fetches. On a slower run `index.html` recorded 38 requests
    // and none of its ten demo modules, and the audit failed -- correctly refusing to trust
    // `host.html`'s zero, but for a reason that had nothing to do with the code. The same
    // sleep could equally cut `host.html` short, and a page measured before it finished
    // fetching is exactly how a demo import would go unnoticed.
    //
    // Quiet is the real condition: the last module is loaded when nothing new has been
    // requested for a while. The ceiling stops a page that polls from running forever, and
    // reaching it is reported below rather than passed off as settled.
    const quietFor = Number(process.env.BAMBO_AUDIT_QUIET_MS ?? 2000);
    const ceiling = Number(process.env.BAMBO_AUDIT_SETTLE_MS ?? 30000);
    const startedAt = Date.now();
    let seen = -1;
    let quietSince = Date.now();
    while (Date.now() - startedAt < ceiling) {
      if (requests.length !== seen) { seen = requests.length; quietSince = Date.now(); }
      else if (Date.now() - quietSince >= quietFor) break;
      await sleep(100);
    }
    const settled = Date.now() - quietSince >= quietFor;

    const evaluate = async (expression) => (await send("Runtime.evaluate", {
      expression, returnByValue: true,
    })).result?.result?.value;
    const runtime = await evaluate("document.body.dataset.financeRuntime ?? ''");
    // The probe checks itself: a session that ended up on a different page would otherwise
    // report that page's requests under this one's name.
    const landed = await evaluate("location.pathname");

    socket.close();
    return { page, runtime, landed, requests, settled,
             demo: requests.filter((url) => DEMO.test(url)), failures };
  } finally {
    chrome.kill();
    // Best effort. Windows holds the profile open for a moment after the process ends,
    // and a temporary directory that survives is not a reason to fail an audit about
    // what the page fetched.
    for (let attempt = 0; attempt < 5; attempt += 1) {
      try { await rm(profile, { recursive: true, force: true }); break; }
      catch { await sleep(300); }
    }
  }
}

const problems = [];

/** A page still fetching when the ceiling arrived was not measured, only interrupted. */
function mustHaveSettled(result) {
  if (!result.settled) {
    problems.push(`${result.page} was still fetching when the time limit arrived after ` +
                  `${result.requests.length} request(s); nothing it did or did not fetch ` +
                  "can be concluded from a run that was cut short");
  }
}

const host = await visit("host.html", 0);
console.log(`${host.landed}          runtime=${host.runtime || "(unset -> host)"}  ` +
            `requests=${host.requests.length}  demo=${host.demo.length}  ` +
            `uncaught=${host.failures.length}`);
mustHaveSettled(host);
if (host.runtime) {
  problems.push(`host.html declares data-finance-runtime="${host.runtime}"; the page the ` +
                "host mounts must carry no such attribute, because standalone is the one " +
                "value that switches demo data on");
}
if (host.demo.length) {
  problems.push(`host.html fetched ${host.demo.length} demo file(s): ` +
                host.demo.map((url) => url.split("/").pop()).join(", "));
}
for (const failure of host.failures) problems.push(`host.html raised: ${failure.split("\n")[0]}`);

const preview = await visit("index.html", 1);
console.log(`${preview.landed}         runtime=${preview.runtime || "(unset)"}  ` +
            `requests=${preview.requests.length}  demo=${preview.demo.length}  ` +
            `uncaught=${preview.failures.length}`);
mustHaveSettled(preview);
if (preview.runtime !== "standalone") {
  problems.push(`index.html should declare standalone, it declares ${preview.runtime || "nothing"}`);
}
if (!preview.demo.length) {
  problems.push("index.html fetched no demo files; the probe cannot tell a safe page from a " +
                "broken measurement, so host.html's zero proves nothing");
}

// Not "did it fetch anything" but "did it fetch the module". An earlier run of this
// audit pointed at a port where an API server was listening: the page loaded, the URL
// was right, and host.html reported two requests and zero demo files -- a pass by
// measuring nothing. The entry point is what makes the count mean something.
const ENTRY = /\/src\/app\/bootstrap\.js/;
for (const visited of [host, preview]) {
  if (!visited.requests.some((url) => ENTRY.test(url))) {
    problems.push(`${visited.page} never fetched src/app/bootstrap.js (${visited.requests.length} ` +
                  "requests): whatever answered is not the Finance module, so its zero " +
                  "demo files is not a result");
  }
}

// Checked here, with both results in hand: a session that ended up on a different page
// would otherwise report that page's requests under this one's name, and the run would
// look like a measurement instead of a mix-up.
for (const visited of [host, preview]) {
  if (!visited.landed?.endsWith(visited.page)) {
    problems.push(`the session for ${visited.page} ended up on ${visited.landed}; ` +
                  "the measurement is not about the page it names");
  }
}

if (problems.length) {
  console.error("\nruntime data audit FAILED");
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
console.log("\nruntime data audit passed: the host's page fetches no demo data, " +
            "and the preview still fetches its own.");
