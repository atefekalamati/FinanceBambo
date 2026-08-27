import { ApiError } from "../../core/api/api-error.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { getTehranTodayIso } from "../../shared/dates/persian-date.js";
import { validatePriceVersion } from "../../features/prices/prices-validation.js";
import { getUnitDefinition, validateUnitConversion } from "../../features/prices/unit-conversions-validation.js";

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 300) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

export function createMockPricesAdapter(context, { initialState = "success", resourceProvider = null } = {}) {
  let priceSequence = 7;
  let importSequence = 1;
  let conversionSequence = 4;
  const importPreviews = new Map();
  const resources = [
    // Ids and titles match the resource catalogue in backend/devhost/seed.py, so the same
    // resource is the same resource across adapters. The prices themselves stay per-unit
    // and are already in a realistic range; only the identities were stale.
    { resourceId: "20000000-0000-4000-8000-000000000001", code: "MAT-REBAR", title: "میلگرد آجدار A3", baseUnit: "kg" },
    { resourceId: "20000000-0000-4000-8000-000000000005", code: "LAB-FORM", title: "اکیپ قالب‌بندی", baseUnit: "hour" },
    { resourceId: "20000000-0000-4000-8000-000000000007", code: "EQ-CRANE", title: "جرثقیل برجی", baseUnit: "hour" },
    { resourceId: "20000000-0000-4000-8000-000000000009", code: "GEN-PERMIT", title: "مجوز و عوارض شهرداری", baseUnit: null },
  ];

  function getActiveResources() {
    const provided = typeof resourceProvider === "function" ? resourceProvider() : null;
    return Array.isArray(provided) ? provided : resources;
  }
  let prices = initialState === "empty" ? [] : [
    { priceId: "50000000-0000-4000-8000-000000000001", sequence: 1, resourceId: resources[0].resourceId, scope: "organization", unitPriceIRR: "285000", currency: "IRR", effectiveFrom: "2026-07-01", createdAt: "2026-07-01T08:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
    { priceId: "50000000-0000-4000-8000-000000000002", sequence: 2, resourceId: resources[0].resourceId, scope: "project", unitPriceIRR: "302000", currency: "IRR", effectiveFrom: "2026-08-01", createdAt: "2026-08-01T08:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
    { priceId: "50000000-0000-4000-8000-000000000003", sequence: 3, resourceId: resources[1].resourceId, scope: "organization", unitPriceIRR: "1850000", currency: "IRR", effectiveFrom: "2026-07-15", createdAt: "2026-07-15T09:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
    { priceId: "50000000-0000-4000-8000-000000000004", sequence: 4, resourceId: resources[2].resourceId, scope: "organization", unitPriceIRR: "12500000", currency: "IRR", effectiveFrom: "2026-06-20", createdAt: "2026-06-20T10:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
    { priceId: "50000000-0000-4000-8000-000000000005", sequence: 5, resourceId: resources[2].resourceId, scope: "project", unitPriceIRR: "13200000", currency: "IRR", effectiveFrom: "2026-08-03", createdAt: "2026-08-03T10:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
    { priceId: "50000000-0000-4000-8000-000000000006", sequence: 6, resourceId: resources[0].resourceId, scope: "project", unitPriceIRR: "295000", currency: "IRR", effectiveFrom: "2026-07-15", createdAt: "2026-07-15T08:00:00Z", actorId: context.userId, actorName: "امیر طاهری" },
  ];
  let conversions = initialState === "empty" ? [] : [
    { conversionId: "55555555-5555-4555-8555-555555555551", organizationId: context.organizationId, projectId: null, sourceUnit: "ton", targetUnit: "kg", factor: "1000.000000", effectiveDate: "2026-01-01", createdBy: context.userId, createdByName: "امیر طاهری", createdAt: "2026-01-01T07:00:00Z" },
    { conversionId: "55555555-5555-4555-8555-555555555552", organizationId: context.organizationId, projectId: null, sourceUnit: "day", targetUnit: "hour", factor: "8.000000", effectiveDate: "2026-01-01", createdBy: context.userId, createdByName: "امیر طاهری", createdAt: "2026-01-01T07:05:00Z" },
    { conversionId: "55555555-5555-4555-8555-555555555553", organizationId: context.organizationId, projectId: context.projectId, sourceUnit: "day", targetUnit: "hour", factor: "10.000000", effectiveDate: "2026-07-01", createdBy: context.userId, createdByName: "امیر طاهری", createdAt: "2026-07-01T07:00:00Z" },
  ];

  function snapshot() {
    const asOfDate = getTehranTodayIso();
    const currentPrices = getActiveResources().map((resource) => {
      const versions = prices
        .filter((price) => price.resourceId === resource.resourceId && price.effectiveFrom <= asOfDate)
        .sort((left, right) => right.effectiveFrom.localeCompare(left.effectiveFrom) || right.sequence - left.sequence);
      const projectPrice = versions.find((price) => price.scope === "project");
      const organizationPrice = versions.find((price) => price.scope === "organization");
      const currentPrice = projectPrice ?? organizationPrice ?? null;
      const selectedScope = currentPrice?.scope ?? null;
      const trendVersions = selectedScope ? versions.filter((price) => price.scope === selectedScope).reverse() : [];
      const previousPrice = trendVersions.length > 1 ? trendVersions.at(-2) : null;
      const currentAmount = currentPrice ? BigInt(currentPrice.unitPriceIRR) : null;
      const previousAmount = previousPrice ? BigInt(previousPrice.unitPriceIRR) : null;
      const trendDirection = previousAmount === null ? "none" : currentAmount > previousAmount ? "up" : currentAmount < previousAmount ? "down" : "flat";
      let latestChangePercent = null;
      if (previousAmount !== null && previousAmount !== 0n) {
        const scale = 1_000_000n;
        const numerator = (currentAmount - previousAmount) * 100n * scale;
        const absolute = numerator < 0n ? -numerator : numerator;
        const rounded = (absolute + previousAmount / 2n) / previousAmount;
        const signed = numerator < 0n ? -rounded : rounded;
        const whole = signed / scale;
        const fraction = (signed < 0n ? -signed : signed) % scale;
        latestChangePercent = `${signed < 0n && whole === 0n ? "-" : ""}${whole}.${String(fraction).padStart(6, "0")}`;
      }
      const trend = {
        resourceId: resource.resourceId,
        currentPriceIrr: currentPrice?.unitPriceIRR ?? null,
        previousPriceIrr: previousPrice?.unitPriceIRR ?? null,
        latestChangePercent,
        trendDirection,
        scopeKind: selectedScope,
        trendPoints: trendVersions.map((price) => ({ effectiveFrom: price.effectiveFrom, unitPriceIrr: price.unitPriceIRR })),
      };
      return { resource: clone(resource), currentPrice: clone(currentPrice), organizationPrice: clone(organizationPrice ?? null), projectPrice: clone(projectPrice ?? null), trend };
    });
    const conversionGroups = new Map();
    conversions
      .filter((conversion) => conversion.effectiveDate <= asOfDate)
      .forEach((conversion) => {
        const key = `${conversion.sourceUnit}:${conversion.targetUnit}`;
        const group = conversionGroups.get(key) ?? [];
        group.push(conversion);
        conversionGroups.set(key, group);
      });
    const currentConversions = [...conversionGroups.values()].map((versions) => {
      const sorted = [...versions].sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate)
        || right.createdAt.localeCompare(left.createdAt)
        || right.conversionId.localeCompare(left.conversionId));
      const projectConversion = sorted.find((conversion) => conversion.projectId === context.projectId) ?? null;
      const organizationConversion = sorted.find((conversion) => conversion.projectId === null) ?? null;
      return {
        sourceUnit: sorted[0].sourceUnit,
        targetUnit: sorted[0].targetUnit,
        dimension: getUnitDefinition(sorted[0].sourceUnit)?.dimension ?? null,
        currentConversion: clone(projectConversion ?? organizationConversion),
        organizationConversion: clone(organizationConversion),
        projectConversion: clone(projectConversion),
      };
    });
    return {
      currentPrices,
      history: clone([...prices].sort((left, right) => right.effectiveFrom.localeCompare(left.effectiveFrom) || right.sequence - left.sequence)),
      currentConversions,
      conversionHistory: clone([...conversions].sort((left, right) => right.effectiveDate.localeCompare(left.effectiveDate)
        || right.createdAt.localeCompare(left.createdAt)
        || right.conversionId.localeCompare(left.conversionId))),
      asOfDate,
      scope: { organizationId: context.organizationId, projectId: context.projectId },
    };
  }

  async function getPrices() {
    await wait();
    if (initialState === "error") {
      throw new ApiError({ status: 503, code: "MOCK_PRICES_UNAVAILABLE", message: "دریافت قیمت‌های آزمایشی انجام نشد.", requestId: "mock-prices-001" });
    }
    return snapshot();
  }

  async function createPriceVersion(values) {
    await wait(420);
    const validation = validatePriceVersion(values);
    if (!validation.valid) {
      throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "اطلاعات قیمت معتبر نیست.", details: validation.errors });
    }
    if (!getActiveResources().some((resource) => resource.resourceId === validation.values.resourceId)) {
      throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "قلم مالی موردنظر پیدا نشد." });
    }
    const sequence = priceSequence++;
    const price = {
      priceId: `50000000-0000-4000-8000-${String(sequence).padStart(12, "0")}`,
      sequence,
      resourceId: validation.values.resourceId,
      scope: validation.values.scope,
      unitPriceIRR: validation.values.unitPriceIRR,
      currency: "IRR",
      effectiveFrom: validation.values.effectiveFrom,
      createdAt: new Date().toISOString(),
      actorId: context.userId,
      actorName: "امیر طاهری",
    };
    prices = [...prices, price];
    return snapshot();
  }

  async function previewPriceImport(file) {
    await wait(500);
    const fileName = String(file?.name ?? "").trim();
    if (!fileName) {
      throw new ApiError({ status: 422, code: "IMPORT_FILE_REQUIRED", message: "انتخاب فایل قیمت الزامی است." });
    }
    if (!/\.xlsx?$/i.test(fileName)) {
      throw new ApiError({ status: 422, code: "IMPORT_FILE_TYPE_INVALID", message: "فقط فایل اکسل با پسوند معتبر پذیرفته می‌شود." });
    }

    const previewId = `price-preview-${String(importSequence++).padStart(4, "0")}`;
    const rows = [
      { rowNumber: 2, resourceId: resources[3].resourceId, resourceCode: resources[3].code, resourceTitle: resources[3].title, unitPriceIRR: "480000000", currency: "IRR", effectiveFrom: "2026-08-08", scope: "organization", status: "valid", errors: [] },
      { rowNumber: 3, resourceId: resources[1].resourceId, resourceCode: resources[1].code, resourceTitle: resources[1].title, importedAmount: "197500", unitPriceIRR: "1975000", currency: "TOMAN", effectiveFrom: "2026-08-08", scope: "project", status: "valid", errors: [] },
    ];
    if (/invalid|error/i.test(fileName)) {
      rows.push({ rowNumber: 4, resourceId: null, resourceCode: "UNKNOWN", resourceTitle: "قلم ناشناخته", unitPriceIRR: "12.5", currency: "", effectiveFrom: "2026-02-30", scope: "unknown", status: "invalid", errors: ["کد قلم مالی پیدا نشد.", `قیمت باید عدد صحیح و مثبت به ${CURRENCY_LABELS.IRR} باشد.`, `واحد پول باید به‌صراحت ${CURRENCY_LABELS.IRR} یا ${CURRENCY_LABELS.TOMAN} باشد.`, "تاریخ اثر یا سطح قیمت معتبر نیست."] });
    }
    // The Backend refuses a file whose bytes it has already committed for this
    // project. A name carrying «تکراری» stands in for those bytes here, so the
    // duplicate wording is reachable without a real repeated upload.
    const duplicateFile = /duplicate|\u062a\u06a9\u0631\u0627\u0631\u06cc/i.test(fileName);

    const preview = {
      previewId,
      fileName,
      totalRows: rows.length,
      validRows: rows.filter((row) => row.status === "valid").length,
      invalidRows: rows.filter((row) => row.status === "invalid").length,
      canCommit: !duplicateFile && rows.every((row) => row.status === "valid"),
      duplicateFile,
      duplicateOfImportId: duplicateFile ? "b0000000-0000-4000-8000-000000000001" : null,
      duplicateCommittedAt: duplicateFile ? "2026-08-11T09:20:00Z" : null,
      rows,
      committed: false,
    };
    importPreviews.set(previewId, preview);
    return clone(preview);
  }

  async function commitPriceImport({ previewId }) {
    await wait(500);
    const preview = importPreviews.get(previewId);
    if (!preview) {
      throw new ApiError({ status: 404, code: "IMPORT_PREVIEW_NOT_FOUND", message: "پیش‌نمایش ورود قیمت پیدا نشد؛ فایل را دوباره بررسی کنید." });
    }
    if (!preview.canCommit) {
      throw new ApiError({ status: 422, code: "IMPORT_PREVIEW_INVALID", message: "تا رفع همه خطاهای ردیفی، ثبت نهایی امکان‌پذیر نیست." });
    }
    if (preview.committed) {
      throw new ApiError({ status: 409, code: "IMPORT_ALREADY_COMMITTED", message: "این پیش‌نمایش قبلاً ثبت نهایی شده است." });
    }
    const imported = preview.rows.map((row) => {
      const sequence = priceSequence++;
      return {
        priceId: `50000000-0000-4000-8000-${String(sequence).padStart(12, "0")}`,
        sequence,
        resourceId: row.resourceId,
        scope: row.scope,
        unitPriceIRR: row.unitPriceIRR,
        currency: "IRR",
        importedCurrency: row.currency,
        effectiveFrom: row.effectiveFrom,
        createdAt: new Date().toISOString(),
        actorId: context.userId,
        actorName: "امیر طاهری",
        source: "excel_import",
      };
    });
    prices = [...prices, ...imported];
    importPreviews.set(previewId, { ...preview, committed: true });
    return { workspace: snapshot(), importedCount: imported.length, previewId };
  }

  async function createUnitConversion(values) {
    await wait(420);
    const validation = validateUnitConversion(values);
    if (!validation.valid) {
      const code = validation.errors.dimension ? "UNIT_MISMATCH" : "VALIDATION_ERROR";
      throw new ApiError({ status: 422, code, message: validation.errors.dimension || "اطلاعات تبدیل واحد معتبر نیست.", details: validation.errors });
    }
    const conversionNumber = conversionSequence++;
    const conversion = {
      conversionId: `55555555-5555-4555-8555-${String(conversionNumber).padStart(12, "0")}`,
      organizationId: context.organizationId,
      projectId: validation.values.scope === "project" ? context.projectId : null,
      sourceUnit: validation.values.sourceUnit,
      targetUnit: validation.values.targetUnit,
      factor: validation.values.factor,
      effectiveDate: validation.values.effectiveDate,
      createdBy: context.userId,
      createdByName: "امیر طاهری",
      createdAt: new Date().toISOString(),
    };
    conversions = [...conversions, conversion];
    return snapshot();
  }

  return Object.freeze({ getPrices, createPriceVersion, previewPriceImport, commitPriceImport, createUnitConversion });
}
