const MIB = 1024 * 1024;

export const FILE_RULES = Object.freeze({
  invoice_image: Object.freeze({
    maxSizeBytes: 10 * MIB,
    extensions: Object.freeze(["jpg", "jpeg", "png", "webp"]),
    mimeByExtension: Object.freeze({
      jpg: "image/jpeg",
      jpeg: "image/jpeg",
      png: "image/png",
      webp: "image/webp",
    }),
  }),
  invoice_voice: Object.freeze({
    maxSizeBytes: 25 * MIB,
    extensions: Object.freeze(["mp3", "m4a", "wav", "ogg"]),
    mimeByExtension: Object.freeze({
      mp3: "audio/mpeg",
      m4a: "audio/mp4",
      wav: "audio/wav",
      ogg: "audio/ogg",
    }),
  }),
});

function extensionOf(name) {
  const parts = String(name ?? "").toLocaleLowerCase("en-US").split(".");
  return parts.length > 1 ? parts.at(-1) : "";
}

export function validateInvoiceFile(file, logicalType) {
  const errors = {};
  const rule = FILE_RULES[logicalType];

  if (!rule) {
    errors.logicalType = "نوع ورودی باید تصویر یا صدای فاکتور باشد.";
    return { valid: false, errors };
  }

  if (!file || !String(file.name ?? "").trim()) {
    errors.file = "انتخاب فایل الزامی است.";
    return { valid: false, errors };
  }

  const extension = extensionOf(file.name);
  if (!rule.extensions.includes(extension)) {
    errors.extension = logicalType === "invoice_image"
      ? "فقط تصویر با قالب جی‌پگ، پی‌ان‌جی یا وب‌پی مجاز است."
      : "فقط صدا با قالب ام‌پی‌تری، ام‌فور‌ای، ویو یا اوجی‌جی مجاز است.";
  }

  if (Number(file.size) <= 0) errors.size = "فایل خالی قابل بارگذاری نیست.";
  if (Number(file.size) > rule.maxSizeBytes) {
    errors.size = logicalType === "invoice_image"
      ? "حجم تصویر نباید بیشتر از ۱۰ مگابایت باشد."
      : "حجم صدا نباید بیشتر از ۲۵ مگابایت باشد.";
  }

  const expectedMime = rule.mimeByExtension[extension];
  if (expectedMime && file.type !== expectedMime) {
    errors.mimeType = "قالب نام فایل و نوع محتوای اعلام‌شده با یکدیگر سازگار نیستند.";
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    values: { logicalType, extension, mimeType: expectedMime, sizeBytes: Number(file.size), originalName: String(file.name) },
  };
}
