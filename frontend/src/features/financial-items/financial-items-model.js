export const RESOURCE_TYPES = Object.freeze([
  { value: "material", label: "متریال" },
  { value: "labor", label: "نیروی انسانی" },
  { value: "equipment", label: "دستگاه و تجهیزات" },
  { value: "general_cost", label: "هزینه عمومی" },
]);

const RESOURCE_TYPE_MAP = new Map(RESOURCE_TYPES.map((type) => [type.value, type.label]));

export function getResourceTypeLabel(value) {
  return RESOURCE_TYPE_MAP.get(value) ?? value;
}

export function isResourceType(value) {
  return RESOURCE_TYPE_MAP.has(value);
}
