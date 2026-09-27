import { ApiError } from "./api-error.js";
import { responseError } from "./response-error.js";

/**
 * Fired once when the host answers 401.
 *
 * The session is the host's cookie -- confirmed by the host team on 2026-09-12:
 * no token, no Authorization header, nothing in storage for this module to read
 * or refresh. So a 401 is not a request that failed and could be tried again; it
 * is the end of the session, and the way back is the host's own login.
 *
 * Announced once per page life. Eight adapters can be in flight at once, and
 * eight identical notices would be eight notices, not one answer.
 */
export const SESSION_ENDED_EVENT = "finance:session-ended";
let sessionEndedAnnounced = false;

function announceSessionEnd(status) {
  if (status !== 401 || sessionEndedAnnounced) return;
  sessionEndedAnnounced = true;
  // Guarded because this module is also exercised outside a browser, where the
  // error contract is what is under test and there is nobody to tell. A client
  // that threw here would replace the ApiError its caller is waiting for.
  if (typeof window?.dispatchEvent !== "function") return;
  window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT));
}

function assertSameOrigin(url) {
  const resolved = new URL(url, window.location.origin);
  if (resolved.origin !== window.location.origin) {
    throw new ApiError({ code: "CROSS_ORIGIN_BLOCKED", message: "درخواست خارجی مرورگر برای ماژول مالی مجاز نیست." });
  }
  return resolved;
}

/**
 * How long one request may take before it is given up on.
 *
 * Without this, a request the service never answers -- a proxy holding the connection,
 * a database lock under `/overview` -- never rejected, `Promise.all` never settled, and
 * the report page stayed on «در حال بارگذاری» with no way to tell that from a slow day.
 * Ninety seconds is far past anything measured (the live report on terrace answers in
 * seconds) and far short of forever.
 */
export const DEFAULT_REQUEST_TIMEOUT_MS = 90_000;

/**
 * A fetch that REJECTED, as opposed to answered. Two kinds, told apart because they
 * need different people:
 *
 *   AbortError  -- the caller cancelled, or the timeout below fired. Passed through
 *                  untouched when it is the caller's own, so cancellation stays
 *                  cancellation and never becomes an error card.
 *   anything else -- the browser could not reach the service at all: a proxy that
 *                  drops the path, a refused connection, TLS, DNS, an extension. The
 *                  browser says `TypeError: Failed to fetch` and nothing more. That is
 *                  not an ApiError, and un-wrapped it reached the reader as «نمایش
 *                  اطلاعات انجام نشد» -- a display fault, not retryable -- for a request
 *                  that never left the machine. Named here for what it is.
 */
function transportError(error, timedOut) {
  if (timedOut) {
    return new ApiError({ status: 0, code: "REQUEST_TIMEOUT",
                          message: "سرویس مالی در زمان مجاز پاسخ نداد." });
  }
  if (error?.name === "AbortError") return error;
  return new ApiError({ status: 0, code: "NETWORK_UNREACHABLE",
                        message: "ارتباط با سرویس مالی برقرار نشد." });
}

async function fetchWithTimeout(fetchImpl, url, options, timeoutMs) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  // A caller's own signal still cancels; it is forwarded rather than replaced.
  options.signal?.addEventListener("abort", () => controller.abort(), { once: true });
  try {
    return await fetchImpl(url, { ...options, signal: controller.signal });
  } catch (error) {
    throw transportError(error, timedOut);
  } finally {
    clearTimeout(timer);
  }
}

export function createApiClient({ fetchImpl = window.fetch.bind(window),
                                  requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS } = {}) {
  async function request(path, options = {}) {
    const url = assertSameOrigin(path);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");

    const response = await fetchWithTimeout(fetchImpl, url, { ...options, headers, credentials: "same-origin" }, requestTimeoutMs);
    const payload = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      announceSessionEnd(response.status);
      throw responseError(response, payload, "دریافت اطلاعات مالی انجام نشد.");
    }
    return payload;
  }

  async function download(path, options = {}) {
    const url = assertSameOrigin(path);
    const headers = new Headers(options.headers);
    const response = await fetchWithTimeout(fetchImpl, url, { ...options, headers, credentials: "same-origin" }, requestTimeoutMs);

    if (!response.ok) {
      announceSessionEnd(response.status);
      const payload = await response.json().catch(() => null);
      throw responseError(response, payload, "دریافت فایل گزارش انجام نشد.");
    }

    return Object.freeze({
      blob: await response.blob(),
      fileName: response.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/i)?.[1] ?? "finance-report.csv",
    });
  }

  return Object.freeze({ request, download });
}
