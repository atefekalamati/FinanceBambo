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
 * The control that puts columns away and brings them back.
 *
 * A button that owns a panel, told apart by aria-expanded -- the same disclosure
 * the items page uses for its resource list. The identity column is not offered.
 */
export function createColumnControl({ name, columns, visible, onToggle, label = "ستون‌ها" }) {
  const container = element("div", "data-table-columns");
  const panel = element("div", "data-table-columns__panel");
  panel.id = `${name}-columns-panel`;
  panel.hidden = true;
  const toggle = element("button", "button button--ghost button--small data-table-columns__toggle", label);
  toggle.type = "button";
  toggle.setAttribute("aria-controls", panel.id);
  toggle.setAttribute("aria-expanded", "false");
  toggle.addEventListener("click", () => {
    const open = panel.hidden;
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  });
  const set = element("fieldset", "data-table-columns__set");
  set.append(element("legend", "", "ستون‌های قابل نمایش"));
  columns.filter((column) => column.tier !== IDENTITY).forEach((column) => {
    const option = element("label", "data-table-columns__option");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = column.key;
    box.checked = visible.has(column.key);
    box.addEventListener("change", () => onToggle(column.key, box.checked));
    option.append(box, element("span", "", column.label));
    set.append(option);
  });
  panel.append(set);
  container.append(toggle, panel);
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
  toolbar.append(createColumnControl({
    name,
    columns,
    visible,
    label: controlLabel,
    onToggle: (key, on) => {
      if (on) visible.add(key);
      else visible.delete(key);
      applyColumnVisibility(table.querySelector("table"), key, on);
    },
  }));
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
