export function hasPermission(context, permissionCode) {
  return Boolean(context?.permissionCodes?.includes(permissionCode));
}

export function canAccessRoute(context, route) {
  return !route.permission || hasPermission(context, route.permission);
}
