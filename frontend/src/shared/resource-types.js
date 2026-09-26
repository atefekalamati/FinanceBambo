/**
 * The three kinds of thing a project spends money on, and their names on screen.
 *
 *   material      — bought by quantity: kilograms, cubic metres, pieces.
 *   work          — bought by the hour: crews and machines alike.
 *   general_cost  — a lump sum with no quantity.
 *
 * Until 2026-09-26 the service split `work` into `labor` and `equipment`. No figure ever
 * depended on which, and MS Project — where every resource comes from — calls both WORK
 * without saying. So the service now has three kinds (migration 0038), and this module is
 * the frontend's single statement of them. Every label map that used to spell the four
 * out reads from here.
 *
 * THE OLD NAMES STILL ARRIVE. Rows stored before 0038 keep `labor` or `equipment` in the
 * database, and issued report snapshots are frozen with those words; the service
 * canonicalises what it reads, but a snapshot payload comes back as it was written. So a
 * type met anywhere is passed through `canonicalResourceType` first, and the old names
 * are `work` here exactly as they are on the service.
 */

export const RESOURCE_TYPES = Object.freeze(["material", "work", "general_cost"]);

/** What `work` used to be called. Read as `work`; never written again. */
export const LEGACY_WORK_TYPES = Object.freeze(["labor", "equipment"]);

/** `labor` and `equipment` are `work`; anything else comes back as it came. */
export function canonicalResourceType(value) {
  return LEGACY_WORK_TYPES.includes(value) ? "work" : value;
}

/**
 * The names. Two registers, because a form field and a chart axis do not want the same
 * length: the long one names the thing, the short one fits beside a bar.
 */
export const RESOURCE_TYPE_LABELS = Object.freeze({
  material: "مصالح",
  work: "نیرو و تجهیزات",
  general_cost: "هزینه‌های عمومی پروژه",
});

export const RESOURCE_TYPE_SHORT_LABELS = Object.freeze({
  material: "مصالح",
  work: "نیرو و تجهیزات",
  general_cost: "هزینه عمومی",
});

/** The label for any type the service has ever sent, or null for one it never has. */
export function resourceTypeLabel(value, labels = RESOURCE_TYPE_LABELS) {
  return labels[canonicalResourceType(value)] ?? null;
}

/**
 * Per-type rows folded onto the three kinds: two `labor` and `equipment` rows from an old
 * snapshot become one `work` row whose money fields are summed exactly, as strings of
 * integer rials. `fields` names the keys to sum; every other key is taken from the first
 * row of the group.
 */
export function foldLegacyTypes(rows, fields) {
  const byType = new Map();
  for (const row of rows ?? []) {
    const type = canonicalResourceType(row?.resourceType);
    const existing = byType.get(type);
    if (!existing) {
      byType.set(type, { ...row, resourceType: type });
      continue;
    }
    for (const field of fields) {
      const a = existing[field];
      const b = row[field];
      if (a == null && b == null) continue;
      existing[field] = String(BigInt(a ?? "0") + BigInt(b ?? "0"));
    }
  }
  return [...byType.values()];
}
