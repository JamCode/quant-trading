import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
import { openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";

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
  html += `<table class="data"><thead><tr>
    <th>代码</th><th>名称</th><th class="num">涨跌幅</th><th class="num">流通市值(亿)</th>
  </tr></thead><tbody>`;
  if (!rows.length) {
    html += '<tr><td colspan="4">暂无成分股</td></tr>';
  } else {
    rows.forEach((r) => {
      html += `<tr>
        <td><code>${escapeHtml(r.code)}</code></td>
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
  } catch (err) {
    setDrawerBody(`<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`);
  }
}
