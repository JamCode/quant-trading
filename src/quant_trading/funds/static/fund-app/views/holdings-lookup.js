import { apiGet, escapeHtml } from "../api.js";
import { openFundDrawer } from "../components/fund-drawer.js";
import { navigate, setQuery } from "../router.js";

const main = () => document.getElementById("app-main");

function fmtWeight(v) {
  if (v === null || v === undefined || v === "") {
    return "—";
  }
  const n = Number(v);
  if (Number.isNaN(n)) {
    return String(v);
  }
  return `${n.toFixed(2)}%`;
}

export async function mountHoldingsLookup(query) {
  const host = main();
  const q = (query.q || "").trim();
  host.innerHTML = `<p class="sub meta">按股票代码或名称（含海外标的）反查持有该股的基金 · 季报披露 · 库内约 <span id="holdings-index-count">—</span> 只基金有持仓索引（最近同步 <span id="holdings-index-sync">—</span>）</p>
    <form class="toolbar" id="holdings-search-form">
      <label class="holdings-search-label">
        <span>标的</span>
        <input type="search" name="q" value="${escapeHtml(q)}" placeholder="如 600519、英伟达、NVDA" autofocus />
      </label>
      <button type="submit">查询</button>
    </form>
    <div id="holdings-search-results"><p class="meta">${q ? "查询中…" : "输入名称或代码后查询"}</p></div>`;

  const form = host.querySelector("#holdings-search-form");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const fd = new FormData(form);
    const term = String(fd.get("q") || "").trim();
    setQuery({ q: term }, { replace: false });
    navigate("/holdings", { query: { q: term } });
    window.dispatchEvent(new PopStateEvent("popstate"));
  });

  apiGet("/fund-holdings/search", { q: "600519", limit: 1 })
    .then((data) => {
      const el = host.querySelector("#holdings-index-count");
      const syncEl = host.querySelector("#holdings-index-sync");
      if (el && data.funds_indexed != null) {
        el.textContent = String(data.funds_indexed);
      }
      if (syncEl && data.last_sync_at) {
        syncEl.textContent = data.last_sync_at;
      } else if (syncEl) {
        syncEl.textContent = "未知";
      }
    })
    .catch(() => {});

  if (!q) {
    return;
  }

  const results = host.querySelector("#holdings-search-results");
  try {
    const data = await apiGet("/fund-holdings/search", { q, limit: 100 });
    const items = data.items || [];
    if (!items.length) {
      const idx = data.funds_indexed != null ? `当前索引约 ${data.funds_indexed} 只基金。` : "";
      results.innerHTML = `<p class="meta">未找到持有「${escapeHtml(q)}」的基金。${idx}
        若应有结果，可能是上周同步未含海外代码，正在补全；也可先打开相关 QDII/主动基金详情触发入库。</p>`;
      return;
    }
    let rows = "";
    items.forEach((r) => {
      rows += `<tr class="clickable" data-fund-code="${escapeHtml(r.fund_code)}">
        <td><code>${escapeHtml(r.fund_code)}</code></td>
        <td>${escapeHtml(r.fund_name || "")}</td>
        <td class="meta">${escapeHtml(r.fund_type || "")}</td>
        <td><code>${escapeHtml(r.stock_code)}</code> ${escapeHtml(r.stock_name || "")}</td>
        <td class="num">${fmtWeight(r.weight_pct)}</td>
        <td class="meta">${escapeHtml(r.report_date || "")}</td>
      </tr>`;
    });
    const hint = data.report_date_hint
      ? `库内最新报告期参考：${escapeHtml(data.report_date_hint)} · `
      : "";
    results.innerHTML = `<p class="meta">${hint}共 ${data.total} 条（各基金取最近一季持仓）</p>
      <div class="table-wrap"><table class="data">
        <thead><tr>
          <th>基金代码</th><th>基金简称</th><th>类型</th><th>匹配标的</th>
          <th class="num">占净值</th><th>报告期</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
    results.querySelectorAll("tr[data-fund-code]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const code = tr.getAttribute("data-fund-code");
        if (code) {
          openFundDrawer({ code });
        }
      });
    });
  } catch (err) {
    const msg = err.body?.detail || err.message || "查询失败";
    results.innerHTML = `<div class="banner-error">${escapeHtml(String(msg))}</div>`;
  }
}
