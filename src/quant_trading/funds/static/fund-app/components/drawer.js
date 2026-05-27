import { currentQuery, setQuery } from "../router.js";

const root = () => document.getElementById("drawer-root");
const titleEl = () => document.getElementById("drawer-title");
const bodyEl = () => document.getElementById("drawer-body");

let onCloseCallback = null;

function bindCloseHandlers() {
  const el = root();
  if (!el || el.dataset.bound === "1") {
    return;
  }
  el.dataset.bound = "1";
  el.querySelectorAll("[data-drawer-close]").forEach((node) => {
    node.addEventListener("click", () => closeDrawer());
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
    }
  });
}

export function openDrawer({ title, html, onClose, wide = false }) {
  bindCloseHandlers();
  const el = root();
  if (!el) {
    return;
  }
  onCloseCallback = onClose || null;
  const panel = el.querySelector(".drawer-panel");
  if (panel) {
    panel.classList.toggle("drawer-wide", Boolean(wide));
  }
  titleEl().textContent = title || "";
  bodyEl().innerHTML = html || '<p class="loading">加载中…</p>';
  el.classList.remove("hidden");
  el.setAttribute("aria-hidden", "false");
}

export function setDrawerBody(html) {
  bodyEl().innerHTML = html;
}

export function setDrawerLoading() {
  bodyEl().innerHTML = '<p class="loading">加载中…</p>';
}

function clearDrawerQuery() {
  const q = { ...currentQuery() };
  delete q.drawer;
  delete q.industry;
  delete q.code;
  setQuery(q, { replace: true });
}

export function closeDrawer() {
  const el = root();
  if (!el) {
    return;
  }
  el.classList.add("hidden");
  el.setAttribute("aria-hidden", "true");
  bodyEl().innerHTML = "";
  clearDrawerQuery();
  if (onCloseCallback) {
    onCloseCallback();
    onCloseCallback = null;
  }
}
