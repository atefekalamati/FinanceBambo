import { ApiError } from "./api-error.js";

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
      const error = payload?.error ?? {};
      throw new ApiError({
        status: response.status,
        code: error.code,
        message: error.message || "دریافت اطلاعات مالی انجام نشد.",
        requestId: error.request_id ?? error.requestId ?? null,
        details: error.details ?? [],
      });
    }
    return payload;
  }

  return Object.freeze({ request });
}
