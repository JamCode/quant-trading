import { apiGet, escapeHtml, fmtPct, pctClassNum } from "../api.js";
import { navigate } from "../router.js";
import { klineChartShell, mountMarketKlineChart } from "../components/market-kline-chart.js";

const main = () => document.getElementById("app-main");

let chartHandle = null;

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

function snapshotGrid(snap) {
  const fields = [
    ["收盘", fmtNum(snap.close_px)],
    ["涨跌幅", fmtPct(snap.change_pct)],
    ["开盘", fmtNum(snap.open_px)],
    ["最高", fmtNum(snap.high_px)],
    ["最低", fmtNum(snap.low_px)],
    ["昨收", fmtNum(snap.prev_close)],
    ["涨跌额", fmtNum(snap.change_amt)],
    ["成交额", fmtAmount(snap.amount)],
  ];
  return `<dl class="detail-dl">${fields
    .map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`)
    .join("")}</dl>`;
}

function normalizeHistoryItems(items) {
  return (items || [])
    .filter((p) => p.close != null)
    .map((p) => ({
      trade_date: p.trade_date,
      open: p.open ?? p.close,
      high: p.high ?? p.close,
      low: p.low ?? p.close,
      close: p.close,
      change_pct: p.change_pct,
      volume: p.volume,
      amount: p.amount,
    }));
}

export async function mountIndexDetail(code) {
  const host = main();
  if (chartHandle) {
    chartHandle.dispose();
    chartHandle = null;
  }
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const detail = await apiGet(`/market-indices/${encodeURIComponent(code)}`);
    const snap = detail.snapshot || {};
    const name = snap.name || code;
    const td = detail.trade_date || snap.trade_date || "";

    host.innerHTML = `<p class="sub"><a href="#" id="indices-back">← 指数行情</a></p>
      <h2 class="view-heading">${escapeHtml(name)} <code>${escapeHtml(code)}</code></h2>
      <p class="meta">快照数据日 ${escapeHtml(td)}</p>
      ${snapshotGrid(snap)}
      <section class="panel" id="index-kline-panel">
        <p class="meta" id="index-chart-meta">加载走势…</p>
        <div id="index-kline-host"></div>
      </section>`;

    host.querySelector("#indices-back")?.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/indices");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    const metaEl = host.querySelector("#index-chart-meta");
    const klineHost = host.querySelector("#index-kline-host");
    try {
      const hist = await apiGet(`/market-indices/${encodeURIComponent(code)}/history`, {
        limit: 500,
        order: "asc",
      });
      const items = normalizeHistoryItems(hist.items);
      if (metaEl) {
        metaEl.textContent =
          items.length > 0
            ? `共 ${hist.total ?? items.length} 个交易日 · 已加载 ${items.length} 条`
            : "暂无历史行情";
      }
      if (items.length && klineHost) {
        klineHost.innerHTML = klineChartShell("点上方区间切换范围 · 副图为成交额（无则显示成交量）");
        chartHandle = await mountMarketKlineChart({
          host: klineHost,
          points: items,
          name,
        });
      } else if (klineHost) {
        klineHost.innerHTML = '<p class="meta">暂无 K 线数据</p>';
      }
    } catch (err) {
      if (metaEl) {
        metaEl.textContent = `走势加载失败：${err.message || "未知错误"}`;
      }
    }
  } catch (err) {
    const msg = err.body?.detail || err.message || "加载失败";
    host.innerHTML = `<div class="banner-error">${escapeHtml(String(msg))}</div>
      <p><a href="#" id="indices-back-err">← 返回列表</a></p>`;
    host.querySelector("#indices-back-err")?.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/indices");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
  }
}
