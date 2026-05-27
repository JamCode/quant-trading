const cfg = window.__FUND_APP__ || { base: "", apiBase: "/api" };

export function appBase() {
  return cfg.base || "";
}

export function apiBase() {
  return cfg.apiBase || "/api";
}

export async function apiGet(path, params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v) !== "") {
      qs.set(k, String(v));
    }
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}${suffix}`;
  const response = await fetch(url);
  if (!response.ok) {
    const err = new Error(`${response.status} ${response.statusText}`);
    err.status = response.status;
    try {
      err.body = await response.json();
    } catch {
      /* ignore */
    }
    throw err;
  }
  return response.json();
}

export function fmtYi(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  let n = Number(value);
  if (Number.isNaN(n)) {
    return "—";
  }
  // Legacy rows: 元 (>=1e6) or mistaken ÷1e4 (1e5–1e6 band)
  const av = Math.abs(n);
  if (av >= 1_000_000) {
    n = n / 1e8;
  } else if (av >= 100_000) {
    n = n / 1e4;
  }
  return n.toFixed(2);
}

export function fmtPct(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const s = String(value).trim();
  if (s.endsWith("%")) {
    return s;
  }
  const n = Number(value);
  if (Number.isNaN(n)) {
    return s || "—";
  }
  return `${n.toFixed(2)}%`;
}

export function pctClass(value) {
  const s = String(value ?? "").trim();
  if (s.startsWith("-") || s.startsWith("−")) {
    return "down";
  }
  const n = Number(s.replace("%", ""));
  if (Number.isNaN(n) || n === 0) {
    return "";
  }
  return n > 0 ? "up" : "down";
}

export function pctClassNum(value) {
  const n = Number(value);
  if (Number.isNaN(n) || n === 0) {
    return "";
  }
  return n > 0 ? "up" : "down";
}

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
