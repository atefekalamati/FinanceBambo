/**
 * A table that survives a narrow screen.
 *
 * Four things travel together here, because each is useless without the others:
 * the first column is pinned to the reading edge so a scrolled row is still
 * identified; the rest scroll sideways inside their own region rather than
 * making the page scroll; the reader can put columns away and bring them back;
 * and what a narrow screen starts with is decided by each column's tier rather
 * than by taking whatever fits.
 *
 * Nothing here knows what a row means. Filtering, sorting, paging and the shape
 * of a cell stay with the page that owns them -- this owns the table's geometry
 * and nothing else.
 *
 * Columns are named, never counted. `data-col` on both the header cell and its
 * body cells is what lets a column be hidden without every rule after it
 * shifting, and it is why the two can only be hidden together.
 */
import { element, tableCaption, tableHead } from "../dom/elements.js";
import { showAccessibleDialog } from "./accessible-dialog.js";

/** A column the reader may not put away: it is how a row is identified at all. */
export const IDENTITY = "identity";

/** Kept on a narrow screen. */
export const PRIMARY = "primary";

/** Put away on a narrow screen, one press from coming back. */
export const SECONDARY = "secondary";

/**
 * Which columns a screen of this width starts with.
 *
 * The two widths are the module's own: 36rem is where its pages go to one
 * column, 64rem where the board does. A tier decides nothing above that.
 */
export function defaultVisibleColumns(columns, matchMedia = globalThis.matchMedia) {
  const matches = (query) => typeof matchMedia === "function" && matchMedia(query).matches;
  const keys = (keep) => new Set(columns.filter(keep).map((column) => column.key));
  if (matches("(max-width: 36rem)")) return keys((column) => column.tier !== SECONDARY);
  if (matches("(max-width: 64rem)")) return keys((column) => column.tier !== SECONDARY || column.keepOnTablet);
  return keys(() => true);
}

/** Show or hide one column. Header and body move together, or they stop agreeing. */
export function applyColumnVisibility(table, key, visible) {
  if (!table) return;
  table.querySelectorAll(`:is(th, td)[data-col="${key}"]`).forEach((cell) => { cell.hidden = !visible; });
  const shown = table.querySelectorAll("thead th:not([hidden])").length;
  table.dataset.columns = String(shown);
  // The "nothing here" row spans the columns, so it has to follow them.
  table.querySelectorAll("td[data-empty]").forEach((cell) => { cell.colSpan = shown; });
}

/**
 * Where the chooser stops being a popover and becomes a sheet.
 *
 * 48rem is the module's own tablet break -- the width at which side-by-side
 * layouts stack. A popover anchored to a control near the edge of a phone has
 * nowhere to go; below this width the same controls open as a modal sheet
 * instead of being pushed off screen.
 */
const SHEET_QUERY = "(max-width: 48rem)";

/** A column the reader may not put away, either because it identifies the row or because its owner said so. */
function isMandatory(column) {
  return column.tier === IDENTITY || column.mandatory === true;
}

/** The <table> a control acts on, resolved late: the page may not have rendered it yet. */
function resolveTable(table) {
  const node = typeof table === "function" ? table() : table;
  if (!node) return null;
  if (typeof node.matches === "function" && node.matches("table")) return node;
  return typeof node.querySelector === "function" ? node.querySelector("table") : null;
}

/**
 * Keep the panel inside the window.
 *
 * Anchored to the reading edge it can still overrun the other one -- a control
 * near the corner, or a panel wider than what is left beside it. The correction
 * is measured rather than guessed: whatever crossed the edge is pushed back by
 * exactly that much, and the gutter it stops short of is a stylesheet value, so
 * the spacing stays with the rest of the design system.
 *
 * The shift is physical pixels on purpose. `getBoundingClientRect` reports the
 * viewport's own axes, so translateX moves in the same direction the overflow
 * was measured in -- which is what makes one calculation correct in both
 * writing directions.
 */
