/**
 * Reading the module's context out of the host, rather than being handed it.
 *
 * The contract in HOST_PROJECT_CONTEXT_FA.md asks the host to set
 * `window.__BAMBO_FINANCE_CONTEXT__` before this module boots. Nothing in the
 * BAMBO dashboard does that, and nothing was ever asked to: the dashboard keeps
 * the chosen project in the address (`?project=`) with the last choice in
 * `localStorage['bambo:project']`, exactly as its own `ProjectScopeSelector`
 * resolves it, and everything else — who is signed in, which organization owns
 * the project, what this account may do — is behind three endpoints it already
 * serves.
 *
 * So this reads those instead. The handed-over context still wins where it
 * exists; this is what happens when it does not, and it turns "the module
 * cannot start" into "the module starts".
 *
 * Nothing here is authorization. The permission codes gathered below decide
 * what is worth drawing; every request is checked again by the finance service,
 * which is the answer that counts.
 */

/** The host's own keys. Named here because they are its, not ours. */
const HOST_PROJECT_STORAGE_KEY = "bambo:project";

/** A failure a reader can act on, rather than a stack trace. */
export class HostContextError extends Error {}

/**
 * Which project the host has in scope.
 *
 * The same precedence the dashboard's own selector uses: the address wins
 * because it is explicit and shareable, and the stored choice carries the scope
 * to a page that was opened without one. `building` is accepted too — the
 * dashboard still answers to it, and a link written years ago still works.
 */
export function readHostProjectId({ search, storage } = {}) {
  const query = new URLSearchParams(search ?? globalThis.location?.search ?? "");
  const fromUrl = (query.get("project") || query.get("building") || "").trim();
  if (fromUrl) return fromUrl;
  try {
    const store = storage ?? globalThis.localStorage;
    return (store?.getItem(HOST_PROJECT_STORAGE_KEY) || "").trim();
  } catch {
    // A browser refusing storage is not a reason to fail; it only means there
    // is no remembered choice.
    return "";
  }
}

/** One host call, with its failures turned into something worth reading. */
async function hostJson(fetchImpl, path, { optional = false, notFound = null } = {}) {
  let response;
  try {
    response = await fetchImpl(path, { credentials: "same-origin", headers: { Accept: "application/json" } });
  } catch {
    throw new HostContextError("ارتباط با سایت اصلی برقرار نشد. اتصال خود را بررسی کنید و صفحه را دوباره باز کنید.");
  }
  if (response.status === 401 || response.status === 403) {
    throw new HostContextError("نشست شما در سایت اصلی معتبر نیست. دوباره وارد شوید و این صفحه را باز کنید.");
  }
  // A project that is simply not there is worth saying plainly; a reader can act
  // on it by choosing another one, which a status code does not tell them.
  if (response.status === 404 && notFound) throw new HostContextError(notFound);
  if (!response.ok) {
    if (optional) return null;
    throw new HostContextError(`اطلاعات پروژه از سایت اصلی دریافت نشد (کد ${response.status}).`);
  }
  return response.json().catch(() => null);
}

/**
 * The codes this account holds, and only those.
 *
 * The dashboard's own gates read `isBamboAdmin || permissions.includes(code)`,
 * and it is tempting to copy that here. It would be wrong. The finance service
 * has no administrator bypass: `CoreRbacPermissionAuthorizer` re-reads
 * `user_roles → role_permissions` on every request and refuses a code the row
 * does not grant, whatever the caller is called elsewhere.
 *
 * So honouring the flag here would draw buttons whose only possible answer is
 * 403 — the exact thing `capabilities.js` exists to prevent. If BAMBO
 * administrators are meant to have finance access, the admin role has to be
 * granted the finance codes in Core, the same seed decision
 * `finance_report.issue` is already waiting on.
 */
function financeCodesFor({ permissions }) {
  return [...new Set(Array.isArray(permissions) ? permissions : [])];
}

/**
 * Assemble the context from what the host already knows.
 *
 * Returns the same shape `context-adapter.js` normalizes, or throws a
 * `HostContextError` saying which part of the host could not answer. It never
 * returns a partial context: a project without an organization, or without the
 * codes that decide what to draw, would render a page that quietly lies about
 * what this account can see.
 */
export async function discoverHostContext({
  fetchImpl = globalThis.fetch?.bind(globalThis),
  projectId = readHostProjectId(),
  base = "/api",
} = {}) {
  if (typeof fetchImpl !== "function") return null;
  if (!projectId) {
    throw new HostContextError("پروژه‌ای انتخاب نشده است. از نوار بالای سایت یک پروژه انتخاب کنید.");
  }

  // Asked together: they do not depend on each other, and the slowest decides.
  const [me, projectPayload, rbac] = await Promise.all([
    hostJson(fetchImpl, `${base}/me`),
    hostJson(fetchImpl, `${base}/projects/${encodeURIComponent(projectId)}`,
      { notFound: "پروژه انتخاب‌شده در سایت اصلی پیدا نشد. پروژهٔ دیگری انتخاب کنید." }),
    hostJson(fetchImpl, `${base}/rbac/my-permissions`, { optional: true }),
  ]);

  // The dashboard wraps it; a bare object is accepted too, so a change of shape
  // on one side does not take the module down with it.
  const project = projectPayload?.project ?? projectPayload ?? null;
  if (!project) {
    throw new HostContextError("پروژه انتخاب‌شده در سایت اصلی پیدا نشد. پروژهٔ دیگری انتخاب کنید.");
  }

  const organizationId = project.organizationId ?? me?.orgs?.[0]?.id ?? null;
  if (!organizationId) {
    throw new HostContextError("سازمان این پروژه از سایت اصلی دریافت نشد.");
  }

  return {
    userId: me?.user?.id ?? null,
    organizationId,
    organizationName: me?.orgs?.[0]?.name ?? null,
    projectId: project.id ?? projectId,
    projectName: project.name ?? null,
    projectCode: project.code ?? null,
    /* The host holds this on the project itself and shows it as a dashboard
       figure. Read rather than asked for again, so the per-square-metre costs
       here and the area on the dashboard cannot drift apart. It stays optional:
       a project with none on file gets null, never an invented number. */
    grossBuiltArea: project.builtAreaSqm ?? null,
    permissionCodes: financeCodesFor({ permissions: rbac?.permissions }),
    locale: "fa-IR",
    timezone: "Asia/Tehran",
  };
}
