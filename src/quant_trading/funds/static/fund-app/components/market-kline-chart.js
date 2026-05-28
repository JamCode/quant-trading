/** ECharts K-line + volume/amount sub-chart (A-share colors: up red, down green). */

import { fmtYi } from "../api.js";

let echartsPromise = null;

export function loadEcharts() {
  if (window.echarts) {
    return Promise.resolve(window.echarts);
  }
  if (!echartsPromise) {
    echartsPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js";
      s.onload = () => resolve(window.echarts);
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  return echartsPromise;
}

const UP = "#f85149";
const DOWN = "#3fb950";

function fmtVolAxis(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "";
  }
  if (Math.abs(n) >= 1e8) {
    return `${(n / 1e8).toFixed(1)}亿`;
  }
  if (Math.abs(n) >= 1e4) {
    return `${(n / 1e4).toFixed(0)}万`;
  }
  return String(Math.round(n));
}

function sliceRange(points, rangeKey) {
  const limits = { "1m": 22, "3m": 66, "6m": 126, "1y": 250 };
  const n = limits[rangeKey];
  if (!n || points.length <= n) {
    return points;
  }
  return points.slice(-n);
}

function buildOption(points, name) {
  const dates = points.map((p) => p.trade_date);
  const ohlc = points.map((p) => [
    p.open ?? p.close,
    p.close,
    p.low ?? p.close,
    p.high ?? p.close,
  ]);
  const useAmount = points.some((p) => p.amount != null && Number(p.amount) > 0);
  const volLabel = useAmount ? "成交额" : "成交量";
  const volData = points.map((p, i) => {
    const v = useAmount ? p.amount : p.volume;
    const n = Number(v) || 0;
    const o = ohlc[i][0];
    const c = ohlc[i][1];
    return {
      value: n,
      itemStyle: { color: c >= o ? UP : DOWN, opacity: 0.85 },
    };
  });

  return {
    animation: false,
    backgroundColor: "transparent",
    legend: {
      data: [name, volLabel],
      textStyle: { color: "#8b949e" },
      top: 4,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "rgba(22,27,34,0.95)",
      borderColor: "#30363d",
      textStyle: { color: "#e6edf3", fontSize: 12 },
      formatter(params) {
        const k = params.find((x) => x.seriesType === "candlestick");
        if (!k || !k.data) {
          return "";
        }
        const idx = k.dataIndex;
        const p = points[idx];
        const [open, close, low, high] = k.data;
        const chg = p.change_pct != null ? `${Number(p.change_pct).toFixed(2)}%` : "—";
        let vol = "—";
        if (useAmount && p.amount != null) {
          const a = Number(p.amount);
          vol = Math.abs(a) >= 1e8 ? `${(a / 1e8).toFixed(2)}亿` : fmtVolAxis(a);
        } else if (p.volume != null) {
          vol = fmtVolAxis(p.volume);
        }
        return [
          `<strong>${p.trade_date}</strong>`,
          `开 ${open}  高 ${high}`,
          `低 ${low}  收 ${close}`,
          `涨跌 ${chg}`,
          `${volLabel} ${vol}`,
        ].join("<br/>");
      },
    },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    grid: [
      { left: 56, right: 16, top: 36, height: "56%" },
      { left: 56, right: 16, top: "76%", height: "14%" },
    ],
    xAxis: [
      {
        type: "category",
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: "#30363d" } },
        axisLabel: { color: "#8b949e", fontSize: 11 },
        splitLine: { show: false },
        min: "dataMin",
        max: "dataMax",
      },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: "#30363d" } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitLine: { lineStyle: { color: "#21262d" } },
        axisLabel: { color: "#8b949e", fontSize: 11 },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: {
          color: "#8b949e",
          fontSize: 10,
          formatter: (v) => (useAmount ? fmtVolAxis(v) : fmtVolAxis(v)),
        },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 },
      {
        show: true,
        xAxisIndex: [0, 1],
        type: "slider",
        bottom: 2,
        height: 22,
        start: 60,
        end: 100,
        borderColor: "#30363d",
        fillerColor: "rgba(77,163,255,0.15)",
        handleStyle: { color: "#4da3ff" },
        textStyle: { color: "#8b949e" },
      },
    ],
    series: [
      {
        name,
        type: "candlestick",
        data: ohlc,
        itemStyle: {
          color: UP,
          color0: DOWN,
          borderColor: UP,
          borderColor0: DOWN,
        },
      },
      {
        name: volLabel,
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volData,
        barMaxWidth: 12,
      },
    ],
  };
}

/**
 * @param {object} opts
 * @param {HTMLElement} opts.host - wrapper with .market-kline-chart div inside
 * @param {Array} opts.points - asc by trade_date
 * @param {string} opts.name
 * @returns {{ setRange: (key: string) => void, dispose: () => void }}
 */
export async function mountMarketKlineChart({ host, points, name }) {
  const el = host.querySelector(".market-kline-chart");
  if (!el || !points.length) {
    return { setRange: () => {}, dispose: () => {} };
  }

  const echarts = await loadEcharts();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  let currentRange = "1y";
  let allPoints = points;

  const render = (rangeKey) => {
    currentRange = rangeKey;
    const sliced = sliceRange(allPoints, rangeKey);
    chart.setOption(buildOption(sliced, name), { notMerge: true });
  };

  render(currentRange);

  const onResize = () => chart.resize();
  window.addEventListener("resize", onResize);

  host.querySelectorAll(".chart-toolbar button[data-range]").forEach((btn) => {
    btn.addEventListener("click", () => {
      host.querySelectorAll(".chart-toolbar button[data-range]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      render(btn.getAttribute("data-range") || "1y");
    });
  });

  return {
    setRange: render,
    dispose() {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    },
  };
}

export function klineChartShell(metaText) {
  return `<div class="chart-toolbar" role="group" aria-label="K线区间">
      <div class="chart-toolbar-ranges">
        <span class="sub chart-toolbar-label">区间</span>
        <button type="button" data-range="1m">1月</button>
        <button type="button" data-range="3m">3月</button>
        <button type="button" data-range="6m">6月</button>
        <button type="button" data-range="1y" class="active">1年</button>
        <button type="button" data-range="all">全部</button>
      </div>
      <p class="meta chart-toolbar-meta">${metaText}</p>
    </div>
    <div class="chart-wrap market-kline-wrap">
      <div class="market-kline-chart" role="img" aria-label="K线走势图"></div>
    </div>`;
}
