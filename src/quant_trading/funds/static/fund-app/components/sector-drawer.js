import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
import { navigate } from "../router.js";
import { closeDrawer, openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";

function renderSectorBody(data) {
  const summary = data.summary || {};
  const rows = data.constituents || [];
  let html = `<p class="meta">数据日 <strong>${escapeHtml(data.trade_date || "—")}</strong> · 区间 <strong>${escapeHtml(data.period)}</strong>`;
  if (data.data_source) {
    html += ` · 成分来源 ${escapeHtml(data.data_source)}`;
  }
  html += "</p>";
  if (data.fetch_error) {
    html += `<div class="banner-error">${escapeHtml(data.fetch_error)}</div>`;
  }
  if (summary && Object.keys(summary).length) {
    html += `<div class="stats">
      <span>净流入 <strong class="${pctClassNum(summary.net_amt)}">${fmtYi(summary.net_amt)}</strong> 亿</span>
      <span>涨跌 <strong>${escapeHtml(summary.change_pct || "—")}</strong></span>
      <span>流通市值 <strong>${fmtYi(summary.float_market_cap)}</strong> 亿</span>
    </div>`;
  }
  html += `<table class="data"><colgroup>
    <col style="width:16%" /><col style="width:38%" /><col style="width:18%" /><col style="width:28%" />
  </colgroup><thead><tr>
    <th>代码</th><th>名称</th><th class="num">涨跌幅</th><th class="num">流通市值(亿)</th>
  </tr></thead><tbody>`;
  if (!rows.length) {
    html += '<tr><td colspan="4">暂无成分股</td></tr>';
  } else {
    rows.forEach((r) => {
      html += `<tr>
        <td><a href="#" class="stock-code-link" data-code="${escapeHtml(r.code)}"><code>${escapeHtml(r.code)}</code></a></td>
        <td>${escapeHtml(r.name || "")}</td>
        <td class="num ${pctClassNum(r.change_pct)}">${fmtPct(r.change_pct)}</td>
        <td class="num">${fmtYi(r.float_market_cap)}</td>
      </tr>`;
    });
  }
  html += "</tbody></table>";
  return html;
}

export async function openSectorDrawer({ industry, period, trade_date }) {
  openDrawer({ title: industry, html: "" });
  setDrawerLoading();
  try {
    const data = await apiGet(`/sectors/${encodeURIComponent(industry)}`, {
      period,
      trade_date,
    });
    setDrawerBody(renderSectorBody(data));
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
  } catch (err) {
    setDrawerBody(`<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`);
  }
}
