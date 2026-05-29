import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
import { navigate } from "../router.js";
import { loadEcharts } from "./market-kline-chart.js";
import { closeDrawer, openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";

function renderFlowHistory(host, points) {
  if (!host || !points?.length) {
    return () => {};
  }
  let chart = null;
  loadEcharts()
    .then((echarts) => {
      chart = echarts.init(host, null, { renderer: "canvas" });
      const dates = points.map((p) => String(p.trade_date || "").slice(0, 10));
      const values = points.map((p) => Number(p.net_amt ?? 0));
      chart.setOption({
        animation: false,
        grid: { left: 48, right: 12, top: 16, bottom: 28 },
        tooltip: {
          trigger: "axis",
          formatter(items) {
            const it = items?.[0];
            if (!it) {
              return "";
            }
            const v = Number(it.value);
            const sign = v > 0 ? "+" : "";
            return `${it.name}<br/>净流入 ${sign}${v.toFixed(2)} 亿`;
          },
        },
        xAxis: {
          type: "category",
          data: dates,
          axisLabel: { fontSize: 10, rotate: dates.length > 8 ? 35 : 0 },
        },
        yAxis: {
          type: "value",
          name: "亿",
          axisLabel: { fontSize: 10 },
          splitLine: { lineStyle: { opacity: 0.15 } },
        },
        series: [
          {
            type: "bar",
            data: values.map((v) => ({
              value: v,
              itemStyle: { color: v >= 0 ? "#e74c3c" : "#27ae60" },
            })),
            barMaxWidth: 18,
          },
        ],
      });
      const onResize = () => chart?.resize();
      window.addEventListener("resize", onResize);
      host._flowChartCleanup = () => {
        window.removeEventListener("resize", onResize);
        chart?.dispose();
      };
    })
    .catch(() => {
      host.innerHTML = '<p class="meta">走势加载失败</p>';
    });
  return () => host._flowChartCleanup?.();
}

function constituentsRowsHtml(rows) {
  if (!rows?.length) {
    return "";
  }
  return rows
    .map(
      (r) => `<tr>
        <td><a href="#" class="stock-code-link" data-code="${escapeHtml(r.code)}"><code>${escapeHtml(r.code)}</code></a></td>
        <td>${escapeHtml(r.name || "")}</td>
        <td class="num ${pctClassNum(r.change_pct)}">${fmtPct(r.change_pct)}</td>
        <td class="num">${fmtYi(r.float_market_cap)}</td>
      </tr>`
    )
    .join("");
}

function bindStockLinks(root) {
  root.querySelectorAll(".stock-code-link").forEach((link) => {
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

function renderSectorBody(data) {
  const summary = data.summary || {};
  const rows = data.constituents || [];
  const history = data.flow_history || [];
  const pending = Boolean(data.constituents_pending);
  let html = `<p class="meta">截止 <strong>${escapeHtml(data.trade_date || "—")}</strong> · 区间 <strong>${escapeHtml(data.period)}</strong>`;
  if (data.constituent_date && data.constituent_date !== data.trade_date) {
    html += ` · 成分股索引日 ${escapeHtml(data.constituent_date)}`;
  }
  if (data.alias_note) {
    html += ` · ${escapeHtml(data.alias_note)}`;
  }
  if (data.data_source) {
    html += ` · 成分股 ${escapeHtml(data.data_source === "db" ? "库内" : "同花顺")}`;
  }
  html += "</p>";

  if (data.fetch_error) {
    html += `<div class="banner-error">${escapeHtml(data.fetch_error)}</div>`;
  }

  if (summary && Object.keys(summary).length) {
    html += `<div class="stats">
      <span>净流入 <strong class="${pctClassNum(summary.net_amt)}">${fmtYi(summary.net_amt)}</strong> 亿</span>
      <span>流入 <strong>${fmtYi(summary.inflow_amt)}</strong> 亿</span>
      <span>流出 <strong>${fmtYi(summary.outflow_amt)}</strong> 亿</span>
      <span>涨跌 <strong>${escapeHtml(summary.change_pct || "—")}</strong></span>
      <span>流通市值 <strong>${fmtYi(summary.float_market_cap)}</strong> 亿</span>
    </div>`;
  } else {
    html += '<p class="meta">该区间暂无资金摘要（可能未入库或行业名不匹配）。</p>';
  }

  if (history.length) {
    html += `<section class="panel sector-flow-history">
      <h3 class="sub">近 ${history.length} 日净流入（库内每日「即时」快照）</h3>
      <div class="chart-wrap" style="height:200px"><div id="sector-flow-history-chart" class="fund-nav-compare-chart"></div></div>
    </section>`;
  }

  const countLabel = pending ? "加载中…" : `${rows.length} 只`;
  html += `<section class="panel"><h3 class="sub" id="sector-constituents-title">成分股（${countLabel}）</h3>`;
  html += `<table class="data"><colgroup>
    <col style="width:16%" /><col style="width:38%" /><col style="width:18%" /><col style="width:28%" />
  </colgroup><thead><tr>
    <th>代码</th><th>名称</th><th class="num">涨跌幅</th><th class="num">流通市值(亿)</th>
  </tr></thead><tbody id="sector-constituents-body">`;
  if (pending) {
    html += '<tr><td colspan="4" class="loading">成分股加载中（首次可能需 1–2 分钟）…</td></tr>';
  } else if (!rows.length) {
    html += '<tr><td colspan="4">暂无成分股（需先同步行业成分股）</td></tr>';
  } else {
    html += constituentsRowsHtml(rows);
  }
  html += "</tbody></table></section>";
  html +=
    '<p class="footnote meta">资金来自同花顺行业资金流；成分股来自同花顺 thshy；行情/市值来自全 A 日表。</p>';
  return html;
}

export async function openSectorDrawer({ industry, period, trade_date }) {
  openDrawer({ title: industry, html: "", wide: true });
  setDrawerLoading();
  let disposeChart = null;
  try {
    const data = await apiGet(`/sectors/${encodeURIComponent(industry)}`, {
      period,
      trade_date,
    });
    setDrawerBody(renderSectorBody(data));
    const chartHost = document.getElementById("sector-flow-history-chart");
    if (chartHost && data.flow_history?.length) {
      disposeChart = renderFlowHistory(chartHost, data.flow_history);
    }
    bindStockLinks(document.getElementById("drawer-body"));
  } catch (err) {
    setDrawerBody(`<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`);
  }
  return () => disposeChart?.();
}
