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

/**
 * Follow the host's project, however it says so.
 *
 * Three ways, because the host has never had only one:
 *
 *   the event carrying a context   — the stated contract, and still the best:
 *                                    nothing is fetched and nothing can differ
 *   the event carrying nothing     — a host that only wants to say "it changed";
 *                                    `rediscover` goes and reads the new one
 *   the address, or another tab    — the dashboard's selector writes the project
 *                                    into the URL and into localStorage, and
 *                                    that is all it does
 *
 * `rediscover` is injected rather than imported so this file keeps knowing
 * nothing about the host's endpoints, and so a caller that does not want the
 * requests simply does not pass it.
 */
export function subscribeHostProjectContext(onChange, onError = () => {}, { rediscover = null } = {}) {
  let current = null;
  try {
    current = window.__BAMBO_FINANCE_CONTEXT__?.projectId ?? null;
  } catch {
    current = null;
  }

  function publish(raw) {
    const context = normalizeContext(raw);
    window.__BAMBO_FINANCE_CONTEXT__ = raw;
    current = context.projectId;
    onChange(context);
  }

  async function handleChange(event) {
    try {
      const raw = event?.detail?.context ?? event?.detail ?? null;
      if (raw) {
        publish(raw);
        return;
      }
      // Nothing was handed over. Ask the host what it is showing now.
      if (!rediscover) throw new Error("Context تازه از میزبان دریافت نشد.");
      publish(await rediscover());
    } catch (error) {
      onError(error);
    }
  }

  /** A project change nobody announced: the address, or a choice in another tab. */
  async function handleAmbientChange() {
    if (!rediscover) return;
    try {
      const next = await rediscover();
      // Only when it is genuinely a different project. The address is rewritten
      // for reasons that have nothing to do with us -- the module's own router
      // is one of them -- and rebuilding every adapter for that would throw away
      // a page the reader is still using.
      if (!next || next.projectId === current) return;
      publish(next);
    } catch (error) {
      onError(error);
    }
  }

  const storageChanged = (event) => {
    if (event?.key && event.key !== "bambo:project") return;
    handleAmbientChange();
  };

  window.addEventListener(HOST_PROJECT_CONTEXT_CHANGED_EVENT, handleChange);
  window.addEventListener("popstate", handleAmbientChange);
  window.addEventListener("storage", storageChanged);
  return () => {
    window.removeEventListener(HOST_PROJECT_CONTEXT_CHANGED_EVENT, handleChange);
    window.removeEventListener("popstate", handleAmbientChange);
    window.removeEventListener("storage", storageChanged);
  };
}

export { normalizeContext };
