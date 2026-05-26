import { apiGet, escapeHtml } from "../api.js";
import { openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";

function renderFundBody(data) {
  const fund = data.fund || {};
  const ext = data.extended || {};
  return `<div class="stats">
    <span>代码 <code>${escapeHtml(fund.code)}</code></span>
    <span>类型 ${escapeHtml(fund.fund_type || "—")}</span>
    <span>净值 ${escapeHtml(fund.nav_unit || "—")}</span>
    <span>日涨跌 ${escapeHtml(fund.daily_pct || "—")}</span>
  </div>
  <p class="meta">${escapeHtml(ext.manager || ext.fund_manager || "—")}</p>
  <p class="muted">完整图表与排名见 Phase 2 基金目录增强。</p>`;
}

export async function openFundDrawer({ code }) {
  openDrawer({ title: `基金 ${code}`, html: "" });
  setDrawerLoading();
  try {
    const data = await apiGet(`/funds/${encodeURIComponent(code)}`);
    setDrawerBody(renderFundBody(data));
  } catch (err) {
    setDrawerBody(`<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`);
  }
}
