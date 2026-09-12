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
import { formatDisplayNumber } from "../formatters/display.js";
import {
  ROW_COUNT_OPTIONS,
  clampPage,
  getRowsPerPage,
  pageCount,
  resolveSize,
  setRowsPerPage,
} from "../preferences/rows-per-page.js";
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
/** The widths a tier decides anything at. The live watcher below listens to these. */
const PHONE_QUERY = "(max-width: 36rem)";
const TABLET_QUERY = "(max-width: 64rem)";

export function defaultVisibleColumns(columns, matchMedia = globalThis.matchMedia) {
  const matches = (query) => typeof matchMedia === "function" && matchMedia(query).matches;
  const keys = (keep) => new Set(columns.filter(keep).map((column) => column.key));
  if (matches(PHONE_QUERY)) return keys((column) => column.tier !== SECONDARY);
  if (matches(TABLET_QUERY)) return keys((column) => column.tier !== SECONDARY || column.keepOnTablet);
  return keys(() => true);
}

/**
 * Sets of visible columns a reader has chosen for themselves.
 *
 * `defaultVisibleColumns` answers for a width, and it used to be asked once --
 * so a table opened on a desktop and then turned to a phone kept all nine
 * columns, 1584px of them inside a 335px screen, with the tier system that
 * exists to prevent exactly that having already run and finished.
 *
 * It is asked again now, on every render and on every crossing of a tier. But
 * only for a table nobody has touched: a reader who put a column away meant it,
 * and having a rotation undo that would be worse than the scroll.
 *
 * Weak, so a Set belonging to a page that has gone away is not held by this.
 */
const CHOSEN_BY_READER = new WeakSet();

/** The columns to draw: the reader's choice if they made one, else the width's. */
function effectiveColumns(columns, visible) {
  return CHOSEN_BY_READER.has(visible) ? visible : defaultVisibleColumns(columns);
}

/**
 * Re-apply the width's answer to every table that has not been chosen for.
 *
 * WHY THIS READS THE DOM AND HOLDS NOTHING
 * A `matchMedia` listener lives as long as the page does, and there is no unmount
 * hook here to remove one -- `paint()` replaces the tree and tells nobody. Two
 * earlier attempts registered a listener per table and per visible-Set, and both
 * leaked: measured with forced collection, 23 listeners and 634 nodes became 540
 * and 8644 over three navigation cycles, because the callback held the columns
 * and the columns held the detached tree.
 *
 * So this one is registered once, for the life of the module, and closes over
 * nothing. Everything it needs is on the elements: each header cell carries its
 * tier, and a table the reader has touched carries `data-columns-chosen`. It
 * finds the tables in the document when it runs, and forgets them again.
 */
let watchingTiers = false;

function reapplyTierDefaults() {
  const phone = globalThis.matchMedia(PHONE_QUERY).matches;
  const tablet = globalThis.matchMedia(TABLET_QUERY).matches;
  document.querySelectorAll("table[data-tiered]").forEach((table) => {
    if (table.dataset.columnsChosen === "true") return;
    table.querySelectorAll("thead th[data-col]").forEach((cell) => {
      const secondary = cell.dataset.tier === SECONDARY;
      const keep = cell.dataset.keepTablet === "true";
      const on = !secondary || (tablet && !phone ? keep : !tablet);
      applyColumnVisibility(table, cell.dataset.col, on);
    });
  });
}

