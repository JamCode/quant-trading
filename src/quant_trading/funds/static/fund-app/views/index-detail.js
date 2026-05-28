import { apiGet, escapeHtml, fmtPct, pctClassNum } from "../api.js";
import { navigate } from "../router.js";

const main = () => document.getElementById("app-main");

let priceChart = null;

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

async function loadChartJs() {
  if (window.Chart) {
    return;
  }
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

function renderChart(points, name) {
  const canvas = document.getElementById("indexPriceChart");
  if (!canvas || !window.Chart) {
    return;
  }
  if (priceChart) {
    priceChart.destroy();
  }
  priceChart = new window.Chart(canvas, {
    type: "line",
    data: {
      labels: points.map((p) => p.trade_date),
      datasets: [
        {
          label: `${name} 收盘`,
          data: points.map((p) => p.close),
          borderColor: "#4da3ff",
          tension: 0.1,
          pointRadius: 0,
        },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
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
  ];
  return `<dl class="detail-dl">${fields
    .map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`)
    .join("")}</dl>`;
}

export async function mountIndexDetail(code) {
  const host = main();
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
      <section class="panel">
        <p class="meta" id="index-chart-meta">加载走势…</p>
        <div class="chart-wrap" style="height:320px"><canvas id="indexPriceChart"></canvas></div>
      </section>`;

    host.querySelector("#indices-back")?.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/indices");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    const metaEl = host.querySelector("#index-chart-meta");
    try {
      const hist = await apiGet(`/market-indices/${encodeURIComponent(code)}/history`, {
        limit: 250,
        order: "asc",
      });
      const items = (hist.items || []).filter((p) => p.close != null);
      if (metaEl) {
        metaEl.textContent =
          items.length > 0
            ? `共 ${hist.total ?? items.length} 个交易日 · 展示 ${items.length} 条`
            : "暂无历史收盘";
      }
      if (items.length) {
        await loadChartJs();
        renderChart(items, name);
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
      navigate("/indices", { query: {} });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
  }
}
