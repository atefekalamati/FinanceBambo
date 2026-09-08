/**
 * Which Finance items an operational page should show.
 *
 * One database holds items from three different origins: the schedule the
 * project is running on, items people entered themselves, and items a local
 * test seed invented by turning every schedule TASK into a cost item. The third
 * kind is the reason this module exists — a task is work, an item is a thing
 * bought, and a page that lists «اجرای رابیتس بندی نما» as a cost item is
 * showing a task where an item belongs.
 *
 * The rule below hides. It never deletes, and it never decides anything from a
 * name or a look: three independent facts must coincide before a row is treated
 * as seed-made, and even then a row a person has actually used stays. Hiding a
 * real item is the expensive mistake here, so every rule is written to fail
 * towards showing.
 */

/** `MSP-T<task uid>` — the code shape the seed wrote. On its own, meaningless: it is free text. */
const SEED_TASK_CODE = /^MSP-T(\d+)$/i;

/**
 * True when all three of the seed's marks coincide on one row: it carries no
 * schedule resource identity, its code is `MSP-T<n>`, and its
 * `externalResourceId` is that same `<n>` — which is how the seed wrote the
 * task's uid into both fields. Any one of the three alone matches things it
 * should not, so all three are required.
 *
 * For an irreversible operation this is not the test to use: the seed derives
 * each id as `uuid5(<namespace>, "<project>|task|<task uid>")`, and recomputing
 * that is arithmetic no one can imitate by typing. For hiding a row from a list,
 * these three facts are enough and need nothing the API does not already send.
 */
export function isSeedTaskResource(resource) {
  if (!resource) return false;
  if (resource.sourceResourceUid != null) return false;
  const match = SEED_TASK_CODE.exec(String(resource.code ?? "").trim());
  if (!match) return false;
  return String(resource.externalResourceId ?? "").trim() === match[1];
}

/**
 * True when the item belongs in an operational list.
 *
 * A seed-made row still counts as active once somebody has used it — an invoice
 * names it, or somebody priced it. The backend answers that question in
 * `hasOperationalRecords`, because it is the only place that can see invoices
 * and prices at once; a client that receives nothing there is told nothing, and
 * an untold row is treated as untouched rather than as used.
 */
export function isActiveFinanceResource(resource) {
  if (!resource) return false;
  return !isSeedTaskResource(resource) || resource.hasOperationalRecords === true;
}

/**
 * The items to list, and how many were withheld.
 *
 * Withheld, never removed: the rows stay in the database, the API still returns
 * them, and every count returned here exists so a page can say what it is not
 * showing instead of quietly showing less.
 */
export function selectActiveResources(resources = []) {
  const rows = [];
  let withheldCount = 0;
  resources.forEach((resource) => {
    if (isActiveFinanceResource(resource)) rows.push(resource);
    else withheldCount += 1;
  });
  return { rows, withheldCount };
}
