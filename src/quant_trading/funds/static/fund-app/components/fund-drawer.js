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

function holdingsTable(rows, { maxRows = 80 } = {}) {
  if (!rows?.length) {
    return "";
  }
  const keys = Object.keys(rows[0]);
  const head = keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("");
  let body = "";
  rows.slice(0, maxRows).forEach((row) => {
    body += `<tr>${keys.map((k) => `<td>${escapeHtml(row[k] ?? "—")}</td>`).join("")}</tr>`;
  });
  const more =
    rows.length > maxRows
      ? `<p class="meta">仅展示前 ${maxRows} 条，共 ${rows.length} 条。</p>`
      : "";
  return `<div class="drawer-scroll"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
}

function holdingsHtml(ext, code) {
  const h = ext?.holdings;
  if (!h || typeof h !== "object") {
    return "";
  }

  let html = section(
    "持仓与配置",
    `<p class="meta">来源：雪球资产配置 + 东方财富季报披露（非实时盘口）。打开抽屉时按需拉取并缓存约 24 小时。
      <a href="#" class="fund-holdings-refresh" data-code="${escapeHtml(code)}">强制刷新持仓</a></p>`
  );

  if (h.warnings?.length) {
    html += `<ul class="meta">${h.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`;
  }

  if (h.asset_mix?.length) {
    html += `<h3 class="fund-holdings-sub">资产配置（雪球）</h3>${holdingsTable(h.asset_mix)}`;
  } else {
    html += '<p class="meta">暂无资产配置拆分。</p>';
  }

  html += '<h3 class="fund-holdings-sub">股票投资明细（季报）</h3>';
  if (h.stocks?.length) {
    const meta = h.stock_quarter
      ? `报告期 ${h.stock_quarter}${h.stock_year_used ? ` · 数据年 ${h.stock_year_used}` : ""}`
      : "";
    html += `<p class="meta">${escapeHtml(meta)}</p>${holdingsTable(h.stocks)}`;
  } else {
    html += '<p class="meta">暂无股票季报持仓（货币型、纯债、QDII 等可能不披露 A 股明细）。</p>';
  }

  html += '<h3 class="fund-holdings-sub">债券投资明细（季报）</h3>';
  if (h.bonds?.length) {
    const meta = h.bond_quarter
      ? `报告期 ${h.bond_quarter}${h.bond_year_used ? ` · 数据年 ${h.bond_year_used}` : ""}`
      : "";
    html += `<p class="meta">${escapeHtml(meta)}</p>${holdingsTable(h.bonds)}`;
  } else {
    html += '<p class="meta">暂无债券季报持仓。</p>';
  }

  return html;
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
  html += holdingsHtml(ext, fund.code || "");

  return html;
}

function bindHoldingsRefresh(code) {
  document.querySelector(".fund-holdings-refresh")?.addEventListener("click", async (event) => {
    event.preventDefault();
    const link = event.currentTarget;
    link.textContent = "刷新中…";
    link.style.pointerEvents = "none";
    try {
      await openFundDrawer({ code, refresh: true });
    } finally {
      link.style.pointerEvents = "";
    }
  });
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

export async function openFundDrawer({ code, refresh = false }) {
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
    const detail = await apiGet(`/funds/${encodeURIComponent(code)}`, refresh ? { refresh: 1 } : {});
    const fund = detail.fund || {};
    const ext = detail.extended || {};
    const title = fund.short_name ? `${fund.short_name}（${code}）` : `基金 ${code}`;
    document.getElementById("drawer-title").textContent = title;

    setDrawerBody(renderFundBody(fund, ext));
    bindHoldingsRefresh(code);
    const chart = await mountNavCompareSection(code, fund.short_name || code);
    chartDispose = chart.dispose;
  } catch (err) {
    setDrawerBody(errorBlock(err.message || "加载失败"));
  }
}
