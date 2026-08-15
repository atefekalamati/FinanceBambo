import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

class FakeElement {
  constructor() {
    this.attributes = new Map();
    this.id = "";
    this.tabIndex = 0;
    this.isConnected = true;
    this.focused = false;
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  focus() {
    this.focused = true;
  }
}

class FakeDialog extends FakeElement {
  constructor({ heading, description }) {
    super();
    this.heading = heading;
    this.description = description;
    this.listeners = new Map();
    this.open = false;
  }

  querySelector(selector) {
    if (selector === "h1, h2, h3") return this.heading;
    if (selector === "p") return this.description;
    return null;
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
    this.listeners.get("close")?.();
  }
}

test("labels dialogs, exposes modal semantics, focuses their heading, and restores the opener", async () => {
  const previousHTMLElement = globalThis.HTMLElement;
  const previousDialog = globalThis.HTMLDialogElement;
  const previousDocument = globalThis.document;
  globalThis.HTMLElement = FakeElement;
  globalThis.HTMLDialogElement = FakeDialog;
  const opener = new FakeElement();
  globalThis.document = { activeElement: opener };

  try {
    const { getDialogOpener, showAccessibleDialog } = await import("../../src/shared/components/accessible-dialog.js");
    const heading = new FakeElement();
    const description = new FakeElement();
    const dialog = new FakeDialog({ heading, description });
    showAccessibleDialog(dialog);
    await new Promise((resolve) => queueMicrotask(resolve));

    assert.equal(dialog.open, true);
    assert.equal(dialog.getAttribute("aria-labelledby"), heading.id);
    assert.equal(dialog.getAttribute("aria-describedby"), description.id);
    assert.equal(dialog.getAttribute("aria-modal"), "true");
    assert.equal(getDialogOpener(dialog), opener);
    assert.equal(heading.focused, true);

    dialog.close();
    await new Promise((resolve) => queueMicrotask(resolve));
    assert.equal(opener.focused, true);
  } finally {
    if (previousHTMLElement === undefined) delete globalThis.HTMLElement;
    else globalThis.HTMLElement = previousHTMLElement;
    if (previousDialog === undefined) delete globalThis.HTMLDialogElement;
    else globalThis.HTMLDialogElement = previousDialog;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test("rejects a dialog without an accessible name", async () => {
  const previousHTMLElement = globalThis.HTMLElement;
  const previousDialog = globalThis.HTMLDialogElement;
  const previousDocument = globalThis.document;
  globalThis.HTMLElement = FakeElement;
  globalThis.HTMLDialogElement = FakeDialog;
  globalThis.document = { activeElement: new FakeElement() };

  try {
    const { showAccessibleDialog } = await import("../../src/shared/components/accessible-dialog.js");
    const dialog = new FakeDialog({ heading: null, description: null });
    assert.throws(() => showAccessibleDialog(dialog), /accessible dialog name/i);
    assert.equal(dialog.open, false);
  } finally {
    if (previousHTMLElement === undefined) delete globalThis.HTMLElement;
    else globalThis.HTMLElement = previousHTMLElement;
    if (previousDialog === undefined) delete globalThis.HTMLDialogElement;
    else globalThis.HTMLDialogElement = previousDialog;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test("routes every modal opening through the shared accessible dialog helper", async () => {
  const sourceRoot = fileURLToPath(new URL("../../src/", import.meta.url));
  const files = [];

  async function collect(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = `${directory}/${entry.name}`;
      if (entry.isDirectory()) await collect(path);
      else if (entry.name.endsWith(".js")) files.push(path);
    }
  }

  await collect(sourceRoot);
  const offenders = [];
  for (const path of files) {
    if (path.endsWith("accessible-dialog.js")) continue;
    const source = await readFile(path, "utf8");
    if (/\.showModal\s*\(/.test(source)) offenders.push(path);
  }
  assert.deepEqual(offenders, []);
});