function watchTierDefaults() {
  if (watchingTiers || typeof globalThis.matchMedia !== "function") return;
  watchingTiers = true;
  [PHONE_QUERY, TABLET_QUERY].forEach((query) => {
    globalThis.matchMedia(query).addEventListener("change", reapplyTierDefaults);
  });
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
    /* From here the width stops deciding for this table. Recorded twice on
       purpose: in the Set for the next render, and on the element for the tier
       watcher, which reads the document and cannot see a Set. */
    CHOSEN_BY_READER.add(visible);
    const node = resolveTable(table);
    if (node) {
      node.dataset.columnsChosen = "true";
      applyColumnVisibility(node, key, on);
    }
    if (onToggle) onToggle(key, on);
  };

  const set = element("fieldset", "data-table-columns__set");
  set.append(element("legend", "data-table-columns__title", title));
  const list = element("div", "data-table-columns__list");
  const boxes = new Map();

  /* The ticks say what the table is doing, which is the width's answer until the
     reader gives one of their own. Reading `visible` directly would show a phone
     reader eight ticks over a three-column table. */
  const shownNow = effectiveColumns(columns, visible);
  columns.forEach((column) => {
    const option = element("label", "data-table-columns__option");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = column.key;
    box.checked = shownNow.has(column.key);
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

  /* Read back from the table rather than from anything remembered.
     The tier watcher changes a table on a rotation and holds no reference to
     these inputs -- that is what keeps it from leaking -- so a chooser opened
     after one would otherwise show eight ticks over a three-column table. The
     element it is about is the one place both agree. */
  function syncBoxes() {
    const node = resolveTable(table);
    if (!node) return;
    boxes.forEach((box, key) => {
      if (box.disabled) return;
      const cell = node.querySelector(`thead th[data-col="${key}"]`);
      if (cell) box.checked = !cell.hidden;
    });
  }

  function open() {
    syncBoxes();
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
      const repeatedLabel = repeatedGroupColumnLabel(column, value, group.showColumnLabelsWhenOpen);
      if (repeatedLabel) {
        const label = element("span", "data-table__group-column-label", repeatedLabel);
        // The table header already names this cell for assistive technology.
        // This copy is only a visual wayfinding aid after a long vertical scroll.
        label.setAttribute("aria-hidden", "true");
        cell.append(label);
      }
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
 * A folded parent may repeat the names of its otherwise-empty columns while it
 * is open. The page opts in; populated cells and the identity cell keep their
 * real content, and an action column may use its accessible label when its
 * visible heading is intentionally empty.
 */
export function repeatedGroupColumnLabel(column, value, enabled = false) {
  if (!enabled || column.key === "identity" || (value !== null && value !== undefined && value !== "")) return "";
  const [visibleLabel, accessibleLabel] = Array.isArray(column.label)
    ? column.label
    : [column.label, ""];
  return String(visibleLabel || accessibleLabel || "");
}

/**
 * The chips that say what the table is filtered to.
 *
 * They are the filter, not a description of one: pressing a chip is the whole
 * gesture, which is why there is no apply button beside them. Each is a real
 * button carrying aria-pressed, so what is on is announced rather than only
 * coloured, and label and count sit on one line -- a chip is a word and a
 * number, not a small card.
 *
 * Counts arrive already written. Formatting a number is the page's business
 * (which digits, which locale); a chip only has to place it.
 */
export function createFilterChips({ items, active, onSelect, label = "فیلتر جدول" }) {
  const rail = element("div", "data-table-chips");
  rail.setAttribute("role", "group");
  rail.setAttribute("aria-label", label);
  items.forEach((item) => {
    const chip = element("button", `data-table-chip${item.tone ? ` data-table-chip--${item.tone}` : ""}`);
    chip.type = "button";
    chip.dataset.chip = item.key;
    chip.setAttribute("aria-pressed", String(item.key === active));
    chip.append(element("span", "data-table-chip__label", item.label));
    const count = element("span", "data-table-chip__count numeric");
    count.hidden = item.count === undefined || item.count === null;
    count.textContent = count.hidden ? "" : String(item.count);
    chip.append(count);
    chip.addEventListener("click", () => onSelect(item.key));
    rail.append(chip);
  });
  return rail;
}

/**
 * Move the pressed state and the counts without rebuilding the rail.
 *
 * A page that repaints on every read would otherwise replace the toolbar under
 * the reader's hands -- and with it the search box they are typing into. Kept
 * in place, the caret stays where it was.
 */
export function updateFilterChips(rail, { active, counts = {} } = {}) {
  if (!rail) return;
  rail.querySelectorAll(".data-table-chip").forEach((chip) => {
    const key = chip.dataset.chip;
    if (active !== undefined) chip.setAttribute("aria-pressed", String(key === active));
    if (!(key in counts)) return;
    const count = chip.querySelector(".data-table-chip__count");
    if (!count) return;
    count.hidden = counts[key] === undefined || counts[key] === null;
    count.textContent = count.hidden ? "" : String(counts[key]);
  });
}

/**
 * Looking for something in the table.
 *
 * Reports after a pause rather than per keystroke, because the caller behind
 * this may be a request. Enter and the input's own clear button skip the pause,
 * since both are someone saying they have finished typing.
 *
 * What "matching" means is never decided here -- the caller is handed the text
 * and does its own filtering, server-side or in the page, whichever it already
 * did.
 */
export function createTableSearch({
  value = "",
  onSearch,
  placeholder = "جست‌وجو در جدول…",
  label = "جست‌وجو در جدول",
  delay = 300,
}) {
  const field = element("div", "data-table-search");
  const input = element("input", "app-input data-table-search__input");
  input.type = "search";
  input.value = value;
  input.placeholder = placeholder;
  input.setAttribute("aria-label", label);

  let timer = null;
  let reported = value.trim();
  const report = () => {
    clearTimeout(timer);
    const next = input.value.trim();
    if (next === reported) return;
    reported = next;
    onSearch(next);
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(report, delay);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    report();
  });
  // Fired by the clear button a search input draws for itself.
  input.addEventListener("search", report);

  field.append(input);
  return field;
}

/**
 * Repaint without dropping the caret.
 *
 * A page that rebuilds its tree detaches whatever had focus, and a detached
 * element is blurred even when the very same node goes straight back -- which
 * is exactly what happens to a search box while someone is typing into it, on
 * the reload their own typing asked for.
 *
 * Reaching for the element afterwards rather than before is what makes this
 * work for a toolbar that is moved rather than rebuilt: the node is the same
 * one, so restoring its focus restores the reader's place.
 */
export function repaintPreservingFocus(repaint) {
  const active = document.activeElement;
  let caret = null;
  try {
    caret = [active.selectionStart, active.selectionEnd, active.selectionDirection];
  } catch {
    // Not a field that carries a selection; focus alone is enough.
  }

  repaint();

  if (!(active instanceof HTMLElement) || !active.isConnected || active === document.activeElement) return;
  active.focus({ preventScroll: true });
  if (!caret || caret[0] === null) return;
  try {
    active.setSelectionRange(caret[0], caret[1], caret[2] ?? "none");
  } catch {
    // The field kept its own idea of where the caret goes.
  }
}

/**
 * The row above a table: what it is filtered to, what is being looked for, and
 * which columns are showing.
 *
 * Three controls with three jobs, in one row so the reader reads them as one
 * set. Anything a table grows later belongs here too rather than beside it.
 */
export function createTableToolbar({ chips, search, name, columns, visible, table, controlLabel }) {
  const toolbar = element("div", "data-table-toolbar");
  if (chips) toolbar.append(createFilterChips(chips));
  const tools = element("div", "data-table-toolbar__tools");
  if (search) tools.append(createTableSearch(search));
  if (columns) tools.append(createColumnControl({ name, columns, visible, label: controlLabel, table }));
  toolbar.append(tools);
  return toolbar;
}

/**
 * The strip under a table: which page of it is shown, and how much of it fits
 * on a page.
 *
 * ONE FOOTER, TWO KINDS OF TABLE
 * Most tables here arrive whole -- the server answers `GET /price-history` with
 * every version and the browser holds all of them -- so turning a page is
 * slicing an array it already has. فاکتورها is the exception and always was:
 * invoices have no ceiling, one row per purchase for the life of a project, so
 * that endpoint pages server-side and the browser never holds more than the
 * page it asked for.
 *
 * The difference is real and cannot be hidden from the caller, but it can be
 * hidden from the reader, and this is where. A caller that pages server-side
 * passes `onPageChange` and gets a footer that calls it; one that slices its own
 * array passes the same callback and slices instead. Both draw the same controls
 * in the same place, so two kinds of table are not two kinds of page to learn.
 *
 * WHY THE SIZE CONTROL IS HERE AND NOT IN THE TOOLBAR ABOVE
 * It answers a question about the bottom of the table -- "how far do I scroll
 * before this ends" -- and it is asked on arriving there. The toolbar carries
 * what narrows the rows; this carries what portions them.
 */
export function createTablePagination({
  name,
  page = 1,
  total = 0,
  pageSize,
  onPageChange,
  onPageSizeChange,
  label = "صفحه‌بندی جدول",
} = {}) {
  const chosen = pageSize ?? getRowsPerPage(name);
  const size = resolveSize(chosen, total);
  const pages = pageCount(total, size);
  const current = clampPage(page, total, size);

  const nav = element("nav", "table-pagination");
  nav.setAttribute("aria-label", label);

  const steps = element("div", "table-pagination__steps");
  const previous = element("button", "button button--ghost", "صفحه قبل");
  previous.type = "button";
  previous.disabled = current <= 1;
  previous.addEventListener("click", () => onPageChange?.(current - 1));
  const position = element("span", "table-pagination__position numeric",
    `صفحه ${formatDisplayNumber(String(current))} از ${formatDisplayNumber(String(pages))}`);
  const next = element("button", "button button--ghost", "صفحه بعد");
  next.type = "button";
  next.disabled = current >= pages;
  next.addEventListener("click", () => onPageChange?.(current + 1));
  steps.append(previous, position, next);

  const sizing = element("div", "table-pagination__sizing");
  const selectId = `rows-per-page-${name}`;
  const caption = element("label", "table-pagination__label", "سطر در هر صفحه");
  caption.htmlFor = selectId;
  const select = element("select", "app-input table-pagination__select");
  select.id = selectId;
  ROW_COUNT_OPTIONS.forEach((option) => {
    const item = element("option", "", option === "all" ? "همه" : formatDisplayNumber(String(option)));
    item.value = String(option);
    item.selected = String(option) === String(chosen);
    select.append(item);
  });
  select.addEventListener("change", () => {
    const stored = setRowsPerPage(name, select.value);
    // Back to the first page, not the same number on a different scale: page 7
    // of 9 at ten rows and page 7 of 1 at a hundred are not the same place, and
    // the reader chose a size, not a destination.
    onPageSizeChange?.(stored);
  });
  sizing.append(caption, select);

  // How many of how many, so a capped "all" says so rather than looking like the
  // whole list.
  const shown = Math.min(size, Math.max(total - (current - 1) * size, 0));
  const counted = element("span", "table-pagination__count numeric",
    `${formatDisplayNumber(String(shown))} از ${formatDisplayNumber(String(total))} سطر`);

  nav.append(steps, counted, sizing);
  return nav;
}

/**
 * A table that arrived whole, drawn one page at a time.
 *
 * The page holds the number; this holds everything that follows from it. Given
 * every row and which page is wanted, it slices, builds the table from the same
 * factory every other table uses, and puts the footer under it. The caller's
 * `onChange` is handed the page to move to, and re-renders however it already
 * re-renders -- this owns no state, because a component that remembered which
 * page it was on would disagree with the page that also remembered.
 *
 * `rows` is whatever the caller has already filtered. Paging is the last thing
 * that happens to a list, never the first: slicing before filtering would search
 * one page and report the rest as absent.
 */
export function createPagedDataTable({ name, rows, page = 1, pageSize, onChange, paginationLabel, ...config }) {
  const chosen = pageSize ?? getRowsPerPage(name);
  const size = resolveSize(chosen, rows.length);
  const current = clampPage(page, rows.length, size);
  const start = (current - 1) * size;

  const fragment = document.createDocumentFragment();
  fragment.append(createDataTable({ ...config, rows: rows.slice(start, start + size) }));
  // A list that fits on one page has nothing to turn, but it still has a size to
  // choose -- that is how a reader gets back from ten rows to a hundred.
  fragment.append(createTablePagination({
    name,
    page: current,
    total: rows.length,
    pageSize: chosen,
    label: paginationLabel,
    onPageChange: (next) => onChange?.({ page: next, pageSize: chosen }),
    onPageSizeChange: (next) => onChange?.({ page: 1, pageSize: next }),
  }));
  return fragment;
}

/**
 * A table with its own toolbar above it.
 *
 * For a table whose caller has nowhere obvious to put the controls -- no
 * heading row of its own to hang them from. The toolbar is the table's, so the
 * page that renders it needs to know nothing about columns.
 */
export function createDataTableWithControl({ name, columns, visible, controlLabel, chips, search, onChange, page, pageSize, paginationLabel, ...config }) {
  const fragment = document.createDocumentFragment();
  // Paging is opt-in by passing a handler, so a table that has never needed it
  // is unchanged -- no footer, no slice, the rows it was given.
  const body = onChange
    ? createPagedDataTable({ ...config, name, columns, visible, page, pageSize, onChange, paginationLabel })
    : createDataTable({ ...config, columns, visible });
  // The toolbar's column control acts on a <table> it resolves late, and a
  // fragment cannot be queried for one -- so it is given the element itself
  // when there is one, and the document otherwise, which is what the paged
  // branch leaves behind once its fragment is appended.
  const table = body instanceof DocumentFragment ? body.querySelector("table") : body;
  fragment.append(
    createTableToolbar({ chips, search, name, columns, visible, table, controlLabel }),
    body,
  );
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
  /* The width's answer, recomputed now rather than trusted from whenever the
     page last asked -- unless the reader has chosen, in which case theirs is the
     answer. See `effectiveColumns`. */
  const shown = effectiveColumns(columns, visible);
  table.dataset.columns = String(shown.size);
  if (CHOSEN_BY_READER.has(visible)) table.dataset.columnsChosen = "true";
  /* Marked so the tier watcher can find it, with each column's tier written on
     its own header cell: that is what lets one listener serve every table in the
     document without holding a reference to any of them. */
  table.dataset.tiered = "true";
  if (caption) table.append(tableCaption(caption));
  watchTierDefaults();

  const head = tableHead(columns.map((column) => column.label));
  [...head.querySelectorAll("th")].forEach((cell, index) => {
    cell.dataset.col = columns[index].key;
    if (columns[index].tier) cell.dataset.tier = columns[index].tier;
    if (columns[index].keepOnTablet) cell.dataset.keepTablet = "true";
    cell.hidden = !shown.has(columns[index].key);
  });

  const body = document.createElement("tbody");
  if (!rows.length && emptyMessage) {
    const tr = document.createElement("tr");
    const cell = element("td", "data-table__empty", emptyMessage);
    cell.colSpan = shown.size;
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
      cell.hidden = !shown.has(column.key);
      tr.append(cell);
    });
    body.append(tr);
  });

  table.append(head, body);
  scroll.append(table);
  return scroll;
}
