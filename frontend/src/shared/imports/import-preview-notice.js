import { formatSystemDateTime } from "../formatters/display.js";

/**
 * One wording for the import preview verdict, shared by the estimate and price
 * importers so the two cannot drift apart.
 *
 * The duplicate case earns its own branch because the Backend reports it twice
 * over: structurally, on `duplicateFile`, and as an issue row whose reason is
 * the machine string `duplicate_import_file`. That row carries no row number,
 * so it lands among the file-level errors and used to be printed verbatim —
 * the reader was told «فایل یا قالب معتبر نیست: file: duplicate_import_file».
 * The adapter drops the raw row now that this names it properly; the guard
 * here is what keeps it from reappearing if that ever changes.
 */
export const DUPLICATE_IMPORT_REASON = "duplicate_import_file";

export function isDuplicateImportIssue(issue) {
  return String(issue ?? "").includes(DUPLICATE_IMPORT_REASON);
}

export function describeImportPreview(preview, { readyText, invalidText } = {}) {
  if (preview?.canCommit) return { tone: "ready", text: readyText };

  if (preview?.duplicateFile) {
    const committedAt = preview.duplicateCommittedAt
      ? ` آخرین ثبت این فایل در ${formatSystemDateTime(preview.duplicateCommittedAt)} انجام شده است.`
      : "";
    return {
      tone: "duplicate",
      text: `این فایل قبلاً برای این پروژه ثبت شده است.${committedAt} برای ثبت تغییرات، فایل به‌روزشده را بارگذاری کنید.`,
    };
  }

  const fileErrors = (preview?.fileErrors ?? []).filter((issue) => !isDuplicateImportIssue(issue));
  if (fileErrors.length) return { tone: "invalid", text: `فایل یا قالب معتبر نیست: ${fileErrors.join(" · ")}` };

  return { tone: "invalid", text: invalidText };
}
