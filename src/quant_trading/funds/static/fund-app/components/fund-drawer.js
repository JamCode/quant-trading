import {
  apiGet,
  escapeHtml,
  fetchAllFundNavHistory,
  fetchAllMarketIndexHistory,
} from "../api.js";
import { closeDrawer, openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";
import { navigate } from "../router.js";
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

const STOCK_HOLDING_COLS = ["股票代码", "股票名称", "占净值比例", "持仓市值", "持股数"];

function holdingsTable(rows, columns, { maxRows = 80 } = {}) {
  if (!rows?.length) {
    return "";
  }
  const keys = columns?.length ? columns.filter((k) => k in rows[0]) : Object.keys(rows[0]);
  if (!keys.length) {
    return "";
  }
  const head = keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("");
  let body = "";
  rows.slice(0, maxRows).forEach((row) => {
    body += "<tr>";
    keys.forEach((k) => {
      if (k === "股票代码") {
        body += `<td>${stockCodeCell(row[k])}</td>`;
      } else {
        body += `<td>${escapeHtml(row[k] ?? "—")}</td>`;
      }
    });
    body += "</tr>";
  });
  const more =
    rows.length > maxRows
      ? `<p class="meta">仅展示前 ${maxRows} 条，共 ${rows.length} 条。</p>`
      : "";
  return `<div class="drawer-scroll fund-holdings-table-wrap"><table class="data fund-holdings-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
}

function stockCodeCell(raw) {
  const code = String(raw ?? "").trim();
  if (!code) {
    return "—";
  }
  if (/^\d{6}$/.test(code)) {
    return `<a href="#" class="stock-code-link" data-code="${escapeHtml(code)}"><code>${escapeHtml(code)}</code></a>`;
  }
  return `<code>${escapeHtml(code)}</code>`;
}

function holdingsHtml(ext, code) {
  const h = ext?.holdings;
  const hasHoldings = h && typeof h === "object";

  let inner = `<p class="meta">季报披露持仓（非实时）。缓存约 24 小时。
      <a href="#" class="fund-holdings-refresh" data-code="${escapeHtml(code)}">强制刷新</a></p>`;

  if (!hasHoldings) {
    inner += '<p class="meta">尚未加载持仓，请点「强制刷新」或稍后重试。</p>';
    return section("重仓标的", inner);
  }

  if (h.warnings?.length) {
    inner += `<ul class="meta fund-holdings-warn">${h.warnings
      .map((w) => `<li>${escapeHtml(w)}</li>`)
      .join("")}</ul>`;
  }

  if (h.stocks?.length) {
    const meta = h.stock_quarter
      ? `报告期 ${h.stock_quarter}${h.stock_year_used ? ` · ${h.stock_year_used} 年` : ""} · 共 ${h.stocks.length} 只`
      : `共 ${h.stocks.length} 只`;
    inner += `<p class="meta fund-holdings-period">${escapeHtml(meta)}</p>`;
    inner += holdingsTable(h.stocks, STOCK_HOLDING_COLS);
  } else {
    inner +=
      '<p class="meta">本季未披露股票明细（货币/纯债等），见下方资产配置。</p>';
  }

  if (h.asset_mix?.length) {
    inner += `<h3 class="fund-holdings-sub">资产配置（雪球）</h3>${holdingsTable(h.asset_mix)}`;
  }

  if (h.bonds?.length) {
    const meta = h.bond_quarter
      ? `债券报告期 ${h.bond_quarter}${h.bond_year_used ? ` · ${h.bond_year_used} 年` : ""}`
      : "";
    inner += `<h3 class="fund-holdings-sub">债券持仓（季报）</h3>`;
    if (meta) {
      inner += `<p class="meta">${escapeHtml(meta)}</p>`;
    }
    inner += holdingsTable(h.bonds);
  }

  return section("重仓标的", inner);
}

function fmtAum(fund) {
  if (fund.aum_label) {
    return fund.aum_label;
  }
  if (fund.aum_yi != null && fund.aum_yi !== "") {
    const n = Number(fund.aum_yi);
    if (!Number.isNaN(n)) {
      return `${n.toFixed(2)}亿`;
    }
  }
  return "";
}

function renderFundBody(fund, ext) {
  const name = fund.short_name || fund.code;
  let html = `<p class="meta">${escapeHtml(fund.fund_type || "")} · ${escapeHtml(name)}</p>`;

  const aumText = fmtAum(fund) || ext?.basic?.["最新规模"] || "";

  html += section(
    "行情快照",
    `<dl class="fund-dl">
      ${dlRow("净值日期", fund.nav_date)}
      ${dlRow("单位净值", fund.nav_unit)}
      ${dlRow("累计净值", fund.nav_acc)}
      ${dlRow("日增长率", fund.daily_pct)}
      ${dlRow("最新规模", aumText)}
      ${dlRow("申购", fund.subscribe_status)}
      ${dlRow("赎回", fund.redeem_status)}
    </dl>`
  );

  html += holdingsHtml(ext, fund.code || "");

  html += section(
    "历史净值",
    `<p class="meta" id="fund-nav-load-meta">加载走势与沪深300对比…</p>
    <div id="fund-nav-chart-host"></div>`
  );

  html += basicHtml(ext);

  return html;
}

function bindStockCodeLinks() {
  document.querySelectorAll("#drawer-body .stock-code-link").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const sym = link.getAttribute("data-code");
      if (sym) {
        closeDrawer();
        navigate(`/stocks/${sym}`, { query: {} });
        window.dispatchEvent(new PopStateEvent("popstate"));
      }
    });
  });
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
    bindStockCodeLinks();
    bindHoldingsRefresh(code);
    const chart = await mountNavCompareSection(code, fund.short_name || code);
    chartDispose = chart.dispose;
  } catch (err) {
    setDrawerBody(errorBlock(err.message || "加载失败"));
  }
}
