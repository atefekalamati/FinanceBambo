/* A document small enough to read, for testing modules that render.
 *
 * The module has no dependencies -- that is a rule, not an omission -- so there is no
 * jsdom here and there will not be one. What follows implements only what the shared
 * `element()` helper and a rendering feature module actually touch, and nothing else:
 * enough to assert what a section puts on the page, and too little to be mistaken for
 * a browser.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 *
 * No layout, no styles, no events beyond a direct click, and no CSS selector engine
 * beyond `.class`, `tag`, and `tag tag` / `tag.class` pairs. A test that needs more than
 * that is testing the browser, and the repository already drives a real one: the layout
 * audit renders every route in headless Chrome, and that is where real rendering is
 * checked. This is for asserting the DECISIONS a render makes -- an em dash rather than a
 * zero, an empty state rather than an example row.
 *
 *   import { installDom } from "../helpers/dom.js";
 *   installDom();                       // before importing the module under test
 */

class FakeClassList {
  constructor(node) {
    this.node = node;
  }

  get tokens() {
    return this.node.className.split(/\s+/).filter(Boolean);
  }

  contains(name) {
    return this.tokens.includes(name);
  }

  add(...names) {
    const next = new Set(this.tokens);
    names.forEach((name) => next.add(name));
    this.node.className = [...next].join(" ");
  }
}

class FakeNode {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.className = "";
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this._text = "";
    this.classList = new FakeClassList(this);
  }

  set textContent(value) {
    this._text = value === undefined || value === null ? "" : String(value);
    this.children = [];
  }

  get textContent() {
    if (!this.children.length) return this._text;
    /* Joined with a space so two adjacent cells do not read as one word. A browser
       concatenates without one; for assertions, a run-together string hides mistakes. */
    return this.children.map((child) => child.textContent).join(" ");
  }

  append(...nodes) {
    nodes.forEach((node) => {
      node.parentNode = this;
      this.children.push(node);
    });
  }

  appendChild(node) {
    this.append(node);
    return node;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  click() {
    (this.listeners.get("click") ?? []).forEach((handler) => handler({ target: this }));
  }

  get firstElementChild() {
    return this.children[0] ?? null;
  }

  /** Every descendant, depth first, self excluded. */
  get descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants]);
  }

  matchesOne(selector) {
    const text = selector.trim();
    if (text.startsWith(".")) return this.classList.contains(text.slice(1));
    const [tag, ...classes] = text.split(".");
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    return classes.every((name) => this.classList.contains(name));
  }

  querySelectorAll(selector) {
    /* One level of descendant combinator: "tbody tr td" is the deepest any test here
       needs, and supporting more would be writing a selector engine. */
    const parts = selector.trim().split(/\s+/);
    let matches = this.descendants;
    parts.forEach((part, index) => {
      if (index === 0) {
        matches = matches.filter((node) => node.matchesOne(part));
      } else {
        matches = matches.flatMap((node) => node.descendants.filter((d) => d.matchesOne(part)));
      }
    });
    return matches;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
}

/** Put a document on `globalThis`, once. Returns it. */
export function installDom() {
  if (globalThis.document && globalThis.document.__fake) return globalThis.document;
  const document = {
    __fake: true,
    createElement(tag) {
      return new FakeNode(tag);
    },
    createDocumentFragment() {
      return new FakeNode("#fragment");
    },
    body: new FakeNode("body"),
  };
  globalThis.document = document;
  return document;
}
