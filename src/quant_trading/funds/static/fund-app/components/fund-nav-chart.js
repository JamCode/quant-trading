/** Fund NAV vs CSI 300 normalized return chart (ECharts). */

import { loadEcharts } from "./market-kline-chart.js";
import { escapeHtml, pctClassNum } from "../api.js";

export const HS300_CODE = "000300";
const FUND_COLOR = "#4da3ff";
const INDEX_COLOR = "#f0883e";

const RANGE_LIMITS = {
  "1m": 22,
  "3m": 66,
  "6m": 126,
  "1y": 250,
  "3y": 750,
  "5y": 1250,
};

export function parseNavPoints(items) {
  return (items || [])
    .map((r) => {
      const nav_unit = Number(String(r.nav_unit ?? "").replace(/,/g, ""));
      return {
        nav_date: String(r.nav_date || "").slice(0, 10),
        nav_unit,
      };
    })
    .filter((r) => r.nav_date && Number.isFinite(r.nav_unit) && r.nav_unit > 0)
    .sort((a, b) => a.nav_date.localeCompare(b.nav_date));
}

export function parseIndexPoints(items) {
  return (items || [])
    .map((r) => ({
      trade_date: String(r.trade_date || "").slice(0, 10),
      close: Number(r.close),
    }))
    .filter((r) => r.trade_date && Number.isFinite(r.close) && r.close > 0)
    .sort((a, b) => a.trade_date.localeCompare(b.trade_date));
}

function sliceNavByRange(navAsc, rangeKey) {
  const n = RANGE_LIMITS[rangeKey];
  if (!n || navAsc.length <= n) {
    return navAsc;
  }
  return navAsc.slice(-n);
}

/** Index close on each fund NAV date (forward-fill from prior trading day). */
export function alignIndexToNavDates(navSlice, indexAsc) {
  if (!navSlice.length || !indexAsc.length) {
    return [];
  }
  let j = 0;
  let lastClose = null;
  const out = [];
  for (const f of navSlice) {
    while (j < indexAsc.length && indexAsc[j].trade_date <= f.nav_date) {
      lastClose = indexAsc[j].close;
      j += 1;
    }
    if (lastClose != null) {
      out.push({ nav_date: f.nav_date, close: lastClose });
    }
  }
  return out;
}

export function periodReturns(navSlice, indexAligned) {
  if (!navSlice.length) {
    return { fundReturn: null, indexReturn: null, excess: null };
  }
  const navStart = navSlice[0].nav_unit;
  const navEnd = navSlice[navSlice.length - 1].nav_unit;
  const fundReturn = (navEnd / navStart - 1) * 100;
  let indexReturn = null;
  if (indexAligned.length >= 2) {
    const i0 = indexAligned[0].close;
    const i1 = indexAligned[indexAligned.length - 1].close;
    indexReturn = (i1 / i0 - 1) * 100;
  }
  const excess =
    indexReturn != null && Number.isFinite(fundReturn) ? fundReturn - indexReturn : null;
  return { fundReturn, indexReturn, excess };
}

function normalizedNav(navSlice) {
  const start = navSlice[0].nav_unit;
  return navSlice.map((p) => ({
    date: p.nav_date,
    value: (100 * p.nav_unit) / start,
  }));
}

function normalizedIndex(indexAligned) {
  if (!indexAligned.length) {
    return [];
  }
  const start = indexAligned[0].close;
  return indexAligned.map((p) => ({
    date: p.nav_date,
    value: (100 * p.close) / start,
  }));
}

