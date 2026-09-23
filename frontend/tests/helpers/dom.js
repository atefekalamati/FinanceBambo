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

  remove(...names) {
    const next = new Set(this.tokens);
    names.forEach((name) => next.delete(name));
    this.node.className = [...next].join(" ");
  }

  /* The two-argument form, which is the one feature code uses to mark exactly one node
     of a list as chosen: `toggle(name, node === chosen)`. The one-argument form flips,
     like the real API. */
  toggle(name, force) {
    const on = force === undefined ? !this.contains(name) : Boolean(force);
    if (on) this.add(name);
    else this.remove(name);
    return on;
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
    /* A plain object, which is all `element.dataset.foo = "x"` needs. Not mirrored into
       `attributes`: nothing here queries `[data-*]`, and a half-working mirror would be a
       worse lie than an honest gap. Added because feature code genuinely uses it -- a
       panel stamps the row id it belongs to -- and without it the module threw before
       rendering anything. */
    this.dataset = {};
    /* A real `<input>`, `<select>` or `<textarea>` always has a string value, empty
       before anybody types. Without this, `field.value.trim()` -- which is how every form
       in this codebase reads a field -- threw on undefined, and the module swallowed it
       into the feedback line, so the page rendered "Cannot read properties of undefined"
       where a product list should have been. */
    this.value = "";
    this.disabled = false;
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

  /* How a feature module re-renders a region: drop what is there and put the new nodes
     in. Common enough in this codebase that a stub without it cannot render most
     sections at all -- `element.replaceChildren()` with no arguments is also the
     idiomatic "empty this", so the no-argument case has to work too. */
  replaceChildren(...nodes) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this.append(...nodes);
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  /* Asked before setting one: `showAccessibleDialog` will not overwrite a name a caller
     gave the dialog itself. Without this the check threw and the dialog never opened. */
  hasAttribute(name) {
    return this.attributes.has(name);
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  /* Fire one listener type directly. A form is driven by `change` and `input` as much as
     by `click` -- a cascade of dropdowns has no clicks in it at all -- and a stub that
     could only click would push every cascade test into calling the module's internals. */
  dispatch(type) {
    (this.listeners.get(type) ?? []).forEach((handler) => handler({ target: this }));
  }

  click() {
    this.dispatch("click");
  }

  /* A no-op, deliberately. Forms move focus -- to the box a validation message is about, to
     the field a disclosure just revealed -- and a stub that threw would make every such
     form untestable here. Pretending to track focus would be worse: nothing in this file
     lays anything out, and a `document.activeElement` that no browser rule maintained
     would be a fact these tests could assert and be wrong about. */
  focus() {}
  blur() {}

  /* `<dialog>` has these and a panel calls them on its own close button. No focus trap and
     no backdrop here: this stub does not lay anything out, and pretending otherwise would
     be a worse lie than an honest no-op. */
  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
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

    /* `[name="x"]`, optionally after a tag. Forms are addressed by field name far more
       often than by class, and a helper that could not do it would push every form test
       into indexing into `children`, which breaks the moment a field moves. */
    const attribute = text.match(/^([a-zA-Z]*)\[([a-zA-Z-]+)=["']?([^"'\]]*)["']?\]$/);
    if (attribute) {
      const [, tag, name, value] = attribute;
      if (tag && this.tagName !== tag.toUpperCase()) return false;
      /* A property first, then the attribute: `element.name = "x"` and
         `setAttribute("name", "x")` are both ordinary ways to set one, and a test should
         not have to know which the module used. */
      const actual = this[name] ?? this.getAttribute(name);
      return actual === value;
    }

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

/* A fragment is its own TYPE, not just a node with a funny name.
 *
 * `data-table.js` asks `body instanceof DocumentFragment` to decide whether it can query
 * the element for a <table> or has to resolve one later. With no such global the question
 * throws, and a module that renders perfectly well in a browser cannot be rendered here at
 * all. So the class exists and is published under the name the browser uses -- which is
 * the whole of what `instanceof` needs, and still no layout, styles or selector engine. */
class FakeDocumentFragment extends FakeNode {
  constructor() {
    super("#fragment");
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
    createTextNode(value) {
      const node = new FakeNode("#text");
      node.textContent = value;
      return node;
    },
    createDocumentFragment() {
      return new FakeDocumentFragment();
    },
    /* SVG. The shared report header draws the company mark, and a module that renders a
       letterhead cannot be rendered here at all without this. The namespace is accepted and
       discarded: nothing in these tests asks what namespace a node is in, and a stub that
       tracked one would be pretending to know more about SVG than it does. */
    createElementNS(_namespace, tag) {
      return new FakeNode(tag);
    },
    body: new FakeNode("body"),
  };
  globalThis.document = document;
  globalThis.DocumentFragment = FakeDocumentFragment;
  /* `showAccessibleDialog` refuses anything that is not a real <dialog>, which is right in
     the browser and made every dialog in the module untestable through its own entry
     point: tests had to append the element and skip `open()`, so the one function that
     sets `aria-modal`, names the dialog and returns focus was never exercised.

     This is not a pretend dialog. The stub above really does implement `showModal` and
     `close`; what was missing was only the constructor the guard checks against, so the
     brand is declared for nodes that already behave like one. */
  globalThis.HTMLDialogElement = { [Symbol.hasInstance]: (value) => value?.tagName === "DIALOG" };
  /* The same, for the guard that decides whether an element is still worth focusing.
     Every node this stub makes is one. */
  globalThis.HTMLElement = { [Symbol.hasInstance]: (value) => value instanceof FakeNode };
  return document;
}
