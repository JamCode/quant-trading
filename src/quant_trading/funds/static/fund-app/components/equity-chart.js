import { loadEcharts } from "./market-kline-chart.js";

export async function mountEquityChart(el, points) {
  if (!el || !points?.length) {
    return () => {};
  }
  const echarts = await loadEcharts();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  const dates = points.map((p) => p.trade_date);
  const values = points.map((p) => p.equity);
  chart.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: { left: 56, right: 16, top: 24, bottom: 32 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(22,27,34,0.95)",
      borderColor: "#30363d",
      textStyle: { color: "#e6edf3" },
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
      axisLabel: { color: "#8b949e" },
      splitLine: { lineStyle: { color: "#21262d" } },
    },
    series: [
      {
        type: "line",
        data: values,
        showSymbol: false,
        lineStyle: { width: 2, color: "#4da3ff" },
        areaStyle: { color: "rgba(77,163,255,0.12)" },
      },
    ],
  });
  const onResize = () => chart.resize();
  window.addEventListener("resize", onResize);
  return () => {
    window.removeEventListener("resize", onResize);
    chart.dispose();
  };
}
