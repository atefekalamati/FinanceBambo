/**
 * How many rows of a table a reader wants to see at once.
 *
 * Kept per table rather than once for the module. The tables are not alike: the
 * price list is scanned, so a hundred rows on one screen is the point of it,
 * while the settings revisions are read a few at a time and a hundred would
 * bury the page. One number for both would be wrong for one of them, and the
 * reader would have to keep changing it back.
 *
 * The choice is this browser's, like the display currency beside it. It never
 * reaches the server and never leaves the machine: it decides how much of an
 * answer to draw, not which answer to ask for -- so a shared value would be a
 * claim about a person made from one of their devices.
 */

const STORAGE_PREFIX = "bambo.finance.rowsPerPage.";

/** The offered steps. `ALL` is a ceiling, not a promise -- see `resolveSize`. */
export const ROW_COUNT_OPTIONS = Object.freeze([10, 25, 50, 100, "all"]);

export const DEFAULT_ROWS_PER_PAGE = 25;

/**
 * What "all" is allowed to mean.
 *
 * A table whose rows are already in the browser can draw every one of them, and
 * for the sizes this module sees -- 835 estimate lines on the reference project
 * -- that is a moment's work. It is still a ceiling rather than no limit: a row
 * here is a table row with cells, controls and a sparkline in it, and a project
 * ten times that size would be asking the browser to build tens of thousands of
 * elements because a menu offered the word "all". The footer says what it did
 * rather than silently drawing fewer.
 */
export const ALL_ROWS_CEILING = 500;

/** Kept in memory too, so a browser refusing storage still holds the choice. */
const memory = new Map();

function keyFor(name) {
  return `${STORAGE_PREFIX}${name}`;
}

function isOffered(value) {
  return ROW_COUNT_OPTIONS.some((option) => String(option) === String(value));
}

/**
 * The reader's choice for this table, or a default when they have made none.
 *
 * `fallback` is for a table whose starting size is settled elsewhere. فاکتورها
 * is the one: the PRD states the register opens at fifty rows, and that is a
 * product decision about that list rather than this module's taste, so the page
 * passes it rather than inheriting the twenty-five that suits the others.
 */
export function getRowsPerPage(name, fallback = DEFAULT_ROWS_PER_PAGE) {
  try {
    const stored = window.localStorage.getItem(keyFor(name));
    if (isOffered(stored)) return stored === "all" ? "all" : Number(stored);
  } catch {
    // Private windows and blocked site data both land here.
  }
  const held = memory.get(name);
  return held === undefined ? fallback : held;
}

export function setRowsPerPage(name, value) {
  if (!isOffered(value)) throw new TypeError("Unsupported rows-per-page value.");
  const normalized = value === "all" ? "all" : Number(value);
  memory.set(name, normalized);
  try {
    window.localStorage.setItem(keyFor(name), String(normalized));
  } catch {
    // The choice still applies to this render.
  }
  return normalized;
}

/**
 * How many rows to actually draw, given what the reader asked for and how many
 * there are. Returns a number, never "all", so callers never slice by a word.
 */
export function resolveSize(value, total) {
  if (value !== "all") return Math.max(Number(value) || DEFAULT_ROWS_PER_PAGE, 1);
  return Math.min(Math.max(total, 1), ALL_ROWS_CEILING);
}

/** Total pages for a row count and a page size, never below one. */
export function pageCount(total, size) {
  return Math.max(Math.ceil(Math.max(total, 0) / Math.max(size, 1)), 1);
}

/**
 * Keep a page number inside the pages that exist.
 *
 * Raising the row count shrinks the number of pages, so a reader on page 7 of 9
 * who switches from 10 rows to 100 is on a page that no longer exists. Landing
 * them on the last page keeps them near what they were reading, which an empty
 * page or a jump to the first would not.
 */
export function clampPage(page, total, size) {
  return Math.min(Math.max(Number(page) || 1, 1), pageCount(total, size));
}
