import { ROUTES, SURFACE_REQUIREMENTS, homeRouteFor, SURFACES } from "../config/routes.js";

export function hasPermission(context, permissionCode) {
  return Boolean(context?.permissionCodes?.includes(permissionCode));
}

/**
 * Two questions, both answered from the host's codes.
 *
 * The route's own permission is what its first request needs — every page opens
 * with a GET, so this is a reading permission. The surface requirement is
 * whether this account belongs on that side of the module at all: امور مالی is
 * where numbers are authored, and an account that cannot author one has nothing
 * to do there.
 *
 * Neither is enforcement. The Backend checks again on every request, and would
 * refuse. This decides what to draw.
 */
export function canAccessRoute(context, route) {
  if (route.permission && !hasPermission(context, route.permission)) return false;
  return canAccessSurface(context, route.surface);
}

/**
 * Whether this account belongs on a surface at all — it does if it holds any one
 * of that surface's codes. See SURFACE_REQUIREMENTS for why any rather than all.
 */
export function canAccessSurface(context, surface) {
  const required = SURFACE_REQUIREMENTS[surface];
  return !required?.length || required.some((code) => hasPermission(context, code));
}

/**
 * Where an account lands when it arrives with no route of its own — the first
 * home it is allowed to open. A customer must never be dropped at the door of
 * امور مالی and told it is closed.
 */
export function defaultRouteFor(context) {
  const home = [SURFACES.OPERATIONS, SURFACES.REPORT]
    .map((surface) => homeRouteFor(surface))
    .find((route) => route && canAccessRoute(context, route));
  return home?.path ?? ROUTES.find((route) => route.enabled)?.path ?? "/finance";
}
