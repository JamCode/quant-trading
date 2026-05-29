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
  host.innerHTML = `<p class="sub meta">按股票代码或名称（含海外标的）反查持有该股的基金 · 数据来自季报</p>
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

  if (!q) {
    return;
  }

  const results = host.querySelector("#holdings-search-results");
  try {
    const data = await apiGet("/fund-holdings/search", { q, limit: 100 });
    const items = data.items || [];
    if (!items.length) {
      results.innerHTML = `<p class="meta">未找到持有「${escapeHtml(q)}」的基金。
        可先打开相关基金详情触发持仓入库，或等待每周持仓同步任务。</p>`;
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
