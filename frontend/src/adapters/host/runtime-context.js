import { normalizeContext } from "./context-adapter.js";

/** Host is the default. Only the explicitly marked development page may use mocks. */
export function resolveRuntimeContext({ mode = "host", hostContext, createStandaloneContext } = {}) {
  if (mode !== "host" && mode !== "standalone") {
    throw new Error("حالت اجرای ماژول مالی معتبر نیست.");
  }
  // A supplied but invalid context must never fall back to demo data.
  if (hostContext !== undefined && hostContext !== null) {
    return { runtime: "host", context: normalizeContext(hostContext) };
  }
  if (mode === "standalone") {
    return { runtime: "standalone", context: createStandaloneContext() };
  }
  throw new Error("اطلاعات پروژه از سایت اصلی دریافت نشده است. پس از آماده‌شدن اطلاعات پروژه، صفحه را دوباره بارگذاری کنید.");
}
