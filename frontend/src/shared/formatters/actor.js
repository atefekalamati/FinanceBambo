/* How a person is shown wherever Finance stores only their id.

   Finance records actors as bare UUIDs, because the people belong to the host. The API now
   carries a name beside each id -- `submittedBy` + `submittedByName`, `createdBy` +
   `createdByName`, and so on -- and it is filled only when the host's directory knows the
   id. So the name is the label when there is one, and the id remains the label when there
   is not.

   Falling back to the id rather than to «کاربر نامشخص» is deliberate. A reader who cannot
   be given a name can still copy an id, match it against another page, or hand it to whoever
   can resolve it; a placeholder destroys the one identifying fact the record actually holds.
   The one case that does get a word is a record with no actor at all, where there is nothing
   to fall back TO -- an unattended import has no importer, and saying so is the truth. */

export const NO_ACTOR = "ثبت نشده";

export function actorLabel(name, id, absent = NO_ACTOR) {
  if (typeof name === "string" && name.trim()) return name.trim();
  if (id === null || id === undefined || String(id).trim() === "") return absent;
  return String(id);
}
