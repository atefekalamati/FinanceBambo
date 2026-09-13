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

export function createApiClient({ fetchImpl = window.fetch.bind(window) } = {}) {
  async function request(path, options = {}) {
    const url = assertSameOrigin(path);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");

    const response = await fetchImpl(url, { ...options, headers, credentials: "same-origin" });
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
    const response = await fetchImpl(url, { ...options, headers, credentials: "same-origin" });

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
