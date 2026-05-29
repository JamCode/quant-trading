import { apiGet, escapeHtml, fmtPct, pctClassNum } from "../api.js";
import { navigate } from "../router.js";

const main = () => document.getElementById("app-main");

const POLL_MS = 60_000;
let pollTimer = null;

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const n = Number(value);
  if (Number.isNaN(n)) {
    return "—";
  }
  return n.toFixed(digits);
}

function fmtAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const n = Number(value);
  if (Number.isNaN(n)) {
    return "—";
  }
  if (Math.abs(n) >= 1e8) {
    return `${(n / 1e8).toFixed(2)}亿`;
  }
  if (Math.abs(n) >= 1e4) {
    return `${(n / 1e4).toFixed(2)}万`;
  }
  return n.toFixed(0);
}

function regionLabel(region) {
  const map = { cn: "A 股", hk: "港股", global: "全球" };
  return map[region] || region || "—";
}

function displayPrice(row) {
  if (row.live && row.last_price != null) {
    return row.last_price;
  }
  return row.close_px;
}

function renderTable(data) {
  const items = data.items || [];
  let rows = "";
  items.forEach((r) => {
    const code = r.code || "";
    const live = Boolean(r.live);
    const priceLabel = live ? "现价" : "收盘";
    const dateCell = live
      ? `<span class="live-badge">盘中</span> ${escapeHtml((r.quote_time || "").slice(11, 16) || "—")}`
      : escapeHtml(r.trade_date || "—");
    rows += `<tr class="clickable${live ? " row-live" : ""}" data-code="${escapeHtml(code)}">
        <td><code>${escapeHtml(code)}</code></td>
        <td>${escapeHtml(r.name || "")}</td>
        <td class="muted">${escapeHtml(regionLabel(r.region))}</td>
        <td>${dateCell}</td>
        <td class="num" title="${escapeHtml(priceLabel)}">${fmtNum(displayPrice(r))}</td>
        <td class="num ${pctClassNum(r.change_pct)}">${fmtPct(r.change_pct)}</td>
        <td class="num">${fmtNum(r.change_amt)}</td>
        <td class="num">${fmtAmount(r.amount)}</td>
      </tr>`;
  });
  if (!rows) {
    rows =
      '<tr><td colspan="8">暂无指数数据，请确认 <code>market_index_intraday_cn</code> / <code>market_index_daily_*</code> 爬虫已运行</td></tr>';
  }

  const qt = data.quote_time ? ` · A 股盘中更新 ${escapeHtml(data.quote_time)}` : "";
  const td = data.trade_date ? ` · 日 K 数据日 ${escapeHtml(data.trade_date)}` : "";

  return `<p class="sub meta" id="indices-meta">共 ${items.length} 只指数${qt}${td} · 盘中行情来自 <code>market_index_intraday</code></p>
      <section class="panel table-scroll">
        <table class="data"><thead><tr>
          <th>代码</th><th>名称</th><th>市场</th><th>时间</th><th class="num">现价/收盘</th>
          <th class="num">涨跌幅</th><th class="num">涨跌额</th><th class="num">成交额</th>
        </tr></thead><tbody id="indices-tbody">${rows}</tbody></table>
      </section>
      <p class="meta">A 股交易时段约每分钟刷新 · 点击行查看走势</p>`;
}

function bindRowClicks(host) {
  host.querySelectorAll("tr[data-code]").forEach((row) => {
    row.addEventListener("click", () => {
      const code = row.getAttribute("data-code");
      navigate(`/indices/${encodeURIComponent(code)}`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
  });
}

async function loadIndices(host, { silent = false } = {}) {
  if (!silent) {
    host.innerHTML = '<p class="loading">加载中…</p>';
  }
  const data = await apiGet("/market-indices", { region: "all", live: "1" });
  const tableHtml = renderTable(data);
  if (silent && host.querySelector("#indices-tbody")) {
    const wrap = document.createElement("div");
    wrap.innerHTML = tableHtml;
    const newMeta = wrap.querySelector("#indices-meta");
    const newBody = wrap.querySelector("#indices-tbody");
    const meta = host.querySelector("#indices-meta");
    const body = host.querySelector("#indices-tbody");
    if (meta && newMeta) {
      meta.outerHTML = newMeta.outerHTML;
    }
    if (body && newBody) {
      body.innerHTML = newBody.innerHTML;
      bindRowClicks(host);
    }
    return;
  }
  host.innerHTML = tableHtml;
  bindRowClicks(host);
}

export function unmountIndices() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export async function mountIndices() {
  const host = main();
  unmountIndices();
  try {
    await loadIndices(host);
    pollTimer = setInterval(() => {
      loadIndices(host, { silent: true }).catch(() => {});
    }, POLL_MS);
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
