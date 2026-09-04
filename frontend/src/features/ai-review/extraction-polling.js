/**
 * Waiting for a background extraction to finish.
 *
 * The backend used to do the OCR inside the request. It now answers 202 the moment the work
 * is queued, so the page no longer learns the outcome from the call it made -- it has to
 * watch the attachment's own status, which the backend already moves through
 * `uploaded -> processing -> ready | failed`. No new status is introduced here and none is
 * inferred: the file's own row is the single answer, exactly as it was before.
 *
 * Separated from the page so it can be tested without a DOM, a timer or a browser.
 */

/** The statuses that mean the work is over, whichever way it went. */
export const SETTLED = Object.freeze(["ready", "failed"]);

/** How long to keep asking, and how often. A local OCR run took ~35s cold, ~12s warm. */
export const DEFAULT_INTERVAL_MS = 2000;
export const DEFAULT_ATTEMPTS = 60;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Poll until this file stops processing, and report the status it settled on.
 *
 * Returns `"ready"`, `"failed"`, `"uploaded"`, or `"timeout"` when it never settled.
 *
 * `uploaded` is a real answer, not an error: it means nothing ever started -- the request
 * was refused for a permission reason, or the file was never claimed. Returning the status
 * rather than throwing lets the caller do the same thing in every case: refresh the list and
 * let the card say what happened. That is also why a rejected `startExtraction` does not
 * need to be told apart from a genuine failure by reading its message; a duplicate request
 * is answered 503 while the file really is `processing`, and polling resolves it correctly.
 */
export async function waitForExtraction({
  adapter,
  fileId,
  intervalMs = DEFAULT_INTERVAL_MS,
  attempts = DEFAULT_ATTEMPTS,
  wait = sleep,
} = {}) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    let files;
    try {
      files = await adapter.getFiles();
    } catch (error) {
      // A single failed poll is not a failed extraction -- the work continues on the
      // server. Keep asking; only running out of attempts is an answer.
      await wait(intervalMs);
      continue;
    }
    const file = (files ?? []).find((item) => item.fileId === fileId);
    if (!file) return "timeout";
    if (file.processingStatus !== "processing") return file.processingStatus;
    if (attempt < attempts - 1) await wait(intervalMs);
  }
  return "timeout";
}
