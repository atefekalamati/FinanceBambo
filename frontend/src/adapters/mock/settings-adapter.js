import { ApiError } from "../../core/api/api-error.js";
import { validateSettingsRevision } from "../../features/settings/settings-validation.js";

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 320) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

export function createMockSettingsAdapter(context, { initialState = "success" } = {}) {
  // Mirrors FinanceSettingsResponse plus the trail GET /settings/revisions serves.
  let revisions = initialState === "empty" ? [] : [{
    revisionId: "10000000-0000-4000-8000-000000000001",
    revisionNumber: 1,
    previousValue: null,
    newValue: "4250.0000",
    effectiveDate: "2026-08-06",
    reason: "ثبت اولیه زیربنای کل پروژه",
    actorId: context.userId,
    actorName: null,
    occurredAt: "2026-08-06T09:15:00Z",
  }];
  let settings = initialState === "empty" ? null : {
    settingsId: "10000000-0000-4000-8000-000000000001",
    // FinanceSettingsResponse.canEdit: the Backend's verdict on this actor.
    canEdit: true,
    currency: "IRR",
    displayCurrency: "TOMAN",
    grossBuiltArea: "4250.0000",
    grossBuiltAreaUnit: "m2",
    revision: 1,
    effectiveFrom: "2026-08-06",
    reason: "ثبت اولیه زیربنای کل پروژه",
    createdBy: context.userId,
    createdAt: "2026-08-06T09:15:00Z",
  };

  async function getSettings() {
    await wait();
    if (initialState === "error") throw new ApiError({ status: 503, code: "MOCK_SETTINGS_UNAVAILABLE", message: "دریافت تنظیمات آزمایشی انجام نشد.", requestId: "mock-settings-001" });
    return settings ? clone({ ...settings, revisions }) : null;
  }

  async function updateGrossBuiltArea({ grossBuiltArea, reason, effectiveDate, expectedRevision }) {
    await wait(420);
    const validation = validateSettingsRevision({ grossBuiltArea, reason, effectiveDate });
    if (!validation.valid) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "اطلاعات Revision معتبر نیست.", details: validation.errors });
    if (settings && expectedRevision !== settings.revision) {
      throw new ApiError({ status: 409, code: "STALE_VERSION", message: "تنظیمات توسط کاربر دیگری تغییر کرده است. صفحه را دوباره بارگذاری کنید." });
    }

    const nextRevision = (settings?.revision ?? 0) + 1;
    revisions = [{
      revisionId: `10000000-0000-4000-8000-${String(nextRevision).padStart(12, "0")}`,
      revisionNumber: nextRevision,
      previousValue: settings?.grossBuiltArea ?? null,
      newValue: validation.values.grossBuiltArea,
      effectiveDate: validation.values.effectiveDate,
      reason: validation.values.reason,
      actorId: context.userId,
      actorName: null,
      occurredAt: new Date().toISOString(),
    }, ...revisions];
    settings = {
      settingsId: `10000000-0000-4000-8000-${String(nextRevision).padStart(12, "0")}`,
      currency: "IRR",
      displayCurrency: "TOMAN",
      grossBuiltArea: validation.values.grossBuiltArea,
      grossBuiltAreaUnit: "m2",
      revision: nextRevision,
      effectiveFrom: validation.values.effectiveDate,
      reason: validation.values.reason,
      createdBy: context.userId,
      createdAt: new Date().toISOString(),
    };
    return clone({ ...settings, revisions });
  }

  return Object.freeze({ getSettings, updateGrossBuiltArea });
}