function positionPanel(container, panel) {
  panel.style.removeProperty("--data-table-popover-shift");
  panel.style.removeProperty("--data-table-popover-max-block");
  panel.classList.remove("data-table-columns__panel--above");

  const gutter = Number.parseFloat(
    getComputedStyle(panel).getPropertyValue("--data-table-popover-gutter"),
  ) || 0;

  const anchor = container.getBoundingClientRect();
  const natural = panel.getBoundingClientRect();
  // The offset the stylesheet puts between button and panel, measured rather
  // than repeated here, so the two cannot drift apart.
  const gap = natural.top - anchor.bottom;
  const roomBelow = window.innerHeight - gutter - (anchor.bottom + gap);
  const roomAbove = anchor.top - gap - gutter;

  /* Flip only when above is genuinely roomier -- a panel that jumps to a side
     with even less space has moved for nothing. Whichever side it ends on, it
     is then capped to what that side actually has, so a long list scrolls
     inside itself instead of running off the screen. */
  let room = roomBelow;
  if (natural.height > roomBelow && roomAbove > roomBelow) {
    panel.classList.add("data-table-columns__panel--above");
    room = roomAbove;
  }
  if (natural.height > room) {
    panel.style.setProperty("--data-table-popover-max-block", `${Math.max(0, Math.floor(room))}px`);
  }

  // Measured after the height is settled: capping it can add a scrollbar, and
  // a scrollbar changes the width this has to keep on screen.
  const settled = panel.getBoundingClientRect();
  const overflowStart = gutter - settled.left;
  const overflowEnd = settled.right - (window.innerWidth - gutter);
  const shift = overflowStart > 0 ? overflowStart : overflowEnd > 0 ? -overflowEnd : 0;
  if (shift) panel.style.setProperty("--data-table-popover-shift", `${Math.round(shift)}px`);
}

/**
 * The control that puts columns away and brings them back.
 *
 * One list of checkboxes with two homes. On a wide screen it sits in a popover
 * beside its button; below the tablet break the same element is moved into a
 * modal sheet, where a touch has room and nothing can be pushed off screen.
 *
 * It is moved, not rebuilt. A reader who turns the phone while the chooser is
 * open finds the same ticks in the other container, because they are the same
 * inputs -- there is no second copy that could disagree with the first.
 *
 * Mandatory columns are listed and locked rather than hidden from the list: a
 * reader looking for a column they can see needs to find it and learn that it
 * stays, not fail to find it at all.
 */
