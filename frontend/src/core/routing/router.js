export function createHashRouter({ routes, defaultPath, onNavigate }) {
  function currentLocation() {
    const value = window.location.hash.replace(/^#/, "");
    const [path, queryString = ""] = value.split("?", 2);
    const validPath = routes.some((route) => route.path === path && route.enabled) ? path : defaultPath;
    return {
      path: validPath,
      query: new URLSearchParams(validPath === path ? queryString : ""),
    };
  }

  function navigate() {
    const { path, query } = currentLocation();
    if (!routes.some((route) => route.path === window.location.hash.replace(/^#/, "").split("?", 1)[0] && route.enabled)) {
      window.history.replaceState(null, "", `#${path}`);
    }
    const route = routes.find((item) => item.path === path);
    onNavigate(route, query);
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
