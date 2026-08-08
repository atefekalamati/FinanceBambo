export function createHashRouter({ routes, defaultPath, onNavigate }) {
  function currentPath() {
    const value = window.location.hash.replace(/^#/, "");
    return routes.some((route) => route.path === value && route.enabled) ? value : defaultPath;
  }

  function navigate() {
    const path = currentPath();
    if (window.location.hash !== `#${path}`) window.history.replaceState(null, "", `#${path}`);
    const route = routes.find((item) => item.path === path);
    onNavigate(route);
  }

  return Object.freeze({
    start() {
      window.addEventListener("hashchange", navigate);
      navigate();
    },
    stop() {
      window.removeEventListener("hashchange", navigate);
    },
  });
}
