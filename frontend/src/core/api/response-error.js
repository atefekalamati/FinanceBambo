import { ApiError } from "./api-error.js";

function nonEmptyString(...values) {
  return values.find((value) => typeof value === "string" && value.trim().length > 0);
}

/** Normalize the Finance envelope and the host's { code, messageFa } envelope. */
export function responseError(response, payload, fallbackMessage) {
  const nested = payload?.error;
  const error = nested && typeof nested === "object" && !Array.isArray(nested) ? nested : payload;
  return new ApiError({
    status: response.status,
    code: nonEmptyString(error?.code) ?? `HTTP_${response.status}`,
    message: nonEmptyString(error?.messageFa, error?.message) ?? fallbackMessage,
    requestId: nonEmptyString(
      error?.request_id, error?.requestId,
      payload?.request_id, payload?.requestId,
      response.headers.get("X-Request-ID"),
    ) ?? null,
    details: Array.isArray(error?.details) ? error.details : [],
  });
}
