import { appBase } from "./api.js";

function normalizePath(path) {
  if (!path || path === "") {
    return "/";
  }
  return path.startsWith("/") ? path : `/${path}`;
}

export function currentPath() {
  const base = appBase();
  let path = window.location.pathname;
  if (base && path.startsWith(base)) {
    path = path.slice(base.length) || "/";
  }
  return normalizePath(path);
}

export function currentQuery() {
  const params = Object.fromEntries(new URLSearchParams(window.location.search));
  return params;
}

export function buildUrl(path, query = {}) {
  const base = appBase();
  const fullPath = normalizePath(path);
  const urlPath = base ? `${base}${fullPath}` : fullPath;
  const qs = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v) !== "") {
      qs.set(k, String(v));
    }
  });
  const q = qs.toString();
  return q ? `${urlPath}?${q}` : urlPath;
}

export function navigate(path, { replace = false, query = null } = {}) {
  const q = query === null ? currentQuery() : query;
  const url = buildUrl(path, q);
  if (replace) {
    window.history.replaceState({ path, query: q }, "", url);
  } else {
    window.history.pushState({ path, query: q }, "", url);
  }
}

export function setQuery(patch, { replace = true } = {}) {
  const q = { ...currentQuery(), ...patch };
  Object.keys(q).forEach((k) => {
    if (q[k] === undefined || q[k] === null || q[k] === "") {
      delete q[k];
    }
  });
  const url = buildUrl(currentPath(), q);
  if (replace) {
    window.history.replaceState({ path: currentPath(), query: q }, "", url);
  } else {
    window.history.pushState({ path: currentPath(), query: q }, "", url);
  }
  return q;
}

export function initRouter({ onRoute }) {
  const run = () => {
    onRoute({ path: currentPath(), query: currentQuery() });
  };
  window.addEventListener("popstate", run);
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-nav]");
    if (!link) {
      return;
    }
    event.preventDefault();
    const path = link.getAttribute("data-path") || "/";
    navigate(path, { query: {} });
    run();
  });
  run();
}