export function createColumnControl({
  name,
  columns,
  visible,
  onToggle,
  table,
  label = "ستون‌ها",
  title = "نمایش ستون‌ها",
}) {
  const container = element("div", "data-table-columns");

  const panel = element("div", "data-table-columns__panel");
  panel.id = `${name}-columns-panel`;
  panel.hidden = true;

  const toggle = element("button", "button button--ghost button--small data-table-columns__toggle");
  toggle.type = "button";
  toggle.append(element("span", "data-table-columns__icon", "☷"));
  toggle.append(element("span", "data-table-columns__label", label));
  toggle.setAttribute("aria-controls", panel.id);
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-haspopup", "dialog");
  // The label is hidden on a small screen to leave the icon alone; the name has
  // to survive that, so it is stated here rather than left to the text node.
  toggle.setAttribute("aria-label", label);
  toggle.title = label;

  /* One change, applied everywhere it has to land. Callers that still pass
     `onToggle` keep working: the set operations are idempotent, and the table
     is only touched here when this control was given one. */
  const applyColumn = (key, on) => {
    if (on) visible.add(key);
    else visible.delete(key);
    if (table) applyColumnVisibility(resolveTable(table), key, on);
    if (onToggle) onToggle(key, on);
  };

  const set = element("fieldset", "data-table-columns__set");
  set.append(element("legend", "data-table-columns__title", title));
  const list = element("div", "data-table-columns__list");
  const boxes = new Map();

  columns.forEach((column) => {
    const option = element("label", "data-table-columns__option");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = column.key;
    box.checked = visible.has(column.key);
    if (isMandatory(column)) {
      box.checked = true;
      box.disabled = true;
      option.classList.add("data-table-columns__option--locked");
      option.title = "این ستون همیشه نمایش داده می‌شود.";
    } else {
      box.addEventListener("change", () => applyColumn(column.key, box.checked));
    }
    boxes.set(column.key, box);
    option.append(box, element("span", "data-table-columns__option-label", column.label));
    list.append(option);
  });
  set.append(list);

  const footer = element("div", "data-table-columns__footer");
  const reset = element("button", "button button--ghost button--small", "بازنشانی");
  reset.type = "button";
  // Recomputed rather than remembered: the default for a phone is not the
  // default for a desktop, and the reader is on one of them right now.
  reset.addEventListener("click", () => {
    const defaults = defaultVisibleColumns(columns);
    columns.forEach((column) => {
      const box = boxes.get(column.key);
      if (!box || box.disabled) return;
      const on = defaults.has(column.key);
      if (box.checked === on) return;
      box.checked = on;
      applyColumn(column.key, on);
    });
  });
  const done = element("button", "button button--primary button--small data-table-columns__done", "بستن");
  done.type = "button";
  done.hidden = true;
  footer.append(reset, done);
  set.append(footer);

  panel.append(set);
  container.append(toggle, panel);

  /* --- opening, closing, and moving between the two homes ---------------- */

  let sheet = null;
  let watcher = null;

  const sheetWanted = () =>
    typeof globalThis.matchMedia === "function" && globalThis.matchMedia(SHEET_QUERY).matches;

  const isOpen = () => toggle.getAttribute("aria-expanded") === "true";

  const onDocumentPointerDown = (event) => {
    if (!container.contains(event.target)) close();
  };
  const onDocumentKeyDown = (event) => {
    if (event.key === "Escape") close();
  };
  /* The sheet is a child of <body>, not of the mount, so a route change tears
     down the table it belongs to and leaves the sheet standing over the next
     page. Routing here is the address bar, so that is what to listen to. */
  const onNavigate = () => close();

  function openPopover() {
    panel.hidden = false;
    container.append(panel);
    if (!panel.contains(set)) panel.append(set);
    done.hidden = true;
    positionPanel(container, panel);
    document.addEventListener("pointerdown", onDocumentPointerDown, true);
    document.addEventListener("keydown", onDocumentKeyDown);
  }

  function closePopover() {
    document.removeEventListener("pointerdown", onDocumentPointerDown, true);
    document.removeEventListener("keydown", onDocumentKeyDown);
    panel.hidden = true;
    panel.style.removeProperty("--data-table-popover-shift");
    panel.classList.remove("data-table-columns__panel--above");
  }

  function openSheet() {
    // `confirm-dialog` is the module's dialog surface, and one of the three
    // roots base.css scopes its element rules to -- a dialog outside that list
    // would render with the host page's element styles instead of this one's.
    const dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog data-table-columns__dialog";
    dialog.setAttribute("aria-label", title);
    dialog.append(set);
    done.hidden = false;
    document.body.append(dialog);
    sheet = dialog;

    /* A dialog's `close` event arrives in a later task, so this cannot be the
       only place the button's state is put right -- anything that closed it
       deliberately would look open until the event landed. Whoever closes it on
       purpose clears `sheet` first and reports it themselves; reaching here
       still holding it means Escape or the backdrop did it, and then this is
       the only report there will be. */
    dialog.addEventListener("close", () => {
      if (!panel.contains(set)) panel.append(set);
      dialog.remove();
      if (sheet !== dialog) return;
      sheet = null;
      markClosed();
    });

    // Escape and the focus trap come from showModal; the return to the button
    // that opened it comes from here.
    showAccessibleDialog(dialog, {
      opener: toggle,
      initialFocus: () => dialog.querySelector("input:not(:disabled)"),
    });
  }

  /** Take the sheet down without letting its late `close` event speak for us. */
  function dismissSheet() {
    const open = sheet;
    sheet = null;
    open?.close();
  }

  function markClosed() {
    toggle.setAttribute("aria-expanded", "false");
    window.removeEventListener("hashchange", onNavigate);
    if (watcher) {
      watcher.removeEventListener("change", onBreakpointChange);
      watcher = null;
    }
  }

  function onBreakpointChange() {
    if (!isOpen()) return;
    // Crossing the break with the chooser open: hand the same element to the
    // other container rather than closing on the reader mid-choice.
    if (sheetWanted()) {
      if (sheet) return;
      closePopover();
      openSheet();
    } else {
      if (!sheet) return;
      dismissSheet();
      openPopover();
    }
  }

  function open() {
    if (sheetWanted()) openSheet();
    else openPopover();
    toggle.setAttribute("aria-expanded", "true");
    window.addEventListener("hashchange", onNavigate);
    if (typeof globalThis.matchMedia === "function") {
      watcher = globalThis.matchMedia(SHEET_QUERY);
      watcher.addEventListener("change", onBreakpointChange);
    }
  }

  function close() {
    if (sheet) {
      // The sheet returns focus to its opener itself, so this must not.
      markClosed();
      dismissSheet();
      return;
    }
    closePopover();
    markClosed();
    toggle.focus({ preventScroll: true });
  }

  done.addEventListener("click", close);
  toggle.addEventListener("click", () => {
    if (isOpen()) close();
    else open();
  });

  return container;
}

