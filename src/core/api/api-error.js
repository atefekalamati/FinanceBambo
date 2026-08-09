export class ApiError extends Error {
  constructor({ status = 0, code = "UNKNOWN_ERROR", message = "خطای پیش‌بینی‌نشده", requestId = null, details = [] } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}
