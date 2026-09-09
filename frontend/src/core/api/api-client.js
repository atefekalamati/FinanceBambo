import { ApiError } from "./api-error.js";
import { responseError } from "./response-error.js";

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
      throw responseError(response, payload, "دریافت اطلاعات مالی انجام نشد.");
    }
    return payload;
  }

  async function download(path, options = {}) {
    const url = assertSameOrigin(path);
    const headers = new Headers(options.headers);
    const response = await fetchImpl(url, { ...options, headers, credentials: "same-origin" });

    if (!response.ok) {
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
