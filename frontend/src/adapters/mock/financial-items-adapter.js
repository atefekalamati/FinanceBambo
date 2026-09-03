import { ApiError } from "../../core/api/api-error.js";
import { CURRENCY_LABELS } from "../../shared/constants/currency.js";
import { validateEstimateLine, validateEstimateRevision, validateResource } from "../../features/financial-items/financial-items-validation.js";
import { compareDecimalStrings } from "../../shared/validation/decimal-validation.js";

function clone(value) {
  return structuredClone(value);
}

function wait(duration = 300) {
  return new Promise((resolve) => setTimeout(resolve, duration));
}

export function createMockFinancialItemsAdapter(context, { initialState = "success" } = {}) {
  let resourceSequence = 5;
  let lineSequence = 6;
  let revisionSequence = 6;
  let activitySequence = 3;
  let importSequence = 1;
  const importPreviews = new Map();

  const activities = [
    { activityExternalId: "ACT-102", taskExternalId: "task-foundation", title: "اجرای فونداسیون", wbsCode: "1.2" },
    { activityExternalId: "ACT-201", taskExternalId: "task-floor1-slab", title: "سقف طبقه اول", wbsCode: "2.1" },
    { activityExternalId: "ACT-202", taskExternalId: "task-formwork", title: "قالب‌بندی", wbsCode: "2.2" },
    { activityExternalId: "ACT-002", taskExternalId: "task-permit", title: "مجوزهای پروژه", wbsCode: "0.2" },
  ];

  const unitRegistry = [
    { code: "kg", label: "کیلوگرم", dimension: "mass", dimensionLabel: "جرم", decimalPrecision: 4 },
    { code: "m", label: "متر", dimension: "length", dimensionLabel: "طول", decimalPrecision: 4 },
    { code: "m2", label: "متر مربع", dimension: "area", dimensionLabel: "مساحت", decimalPrecision: 4 },
    { code: "m3", label: "متر مکعب", dimension: "volume", dimensionLabel: "حجم", decimalPrecision: 4 },
    { code: "hour", label: "ساعت", dimension: "equipment_time", dimensionLabel: "زمان تجهیز", decimalPrecision: 4 },
    { code: "hour", label: "نفر-ساعت", dimension: "labor_time", dimensionLabel: "زمان کار", decimalPrecision: 4 },
  ];

  let resources = initialState === "empty" ? [] : [
    { resourceId: "20000000-0000-4000-8000-000000000001", type: "material", code: "MAT-REBAR", title: "میلگرد", baseUnit: "kg", dimension: "جرم", externalResourceId: "res-rebar", source: "progress_feed" },
    { resourceId: "20000000-0000-4000-8000-000000000002", type: "labor", code: "LAB-FORM", title: "اکیپ قالب‌بندی", baseUnit: "hour", dimension: "زمان کار", externalResourceId: "res-formwork-team", source: "progress_feed" },
    { resourceId: "20000000-0000-4000-8000-000000000003", type: "equipment", code: "EQ-CRANE", title: "جرثقیل", baseUnit: "hour", dimension: "زمان تجهیز", externalResourceId: "res-crane", source: "progress_feed" },
    { resourceId: "20000000-0000-4000-8000-000000000004", type: "general_cost", code: "GEN-PERMIT", title: "هزینه مجوز", baseUnit: null, dimension: null, externalResourceId: "res-permit", source: "manual_entry" },
  ];

  let estimateLines = initialState === "empty" ? [] : [
    { lineId: "30000000-0000-4000-8000-000000000001", activityExternalId: "ACT-102", taskExternalId: "task-foundation", activityTitle: "اجرای فونداسیون", wbsCode: "1.2", resourceId: resources[0].resourceId, originalQuantity: "10000.0000", revisedQuantity: "11250.0000", originalAmount: null, revisedAmount: null, source: "progress_feed" },
    { lineId: "30000000-0000-4000-8000-000000000002", activityExternalId: "ACT-201", taskExternalId: "task-floor1-slab", activityTitle: "سقف طبقه اول", wbsCode: "2.1", resourceId: resources[0].resourceId, originalQuantity: "8500.0000", revisedQuantity: "8500.0000", originalAmount: null, revisedAmount: null, source: "progress_feed" },
    { lineId: "30000000-0000-4000-8000-000000000003", activityExternalId: "ACT-202", taskExternalId: "task-formwork", activityTitle: "قالب‌بندی", wbsCode: "2.2", resourceId: resources[1].resourceId, originalQuantity: "900.0000", revisedQuantity: "980.0000", originalAmount: null, revisedAmount: null, source: "progress_feed" },
    { lineId: "30000000-0000-4000-8000-000000000004", activityExternalId: "ACT-201", taskExternalId: "task-floor1-slab", activityTitle: "سقف طبقه اول", wbsCode: "2.1", resourceId: resources[2].resourceId, originalQuantity: "160.0000", revisedQuantity: "160.0000", originalAmount: null, revisedAmount: null, source: "progress_feed" },
    { lineId: "30000000-0000-4000-8000-000000000005", activityExternalId: "ACT-002", taskExternalId: "task-permit", activityTitle: "مجوزهای پروژه", wbsCode: "0.2", resourceId: resources[3].resourceId, originalQuantity: null, revisedQuantity: null, originalAmount: "250000000", revisedAmount: "250000000", source: "manual_entry" },
  ];

  if (estimateLines.length) {
    estimateLines = estimateLines.map((line, index) => {
      const current = line.revisedQuantity ?? line.revisedAmount;
      const original = line.originalQuantity ?? line.originalAmount;
      const hasSeedRevision = compareDecimalStrings(current, original) !== 0;
      return {
        ...line,
        revision: hasSeedRevision ? 2 : 1,
        revisions: hasSeedRevision ? [{
          revisionId: `40000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
          previousValue: original,
          newValue: current,
          reason: index === 0 ? "اصلاح متره براساس نقشه اجرایی جدید" : "اصلاح مقدار براساس صورت‌جلسه کارگاهی",
          actorId: context.userId,
          actorName: "امیر طاهری",
          occurredAt: "2026-08-07T10:30:00Z",
          source: "manual_revision",
          isOverrun: compareDecimalStrings(current, original) > 0,
          revisionNumber: 2,
        }] : [],
      };
    });
  }

  function snapshot() {
    return {
      resources: clone(resources),
      estimateLines: clone(estimateLines),
      activities: clone(activities),
      unitRegistry: clone(unitRegistry),
      scope: { organizationId: context.organizationId, projectId: context.projectId },
    };
  }

  async function getWorkspace() {
    await wait();
    if (initialState === "error") {
      throw new ApiError({ status: 503, code: "MOCK_ITEMS_UNAVAILABLE", message: "دریافت اقلام و متره آزمایشی انجام نشد.", requestId: "mock-items-001" });
    }
    return snapshot();
  }

  function getResourceSnapshot() {
    return clone(resources);
  }

  async function createResource(values) {
    await wait(380);
    const validation = validateResource(values);
    if (!validation.valid) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "اطلاعات قلم مالی معتبر نیست.", details: validation.errors });
    if (resources.some((resource) => resource.code.toLocaleLowerCase("en-US") === validation.values.code.toLocaleLowerCase("en-US"))) {
      throw new ApiError({ status: 409, code: "RESOURCE_CODE_DUPLICATE", message: "کد قلم مالی قبلاً ثبت شده است." });
    }

    const resource = {
      resourceId: `20000000-0000-4000-8000-${String(resourceSequence++).padStart(12, "0")}`,
      ...validation.values,
      dimension: validation.values.baseUnit ? unitRegistry.find((unit) => unit.code === validation.values.baseUnit)?.dimension ?? null : null,
      externalResourceId: null,
      source: "manual_entry",
    };
    resources = [...resources, resource];
    return snapshot();
  }

  async function createActivity(values) {
    await wait(380);
    const title = String(values.title ?? "").trim();
    if (!title) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "عنوان فعالیت الزامی است." });
    const activity = {
      activityExternalId: `ACT-${String(activitySequence++).padStart(3, "0")}`,
      taskExternalId: values.parentTaskExternalId || `task-${Date.now()}`,
      title,
      wbsCode: values.wbsCode || null,
      status: "active",
    };
    activities.push(activity);
    return { created: clone(activity), workspace: snapshot() };
  }

  async function createEstimateLine(values) {
    await wait(380);
    // The unit-price rule depends on the resource type, so it is resolved first.
    const selectedResource = resources.find((item) => item.resourceId === String(values.resourceId ?? "").trim());
    const isGeneralCost = selectedResource?.type === "general_cost";
    const validation = validateEstimateLine(values, { isGeneralCost });
    if (!validation.valid) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "اطلاعات خط متره معتبر نیست.", details: validation.errors });
    const resource = selectedResource;
    const activity = activities.find((item) => item.activityExternalId === validation.values.activityExternalId);
    if (!resource || !activity) throw new ApiError({ status: 422, code: "REFERENCE_NOT_FOUND", message: "فعالیت یا قلم مالی انتخاب‌شده معتبر نیست." });

    const [amountInteger, amountFraction] = validation.values.originalQuantity.split(".");
    if (isGeneralCost && amountFraction !== undefined) {
      throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: `مبلغ IRR باید عدد صحیح ${CURRENCY_LABELS.IRR} باشد.` });
    }
    const amountValue = amountInteger;
    const line = {
      lineId: `30000000-0000-4000-8000-${String(lineSequence++).padStart(12, "0")}`,
      activityExternalId: activity.activityExternalId,
      taskExternalId: activity.taskExternalId,
      activityTitle: activity.title,
      wbsCode: activity.wbsCode,
      resourceId: resource.resourceId,
      originalQuantity: isGeneralCost ? null : validation.values.originalQuantity,
      revisedQuantity: isGeneralCost ? null : validation.values.originalQuantity,
      originalAmount: isGeneralCost ? amountValue : null,
      revisedAmount: isGeneralCost ? amountValue : null,
      originalUnitPriceIRR: isGeneralCost ? amountValue : validation.values.originalUnitPriceIRR,
      source: "manual_entry",
      revision: 1,
      revisions: [],
    };
    estimateLines = [...estimateLines, line];
    return snapshot();
  }

  async function previewEstimateImport(file) {
    await wait(500);
    const fileName = String(file?.name ?? "").trim();
    if (!fileName) {
      throw new ApiError({ status: 422, code: "IMPORT_FILE_REQUIRED", message: "انتخاب فایل برآورد الزامی است." });
    }
    if (!/\.xlsx?$/i.test(fileName)) {
      throw new ApiError({ status: 422, code: "IMPORT_FILE_TYPE_INVALID", message: "فقط فایل اکسل با پسوند معتبر پذیرفته می‌شود." });
    }

    const previewId = `estimate-preview-${String(importSequence++).padStart(4, "0")}`;
    const rows = [
      {
        rowNumber: 2,
        activityExternalId: activities[0].activityExternalId,
        activityTitle: activities[0].title,
        resourceId: resources[2]?.resourceId,
        resourceCode: resources[2]?.code,
        resourceTitle: resources[2]?.title,
        value: "24.0000",
        unit: resources[2]?.baseUnit,
        status: "valid",
        errors: [],
      },
      {
        rowNumber: 3,
        activityExternalId: activities[2].activityExternalId,
        activityTitle: activities[2].title,
        resourceId: resources[0]?.resourceId,
        resourceCode: resources[0]?.code,
        resourceTitle: resources[0]?.title,
        value: "1750.0000",
        unit: resources[0]?.baseUnit,
        status: "valid",
        errors: [],
      },
    ];

    if (/invalid|error/i.test(fileName)) {
      rows.push({
        rowNumber: 4,
        activityExternalId: "",
        activityTitle: "فعالیت نامعتبر",
        resourceId: null,
        resourceCode: "UNKNOWN",
        resourceTitle: "قلم ناشناخته",
        value: "-5",
        unit: null,
        status: "invalid",
        errors: ["شناسه فعالیت پیدا نشد.", "کد قلم مالی معتبر نیست.", "مقدار باید بزرگ‌تر از صفر باشد."],
      });
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
      duplicateOfImportId: duplicateFile ? "b0000000-0000-4000-8000-000000000002" : null,
      duplicateCommittedAt: duplicateFile ? "2026-08-09T14:05:00Z" : null,
      rows,
      committed: false,
    };
    importPreviews.set(previewId, preview);
    return clone(preview);
  }

  async function commitEstimateImport({ previewId }) {
    await wait(500);
    const preview = importPreviews.get(previewId);
    if (!preview) {
      throw new ApiError({ status: 404, code: "IMPORT_PREVIEW_NOT_FOUND", message: "پیش‌نمایش ورود برآورد پیدا نشد؛ فایل را دوباره بررسی کنید." });
    }
    if (!preview.canCommit) {
      throw new ApiError({ status: 422, code: "IMPORT_PREVIEW_INVALID", message: "تا رفع همه خطاهای ردیفی، ثبت نهایی امکان‌پذیر نیست." });
    }
    if (preview.committed) {
      throw new ApiError({ status: 409, code: "IMPORT_ALREADY_COMMITTED", message: "این پیش‌نمایش قبلاً ثبت نهایی شده است." });
    }

    const importedLines = preview.rows.map((row) => {
      const activity = activities.find((item) => item.activityExternalId === row.activityExternalId);
      return {
        lineId: `30000000-0000-4000-8000-${String(lineSequence++).padStart(12, "0")}`,
        activityExternalId: activity.activityExternalId,
        taskExternalId: activity.taskExternalId,
        activityTitle: activity.title,
        wbsCode: activity.wbsCode,
        resourceId: row.resourceId,
        originalQuantity: row.value,
        revisedQuantity: row.value,
        originalAmount: null,
        revisedAmount: null,
        source: "excel_import",
        revision: 1,
        revisions: [],
      };
    });
    estimateLines = [...estimateLines, ...importedLines];
    importPreviews.set(previewId, { ...preview, committed: true });
    return { workspace: snapshot(), importedCount: importedLines.length, previewId };
  }

  async function reviseEstimateLine({ lineId, revisedValue, reason, expectedRevision }) {
    await wait(420);
    const lineIndex = estimateLines.findIndex((line) => line.lineId === lineId);
    if (lineIndex < 0) throw new ApiError({ status: 404, code: "FINANCE_NOT_FOUND", message: "خط متره موردنظر پیدا نشد." });

    const line = estimateLines[lineIndex];
    const resource = resources.find((item) => item.resourceId === line.resourceId);
    const isGeneralCost = resource?.type === "general_cost";
    const validation = validateEstimateRevision({ revisedValue, reason }, { isGeneralCost });
    if (!validation.valid) throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: "اطلاعات Revision معتبر نیست.", details: validation.errors });
    if (expectedRevision !== line.revision) {
      throw new ApiError({ status: 409, code: "STALE_VERSION", message: "این خط توسط کاربر دیگری تغییر کرده است. اطلاعات را دوباره دریافت کنید." });
    }

    const [amountInteger, amountFraction] = validation.values.revisedValue.split(".");
    if (isGeneralCost && amountFraction !== undefined) {
      throw new ApiError({ status: 422, code: "VALIDATION_ERROR", message: `مبلغ IRR باید عدد صحیح ${CURRENCY_LABELS.IRR} باشد.` });
    }

    const previousValue = line.revisedQuantity ?? line.revisedAmount;
    const originalValue = line.originalQuantity ?? line.originalAmount;
    const nextValue = isGeneralCost ? amountInteger : validation.values.revisedValue;
    if (compareDecimalStrings(nextValue, previousValue) === 0) {
      throw new ApiError({ status: 422, code: "REVISION_NO_CHANGE", message: "مقدار جدید باید با مقدار اصلاح‌شده فعلی متفاوت باشد." });
    }
    const nextRevision = line.revision + 1;
    const revision = {
      revisionId: `40000000-0000-4000-8000-${String(revisionSequence++).padStart(12, "0")}`,
      previousValue,
      newValue: nextValue,
      reason: validation.values.reason,
      actorId: context.userId,
      actorName: "امیر طاهری",
      occurredAt: new Date().toISOString(),
      source: "manual_revision",
      isOverrun: compareDecimalStrings(nextValue, originalValue) > 0,
      revisionNumber: nextRevision,
    };
    const updated = {
      ...line,
      revisedQuantity: isGeneralCost ? null : nextValue,
      revisedAmount: isGeneralCost ? nextValue : null,
      revision: nextRevision,
      revisions: [revision, ...line.revisions],
    };
    estimateLines = estimateLines.map((item, index) => index === lineIndex ? updated : item);
    return snapshot();
  }

  return Object.freeze({ getWorkspace, getResourceSnapshot, createResource, createActivity, createEstimateLine, previewEstimateImport, commitEstimateImport, reviseEstimateLine });
}
