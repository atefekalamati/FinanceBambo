/**
 * The DOM helpers every finance surface builds its markup from.
 *
 * Markup is always constructed node by node — never through innerHTML — so a
 * value that later comes from Backend data or user input cannot be parsed as
 * markup by accident.
 */

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Builds a <thead> with one header cell per label. A label may be an empty
 * string for an action column, in which case pass [label, accessibleName] so
 * the column still announces itself to assistive technology.
 */
export function tableHead(labels) {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  labels.forEach((entry) => {
    const [label, accessibleName] = Array.isArray(entry) ? entry : [entry, ""];
    const cell = element("th", "", label);
    if (accessibleName) cell.setAttribute("aria-label", accessibleName);
    row.append(cell);
  });
  head.append(row);
  return head;
}

/** A visually hidden <caption>; every data table needs one to be navigable. */
export function tableCaption(text) {
  return element("caption", "sr-only", text);
}
