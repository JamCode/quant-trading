import {
  apiGet,
  escapeHtml,
  fetchAllFundNavHistory,
  fetchAllMarketIndexHistory,
} from "../api.js";
import { openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";
import {
  HS300_CODE,
  mountFundNavCompareChart,
  navCompareChartShell,
  parseIndexPoints,
  parseNavPoints,
} from "./fund-nav-chart.js";

function dlRow(label, value) {
  const v = value === null || value === undefined || value === "" ? "—" : String(value);
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(v)}</dd>`;
}

function section(title, inner) {
  return `<section class="panel"><h2>${escapeHtml(title)}</h2>${inner}</section>`;
}

function errorBlock(msg) {
  return `<p class="banner-error">${escapeHtml(msg)}</p>`;
}

function basicHtml(ext) {
  const basic = ext?.basic;
  if (!basic || typeof basic !== "object" || !Object.keys(basic).length) {
    return "";
  }
  let rows = "";
  Object.entries(basic).forEach(([k, v]) => {
    if (v !== null && v !== undefined && String(v).trim() !== "") {
      rows += dlRow(k, v);
    }
  });
  if (!rows) {
    return "";
  }
  return section("基金档案", `<dl class="fund-dl">${rows}</dl>`);
}

function holdingsHtml(ext) {
  const stocks = ext?.holdings?.stocks;
  if (!stocks?.length) {
    return "";
  }
  const keys = Object.keys(stocks[0]).slice(0, 4);
  let head = keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("");
  let rows = "";
  stocks.slice(0, 15).forEach((row) => {
    rows += `<tr>${keys.map((k) => `<td>${escapeHtml(row[k] ?? "—")}</td>`).join("")}</tr>`;
  });
  const q = ext.holdings.stock_quarter ? `报告期 ${ext.holdings.stock_quarter}` : "";
  return section(
    "股票持仓（季报）",
    `<p class="meta">${escapeHtml(q)}</p>
    <div class="drawer-scroll"><table class="data"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`
  );
}

function renderFundBody(fund, ext) {
  const name = fund.short_name || fund.code;
  let html = `<p class="meta">${escapeHtml(fund.fund_type || "")} · ${escapeHtml(name)}</p>`;

  html += section(
    "行情快照",
    `<dl class="fund-dl">
      ${dlRow("净值日期", fund.nav_date)}
      ${dlRow("单位净值", fund.nav_unit)}
      ${dlRow("累计净值", fund.nav_acc)}
      ${dlRow("日增长率", fund.daily_pct)}
      ${dlRow("申购", fund.subscribe_status)}
      ${dlRow("赎回", fund.redeem_status)}
    </dl>`
  );

  html += section(
    "历史净值",
    `<p class="meta" id="fund-nav-load-meta">加载走势与沪深300对比…</p>
    <div id="fund-nav-chart-host"></div>`
  );

  html += basicHtml(ext);
  html += holdingsHtml(ext);

  return html;
}

async function mountNavCompareSection(code, fundLabel) {
  const host = document.getElementById("fund-nav-chart-host");
  const meta = document.getElementById("fund-nav-load-meta");
  if (!host) {
    return { dispose: () => {} };
  }

  try {
    const [navRes, idxRes] = await Promise.all([
      fetchAllFundNavHistory(code),
      fetchAllMarketIndexHistory(HS300_CODE),
    ]);
    const navAsc = parseNavPoints(navRes.items);
    const indexAsc = parseIndexPoints(idxRes.items);

    if (!navAsc.length) {
      host.innerHTML = '<p class="meta">暂无历史净值，请稍后重试或联系同步任务。</p>';
      if (meta) {
        meta.textContent = "共 0 条净值";
      }
      return { dispose: () => {} };
    }

    if (meta) {
      meta.textContent = `共 ${navRes.total} 条净值 · 沪深300 ${idxRes.total} 个交易日`;
    }
    host.innerHTML = navCompareChartShell();
    return mountFundNavCompareChart({
      host,
      navAsc,
      indexAsc,
      fundLabel,
    });
  } catch (err) {
    const msg = err.body?.detail || err.message || "加载失败";
    host.innerHTML = errorBlock(String(msg));
    if (meta) {
      meta.textContent = "";
    }
    return { dispose: () => {} };
  }
}

export async function openFundDrawer({ code }) {
  let chartDispose = null;

  openDrawer({
    title: `基金 ${code}`,
    html: "",
    wide: true,
    onClose: () => {
      chartDispose?.();
      chartDispose = null;
    },
  });
  setDrawerLoading();

  try {
    const detail = await apiGet(`/funds/${encodeURIComponent(code)}`);
    const fund = detail.fund || {};
    const ext = detail.extended || {};
    const title = fund.short_name ? `${fund.short_name}（${code}）` : `基金 ${code}`;
    document.getElementById("drawer-title").textContent = title;

    setDrawerBody(renderFundBody(fund, ext));
    const chart = await mountNavCompareSection(code, fund.short_name || code);
    chartDispose = chart.dispose;
  } catch (err) {
    setDrawerBody(errorBlock(err.message || "加载失败"));
  }
}