function fmtReturnPct(n) {
  if (n == null || !Number.isFinite(n)) {
    return "—";
  }
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function returnStatsHtml({ fundReturn, indexReturn, excess, span }) {
  const fundCls = pctClassNum(fundReturn);
  const idxCls = pctClassNum(indexReturn);
  const excCls = pctClassNum(excess);
  return `<dl class="fund-return-stats">
    <div><dt>区间</dt><dd>${escapeHtml(span || "—")}</dd></div>
    <div><dt>基金收益</dt><dd class="num ${fundCls}">${escapeHtml(fmtReturnPct(fundReturn))}</dd></div>
    <div><dt>沪深300同期</dt><dd class="num ${idxCls}">${escapeHtml(fmtReturnPct(indexReturn))}</dd></div>
    <div><dt>超额</dt><dd class="num ${excCls}">${escapeHtml(fmtReturnPct(excess))}</dd></div>
  </dl>`;
}

function pairedSeries(navSlice, indexAsc) {
  const aligned = alignIndexToNavDates(navSlice, indexAsc);
  if (!aligned.length) {
    return {
      fundSeries: normalizedNav(navSlice),
      indexSeries: [],
      navSlice,
      indexAligned: [],
    };
  }
  const ok = new Set(aligned.map((a) => a.nav_date));
  const pairedNav = navSlice.filter((n) => ok.has(n.nav_date));
  return {
    fundSeries: normalizedNav(pairedNav),
    indexSeries: normalizedIndex(aligned),
    navSlice: pairedNav,
    indexAligned: aligned,
  };
}

function buildCompareOption(fundSeries, indexSeries, fundLabel) {
  const dates = fundSeries.map((p) => p.date);
  const series = [
    {
      name: fundLabel,
      type: "line",
      data: fundSeries.map((p) => p.value),
      showSymbol: false,
      lineStyle: { width: 2, color: FUND_COLOR },
    },
  ];
  if (indexSeries.length === fundSeries.length && indexSeries.length > 0) {
    series.push({
      name: "沪深300",
      type: "line",
      data: indexSeries.map((p) => p.value),
      showSymbol: false,
      lineStyle: { width: 2, color: INDEX_COLOR },
    });
  }
  return {
    animation: false,
    backgroundColor: "transparent",
    legend: {
      data: series.map((s) => s.name),
      textStyle: { color: "#8b949e" },
      top: 4,
    },
    grid: { left: 56, right: 16, top: 36, bottom: 32 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(22,27,34,0.95)",
      borderColor: "#30363d",
      textStyle: { color: "#e6edf3", fontSize: 12 },
      formatter(params) {
        const lines = [params[0]?.axisValue || ""];
        params.forEach((s) => {
          const v = Number(s.data);
          const pct = Number.isFinite(v) ? `${(v - 100).toFixed(2)}%` : "—";
          lines.push(`${s.marker}${s.seriesName}: ${pct}（基准100）`);
        });
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { color: "#8b949e", fontSize: 11 },
      axisLine: { lineStyle: { color: "#30363d" } },
    },
    yAxis: {
      scale: true,
      axisLabel: {
        color: "#8b949e",
        formatter: (v) => `${(Number(v) - 100).toFixed(0)}%`,
      },
      splitLine: { lineStyle: { color: "#21262d" } },
    },
    series,
  };
}

export function navCompareChartShell() {
  return `<div class="chart-toolbar" role="group" aria-label="净值区间">
      <div class="chart-toolbar-ranges">
        <span class="sub chart-toolbar-label">区间</span>
        <button type="button" data-range="1m">1月</button>
        <button type="button" data-range="3m">3月</button>
        <button type="button" data-range="6m">6月</button>
        <button type="button" data-range="1y" class="active">1年</button>
        <button type="button" data-range="3y">3年</button>
        <button type="button" data-range="5y">5年</button>
        <button type="button" data-range="all">全部</button>
      </div>
      <p class="meta chart-toolbar-meta">净值与沪深300均按区间起点归一为100，便于对比</p>
    </div>
    <div id="fund-return-stats-host"></div>
    <div class="chart-wrap fund-nav-compare-wrap">
      <div class="fund-nav-compare-chart" role="img" aria-label="净值走势对比"></div>
    </div>`;
}

/**
 * @param {object} opts
 * @param {HTMLElement} opts.host
 * @param {Array} opts.navAsc - parsed nav points asc
 * @param {Array} opts.indexAsc - parsed index points asc
 * @param {string} opts.fundLabel
 */
export async function mountFundNavCompareChart({ host, navAsc, indexAsc, fundLabel }) {
  const chartEl = host.querySelector(".fund-nav-compare-chart");
  const statsEl = host.querySelector("#fund-return-stats-host");
  if (!chartEl || !navAsc.length) {
    return { dispose: () => {} };
  }

  const echarts = await loadEcharts();
  const chart = echarts.init(chartEl, null, { renderer: "canvas" });
  let currentRange = "1y";

  const render = (rangeKey) => {
    currentRange = rangeKey;
    const navSliceRaw = sliceNavByRange(navAsc, rangeKey);
    const { fundSeries, indexSeries, navSlice, indexAligned } = pairedSeries(
      navSliceRaw,
      indexAsc
    );
    const rets = periodReturns(navSlice, indexAligned);
    const span =
      navSlice.length > 0
        ? `${navSlice[0].nav_date} ~ ${navSlice[navSlice.length - 1].nav_date}`
        : "";
    if (statsEl) {
      statsEl.innerHTML = returnStatsHtml({ ...rets, span });
    }
    chart.setOption(buildCompareOption(fundSeries, indexSeries, fundLabel), {
      notMerge: true,
    });
  };

  render(currentRange);

  host.querySelectorAll(".chart-toolbar button[data-range]").forEach((btn) => {
    btn.addEventListener("click", () => {
      host.querySelectorAll(".chart-toolbar button[data-range]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      render(btn.getAttribute("data-range") || "1y");
    });
  });

  const onResize = () => chart.resize();
  window.addEventListener("resize", onResize);

  return {
    dispose() {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    },
  };
}
