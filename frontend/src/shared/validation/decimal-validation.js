const DIGIT_MAP = Object.freeze({
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
  "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
  "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
  "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
});

export function normalizeDecimalInput(value) {
  return String(value ?? "")
    .trim()
    .replace(/[۰-۹٠-٩]/g, (digit) => DIGIT_MAP[digit])
    .replace(/[٬,\s]/g, "")
    .replace("٫", ".");
}

export function validatePositiveDecimal(value, { precision = 4, requiredMessage = "مقدار الزامی است.", invalidMessage = "مقدار باید عددی مثبت باشد." } = {}) {
  const input = normalizeDecimalInput(value);
  if (!input) return { valid: false, value: input, message: requiredMessage };

  const pattern = new RegExp(`^\\d+(?:\\.\\d{1,${precision}})?$`);
  if (!pattern.test(input)) return { valid: false, value: input, message: invalidMessage };

  const [integer, fraction] = input.split(".");
  const normalizedInteger = integer.replace(/^0+(?=\d)/, "");
  const normalized = `${normalizedInteger}${fraction ? `.${fraction}` : ""}`;
  if (!/[1-9]/.test(normalized)) return { valid: false, value: normalized, message: invalidMessage };

  return { valid: true, value: normalized, message: "" };
}

export function compareDecimalStrings(left, right) {
  function parts(value) {
    const normalized = normalizeDecimalInput(value);
    const [integer = "0", fraction = ""] = normalized.split(".");
    return {
      integer: integer.replace(/^0+(?=\d)/, "") || "0",
      fraction: fraction.replace(/0+$/, ""),
    };
  }

  const a = parts(left);
  const b = parts(right);
  if (a.integer.length !== b.integer.length) return a.integer.length > b.integer.length ? 1 : -1;
  if (a.integer !== b.integer) return a.integer > b.integer ? 1 : -1;

  const precision = Math.max(a.fraction.length, b.fraction.length);
  const aFraction = a.fraction.padEnd(precision, "0");
  const bFraction = b.fraction.padEnd(precision, "0");
  if (aFraction === bFraction) return 0;
  return aFraction > bFraction ? 1 : -1;
}
