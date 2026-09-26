import { RESOURCE_TYPES as KINDS, canonicalResourceType, resourceTypeLabel } from "../../shared/resource-types.js";

/* The form's own register: «متریال» is what the estimators call it on this page. */
const FORM_LABELS = Object.freeze({
  material: "متریال",
  work: "نیرو و تجهیزات",
  general_cost: "هزینه‌های عمومی پروژه",
});

export const RESOURCE_TYPES = Object.freeze(KINDS.map((value) => ({ value, label: FORM_LABELS[value] })));

export function getResourceTypeLabel(value) {
  return resourceTypeLabel(value, FORM_LABELS) ?? canonicalResourceType(value);
}

/* What may be CREATED. The old names are not offered: a stored one is read as `work`. */
export function isResourceType(value) {
  return KINDS.includes(value);
}
