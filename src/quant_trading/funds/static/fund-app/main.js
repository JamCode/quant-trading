import { apiGet } from "./api.js";
import { closeDrawer } from "./components/drawer.js";
import { openFundDrawer } from "./components/fund-drawer.js";
import { openSectorDrawer } from "./components/sector-drawer.js";
import { currentPath, initRouter, setQuery } from "./router.js";
import { mountAdvisor } from "./views/advisor.js";
import { mountCrawler } from "./views/crawler.js";
import { mountDashboard } from "./views/dashboard.js";
import { mountFunds } from "./views/funds.js";
import { mountSectors } from "./views/sectors.js";
import { mountValuation } from "./views/valuation.js";

const NAV = [
  { path: "/", label: "行业仪表盘", title: "行业仪表盘" },
  { path: "/sectors", label: "行业资金流向", title: "行业资金流向" },
  { path: "/valuation", label: "宽基 PE", title: "宽基 PE" },
  { path: "/funds", label: "基金目录", title: "基金目录" },
  { path: "/advisor", label: "基金 AI 助手", title: "基金 AI 助手" },
  { path: "/crawler", label: "爬虫任务", title: "爬虫任务", muted: true },
];

function renderSidebar(activePath) {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) {
    return;
  }
  let html = '<div class="sidebar-brand">Quant Funds</div>';
  NAV.forEach((item) => {
    const active = activePath === item.path ? " active" : "";
    const muted = item.muted ? " nav-muted" : "";
    html += `<a href="#" class="${active}${muted}" data-nav data-path="${item.path}">${item.label}</a>`;
  });
  sidebar.innerHTML = html;
}

function setTitle(path) {
  const item = NAV.find((n) => n.path === path) || NAV[0];
  document.title = item.title;
  const el = document.getElementById("view-title");
  if (el) {
    el.textContent = item.title;
  }
}

function handleDrawerQuery(query) {
  if (query.drawer === "sector" && query.industry) {
    openSectorDrawer({
      industry: query.industry,
      period: query.period,
      trade_date: query.trade_date,
    });
    return;
  }
  if (query.drawer === "fund" && query.code) {
    openFundDrawer({ code: query.code });
    return;
  }
  closeDrawer();
}

async function onRoute({ path, query }) {
  const normalized = path === "" ? "/" : path;
  renderSidebar(normalized);
  setTitle(normalized);
  const main = document.getElementById("app-main");
  if (normalized === "/") {
    await mountDashboard(query);
  } else if (normalized === "/sectors") {
    await mountSectors(query);
  } else if (normalized === "/valuation") {
    await mountValuation(query);
  } else if (normalized === "/funds") {
    await mountFunds(query);
  } else if (normalized === "/advisor") {
    await mountAdvisor(query);
  } else if (normalized === "/crawler") {
    await mountCrawler(query);
  } else {
    main.innerHTML = '<p class="muted">页面未找到</p>';
  }
  handleDrawerQuery(query);
}

initRouter({ onRoute });

document.addEventListener("DOMContentLoaded", () => {
  apiGet("/sync/status")
    .then((s) => {
      const el = document.getElementById("sync-hint");
      if (!el) {
        return;
      }
      const job = s.last_job || {};
      el.textContent = `基金 ${s.funds_stored ?? "—"} 只 · 最近同步 ${job.finished_at || job.started_at || "—"}`;
    })
    .catch(() => {});
});

export { currentPath, setQuery };
