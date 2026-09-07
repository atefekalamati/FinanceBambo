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
  table.dataset.columns = String(table.querySelectorAll("thead th:not([hidden])").length);
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
export function createDataTable({ caption, scrollLabel, className = "", columns, rows, cells, rowAttributes, visible }) {
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
  rows.forEach((row) => {
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
