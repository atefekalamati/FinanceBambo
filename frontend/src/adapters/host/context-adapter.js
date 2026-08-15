const PROJECT_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

export const HOST_PROJECT_CONTEXT_CHANGED_EVENT = "bambo:project-context-changed";

function normalizeContext(raw) {
  const context = {
    userId: raw?.userId ?? raw?.user_id,
    organizationId: raw?.organizationId ?? raw?.organization_id,
    organizationName: raw?.organizationName ?? raw?.organization_name,
    projectId: raw?.projectId ?? raw?.project_id,
    projectName: raw?.projectName ?? raw?.project_name,
    projectCode: raw?.projectCode ?? raw?.project_code,
    grossBuiltArea: raw?.grossBuiltArea ?? raw?.gross_built_area ?? null,
    permissionCodes: raw?.permissionCodes ?? raw?.permission_codes ?? [],
    locale: raw?.locale ?? "fa-IR",
    timezone: raw?.timezone ?? "Asia/Tehran",
  };

  if (!context.organizationId || !PROJECT_ID_PATTERN.test(context.projectId ?? "")) {
    throw new Error("Context معتبر سازمان و پروژه از میزبان دریافت نشد.");
  }
  if (!Array.isArray(context.permissionCodes)) throw new Error("فهرست مجوزهای Context معتبر نیست.");
  return Object.freeze(context);
}

export function getHostContext() {
  if (!window.__BAMBO_FINANCE_CONTEXT__) return null;
  return normalizeContext(window.__BAMBO_FINANCE_CONTEXT__);
}

export function subscribeHostProjectContext(onChange, onError = () => {}) {
  function handleChange(event) {
    try {
      const raw = event.detail?.context ?? event.detail ?? window.__BAMBO_FINANCE_CONTEXT__;
      const context = normalizeContext(raw);
      window.__BAMBO_FINANCE_CONTEXT__ = raw;
      onChange(context);
    } catch (error) {
      onError(error);
    }
  }

  window.addEventListener(HOST_PROJECT_CONTEXT_CHANGED_EVENT, handleChange);
  return () => window.removeEventListener(HOST_PROJECT_CONTEXT_CHANGED_EVENT, handleChange);
}

export { normalizeContext };