/**
 * Build the scrollable, pinned table.
 *
 * `cells` is handed a row and returns what belongs under each column key -- a
 * string or a node. A key it leaves out renders an empty cell, which is a cell
 * with nothing in it rather than a column out of step with its header.
 */
/**
 * One summary row per group, its members folded underneath until pressed.
 *
 * Where several rows belong to one parent -- items of an activity, lines of a
 * document -- reading them flat means reading the parent's name once and then
 * five rows that do not say what they belong to. Folded, the table is a list of
 * parents; opened, one parent's rows appear under it in the same columns.
 *
 * The press target is a real button inside the identity cell, so it is reachable
 * by keyboard and states what it did. The rest of the row delegates to it, so a
 * pointer can press anywhere along it.
 */
function appendGroupedRows({ body, columns, rows, cells, rowAttributes, visible, group }) {
  const order = [];
  const members = new Map();
  rows.forEach((row) => {
    const key = String(group.key(row));
    if (!members.has(key)) { members.set(key, []); order.push(key); }
    members.get(key).push(row);
  });

  order.forEach((key, index) => {
    const mine = members.get(key);
    const summary = document.createElement("tr");
    summary.className = "data-table__group";
    summary.dataset.group = key;
    const content = group.cells(mine, key);
    const toggle = element("button", "data-table__disclosure");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    // Wrapped, so a name and the code under it stay stacked rather than becoming
    // two flex items side by side.
    const name = element("span", "data-table__disclosure-name");
    name.append(content.identity ?? document.createTextNode(key));
    toggle.append(name);
    toggle.append(element("span", "data-table__disclosure-count",
      `${mine.length} ${group.countLabel ?? "قلم"}`));

    columns.forEach((column) => {
      const value = column.key === "identity" ? toggle : content[column.key];
      const cell = element("td", column.cellClass ?? "", typeof value === "string" ? value : "");
      cell.dataset.col = column.key;
      if (value != null && typeof value !== "string") cell.append(value);
      cell.hidden = !visible.has(column.key);
      summary.append(cell);
    });
    body.append(summary);

    const children = mine.map((row) => {
      const tr = document.createElement("tr");
      tr.className = "data-table__child";
      tr.dataset.group = key;
      tr.hidden = true;
      const extra = rowAttributes ? rowAttributes(row) : null;
      if (extra?.className) tr.classList.add(...extra.className.split(" "));
      if (extra?.tabIndex !== undefined) tr.tabIndex = extra.tabIndex;
      const values = cells(row);
      columns.forEach((column) => {
        const value = values[column.key];
        const cell = element("td", column.cellClass ?? "", typeof value === "string" ? value : "");
        cell.dataset.col = column.key;
        if (value != null && typeof value !== "string") cell.append(value);
        cell.hidden = !visible.has(column.key);
        tr.append(cell);
      });
      body.append(tr);
      return tr;
    });

    const setOpen = (open) => {
      toggle.setAttribute("aria-expanded", String(open));
      summary.classList.toggle("data-table__group--open", open);
      children.forEach((child) => { child.hidden = !open; });
    };
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    // Anywhere along the row, but not on a control that means something else.
    summary.addEventListener("click", (event) => {
      if (event.target.closest("button, a, input, select")) return;
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    void index;
  });
}

/**
 * A table with its own column control above it.
 *
 * For a table whose caller has nowhere obvious to put the control -- no heading
 * row of its own to hang it from. The toolbar is the table's, so the page that
 * renders it needs to know nothing about columns.
 */
export function createDataTableWithControl({ name, columns, visible, controlLabel, ...config }) {
  const fragment = document.createDocumentFragment();
  const toolbar = element("div", "data-table-toolbar");
  const table = createDataTable({ ...config, columns, visible });
  toolbar.append(createColumnControl({ name, columns, visible, label: controlLabel, table }));
  fragment.append(toolbar, table);
  return fragment;
}

export function createDataTable({ caption, scrollLabel, className = "", columns, rows, cells, rowAttributes, visible, group, emptyMessage }) {
  const scroll = element("div", "table-scroll data-table-scroll");
  // The same affordance the comparison chart's table uses: a named region the
  // keyboard can reach and scroll, not a pane only a pointer can move.
  scroll.setAttribute("role", "region");
  if (scrollLabel) scroll.setAttribute("aria-label", scrollLabel);
  scroll.tabIndex = 0;

  const table = element("table", `data-table data-table--pinned ${className}`.trim());
  table.dataset.columns = String(visible.size);
  if (caption) table.append(tableCaption(caption));

  const head = tableHead(columns.map((column) => column.label));
  [...head.querySelectorAll("th")].forEach((cell, index) => {
    cell.dataset.col = columns[index].key;
    cell.hidden = !visible.has(columns[index].key);
  });

  const body = document.createElement("tbody");
  if (!rows.length && emptyMessage) {
    const tr = document.createElement("tr");
    const cell = element("td", "data-table__empty", emptyMessage);
    cell.colSpan = visible.size;
    cell.dataset.empty = "true";
    tr.append(cell);
    body.append(tr);
  } else if (group) appendGroupedRows({ body, columns, rows, cells, rowAttributes, visible, group });
  else if (rows.length) rows.forEach((row) => {
    const tr = document.createElement("tr");
    const extra = rowAttributes ? rowAttributes(row) : null;
    if (extra?.className) tr.className = extra.className;
    if (extra?.tabIndex !== undefined) tr.tabIndex = extra.tabIndex;
    const content = cells(row);
    columns.forEach((column) => {
      const value = content[column.key];
      const cell = element("td", column.cellClass ?? "", typeof value === "string" ? value : "");
      cell.dataset.col = column.key;
      if (value != null && typeof value !== "string") cell.append(value);
      cell.hidden = !visible.has(column.key);
      tr.append(cell);
    });
    body.append(tr);
  });

  table.append(head, body);
  scroll.append(table);
  return scroll;
}
