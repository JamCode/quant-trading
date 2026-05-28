import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
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

function snapshotGrid(snap) {
  const fields = [
    ["现价", fmtNum(snap.price)],
    ["涨跌幅", fmtPct(snap.change_pct)],
    ["流通市值(亿)", fmtYi(snap.float_market_cap)],
    ["总市值(亿)", fmtYi(snap.total_market_cap)],
    ["换手%", fmtNum(snap.turnover_pct)],
    ["成交额(亿)", fmtYi(snap.amount)],
    ["PE", fmtNum(snap.pe_dynamic)],
    ["PB", fmtNum(snap.pb)],
    ["60日%", fmtPct(snap.change_60d_pct)],
    ["年初至今%", fmtPct(snap.change_ytd_pct)],
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

export async function mountStockDetail(code, query) {
  const host = main();
  if (chartHandle) {
    chartHandle.dispose();
    chartHandle = null;
  }
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const detail = await apiGet(`/stocks/${encodeURIComponent(code)}`, {
      trade_date: query.trade_date || "",
    });
    const snap = detail.snapshot || {};
    const name = snap.name || code;
    const td = detail.trade_date || snap.trade_date || "";

    const chips = (detail.industries || [])
      .map(
        (ind) =>
          `<button type="button" class="chip" data-industry="${escapeHtml(ind)}">${escapeHtml(ind)}</button>`
      )
      .join("");

    host.innerHTML = `<p class="sub"><a href="#" id="stocks-back">← A 股行情</a></p>
      <h2 class="view-heading">${escapeHtml(name)} <code>${escapeHtml(code)}</code></h2>
      <p class="meta">快照数据日 ${escapeHtml(td)}</p>
      ${snapshotGrid(snap)}
      ${chips ? `<p class="meta">所属行业</p><div class="chip-row">${chips}</div>` : ""}
      <section class="panel">
        <div class="toolbar">
          <strong>日 K</strong>
          <button type="button" id="stock-refresh-history">刷新历史</button>
        </div>
        <p class="meta" id="stock-chart-meta">加载 K 线…</p>
        <div id="stock-kline-host"></div>
      </section>`;

    host.querySelector("#stocks-back")?.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/stocks", { query: td ? { trade_date: td } : {} });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelectorAll(".chip[data-industry]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("/sectors", {
          query: { industry: btn.getAttribute("data-industry"), trade_date: td },
        });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });

    const klineHost = host.querySelector("#stock-kline-host");

    const loadHistory = async (refresh = false) => {
      const metaEl = host.querySelector("#stock-chart-meta");
      if (metaEl) {
        metaEl.textContent = "加载 K 线…";
      }
      if (chartHandle) {
        chartHandle.dispose();
        chartHandle = null;
      }
      try {
        const hist = await apiGet(`/stocks/${encodeURIComponent(code)}/price-history`, {
          limit: 500,
          order: "asc",
          refresh: refresh ? 1 : 0,
        });
        const items = normalizeHistoryItems(hist.items);
        if (metaEl) {
          const srcMap = {
            cache: "MySQL 缓存",
            sina: "新浪（ECS 可用）",
            eastmoney: "东财前复权",
            empty: "无数据",
          };
          let src = srcMap[hist.source] || hist.source || "";
          if (hist.warning) {
            src += ` · 刷新失败已用缓存`;
          }
          metaEl.textContent =
            items.length > 0
              ? `共 ${hist.total ?? items.length} 条 · 已加载 ${items.length} 条 · ${src}`
              : "暂无历史数据，可点「刷新历史」重试";
        }
        if (items.length && klineHost) {
          klineHost.innerHTML = klineChartShell("拖动滑块缩放 · 副图为成交额");
          chartHandle = await mountMarketKlineChart({
            host: klineHost,
            points: items,
            name: `${name} 日K`,
          });
        } else if (klineHost) {
          klineHost.innerHTML = '<p class="meta">暂无 K 线数据</p>';
        }
      } catch (err) {
        if (metaEl) {
          const detail = err.body?.detail;
          metaEl.textContent = `图表加载失败：${detail || err.message || "未知错误"}`;
        }
      }
    };

    host.querySelector("#stock-refresh-history")?.addEventListener("click", () => {
      loadHistory(true);
    });

    await loadHistory(false);
  } catch (err) {
    const msg = err.body?.detail || err.message || "加载失败";
    host.innerHTML = `<div class="banner-error">${escapeHtml(String(msg))}</div>
      <p><a href="#" id="stocks-back-err">← 返回列表</a></p>`;
    host.querySelector("#stocks-back-err")?.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/stocks", { query: {} });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
  }
}
