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
import { mountIndexDetail } from "./views/index-detail.js";
import { mountIndices, unmountIndices } from "./views/indices.js";
import { mountStockDetail } from "./views/stock-detail.js";
import { mountStocks } from "./views/stocks.js";
import { mountHoldingsLookup } from "./views/holdings-lookup.js";
import { mountBacktest } from "./views/backtest.js";

const NAV = [
  { path: "/", label: "行业仪表盘", title: "行业仪表盘" },
  { path: "/sectors", label: "行业资金流向", title: "行业资金流向" },
  { path: "/indices", label: "指数行情", title: "指数行情" },
  { path: "/backtest", label: "策略回测", title: "策略回测" },
  { path: "/valuation", label: "宽基 PE", title: "宽基 PE" },
  { path: "/funds", label: "基金目录", title: "基金目录" },
  { path: "/holdings", label: "持仓反查", title: "持仓反查" },
  { path: "/crawler", label: "爬虫任务", title: "爬虫任务" },
  { path: "/stocks", label: "A 股行情", title: "A 股行情" },
  { path: "/advisor", label: "基金 AI 助手", title: "基金 AI 助手" },
];

function renderSidebar(activePath) {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) {
    return;
  }
  let html = '<div class="sidebar-brand">Quant Funds</div>';
  NAV.forEach((item) => {
    const active =
      activePath === item.path ||
      (item.path === "/stocks" && activePath.startsWith("/stocks/")) ||
      (item.path === "/indices" && activePath.startsWith("/indices/"))
        ? " active"
        : "";
    const muted = item.muted ? " nav-muted" : "";
    html += `<a href="#" class="${active}${muted}" data-nav data-path="${item.path}">${item.label}</a>`;
  });
  sidebar.innerHTML = html;
}

function setTitle(path) {
  let item = NAV.find((n) => n.path === path);
  if (!item && path.startsWith("/stocks/")) {
    item = NAV.find((n) => n.path === "/stocks");
  }
  if (!item && path.startsWith("/indices/")) {
    item = NAV.find((n) => n.path === "/indices");
  }
  item = item || NAV[0];
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
  unmountIndices();
  const normalized = path === "" ? "/" : path;
  renderSidebar(normalized);
  setTitle(normalized);
  const main = document.getElementById("app-main");
  if (normalized === "/") {
    await mountDashboard(query);
  } else if (normalized === "/sectors") {
    await mountSectors(query);
  } else if (normalized === "/indices") {
    await mountIndices(query);
  } else if (/^\/indices\/[^/]+$/.test(normalized)) {
    const indexCode = decodeURIComponent(normalized.split("/")[2]);
    await mountIndexDetail(indexCode, query);
    const el = document.getElementById("view-title");
    if (el) {
      el.textContent = `指数 ${indexCode}`;
    }
  } else if (normalized === "/valuation") {
    await mountValuation(query);
  } else if (normalized === "/funds") {
    await mountFunds(query);
  } else if (normalized === "/holdings") {
    await mountHoldingsLookup(query);
  } else if (normalized === "/stocks") {
    await mountStocks(query);
  } else if (/^\/stocks\/[0-9]{6}$/.test(normalized)) {
    const stockCode = normalized.split("/")[2];
    await mountStockDetail(stockCode, query);
    const el = document.getElementById("view-title");
    if (el) {
      el.textContent = `个股 ${stockCode}`;
    }
  } else if (normalized === "/advisor") {
    await mountAdvisor(query);
  } else if (normalized === "/crawler") {
    await mountCrawler(query);
  } else if (normalized === "/backtest") {
    await mountBacktest(query);
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
