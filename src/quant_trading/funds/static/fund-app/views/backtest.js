import { apiBase, apiGet, escapeHtml } from "../api.js";
import { mountEquityChart } from "../components/equity-chart.js";

const main = () => document.getElementById("app-main");

let disposeChart = null;

function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

function defaultDates() {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 3);
  return { start: isoDate(start), end: isoDate(end) };
}

function fmtPctRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(digits);
}

function cnIndices(items) {
  return (items || []).filter((r) => /^[0-9]{6}$/.test(String(r.code || "")));
}

function renderParamFields(host, strategy, values) {
  host.innerHTML = "";
  if (!strategy?.params?.length) {
    return;
  }
  strategy.params.forEach((spec) => {
    const label = document.createElement("label");
    const title = document.createElement("span");
    title.textContent = spec.label || spec.name;
    const input = document.createElement("input");
    input.type = "number";
    input.name = `param-${spec.name}`;
    input.value = values[spec.name] ?? spec.default;
    if (spec.min != null) {
      input.min = String(spec.min);
    }
    if (spec.max != null) {
      input.max = String(spec.max);
    }
    label.appendChild(title);
    label.appendChild(input);
    host.appendChild(label);
  });
}

function collectParams(strategy) {
  const out = {};
  if (!strategy?.params) {
    return out;
  }
  strategy.params.forEach((spec) => {
    const input = document.querySelector(`input[name="param-${spec.name}"]`);
    if (!input) {
      return;
    }
    out[spec.name] = spec.type === "int" ? parseInt(input.value, 10) : parseFloat(input.value);
  });
  return out;
}

function renderMetrics(summary) {
  return `<dl class="metric-cards">
    <div class="metric-card"><dt>总收益率</dt><dd>${escapeHtml(fmtPctRatio(summary.total_return))}</dd></div>
    <div class="metric-card"><dt>最大回撤</dt><dd>${escapeHtml(fmtPctRatio(summary.max_drawdown))}</dd></div>
    <div class="metric-card"><dt>Sharpe(近似)</dt><dd>${escapeHtml(fmtNum(summary.sharpe_ann_approx))}</dd></div>
    <div class="metric-card"><dt>期末权益</dt><dd>${escapeHtml(fmtNum(summary.final_equity, 0))}</dd></div>
    <div class="metric-card"><dt>样本天数</dt><dd>${escapeHtml(String(summary.bars ?? "—"))}</dd></div>
  </dl>`;
}

export async function mountBacktest() {
  const host = main();
  if (disposeChart) {
    disposeChart();
    disposeChart = null;
  }
  host.innerHTML = '<p class="loading">加载回测配置…</p>';

  const dates = defaultDates();
  let strategies = [];
  let indices = [];

  try {
    const [stratRes, idxRes] = await Promise.all([
      apiGet("/backtest/strategies"),
      apiGet("/market-indices", { region: "cn" }),
    ]);
    strategies = stratRes.strategies || [];
    indices = cnIndices(idxRes.items);
  } catch (err) {
    host.innerHTML = `<div class="banner-error">${escapeHtml(err.message || "加载失败")}</div>`;
    return;
  }

  if (!strategies.length) {
    host.innerHTML = '<div class="banner-error">暂无已注册策略</div>';
    return;
  }
  if (!indices.length) {
    host.innerHTML = '<div class="banner-error">暂无可用指数</div>';
    return;
  }

  const indexOptions = indices
    .map(
      (r) =>
        `<option value="${escapeHtml(r.code)}">${escapeHtml(r.name || r.code)} (${escapeHtml(r.code)})</option>`
    )
    .join("");
  const strategyOptions = strategies
    .map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`)
    .join("");

  host.innerHTML = `<div class="backtest-layout">
    <p class="meta">策略在服务端代码中注册，本页仅选择参数与区间。</p>
    <form id="backtest-form" class="backtest-form panel">
      <label><span>指数</span><select name="code" required>${indexOptions}</select></label>
      <label><span>策略</span><select name="strategy_id" required>${strategyOptions}</select></label>
      <label><span>开始日期</span><input type="date" name="start_date" value="${dates.start}" required></label>
      <label><span>结束日期</span><input type="date" name="end_date" value="${dates.end}" required></label>
      <div id="backtest-params" class="backtest-params"></div>
      <div class="backtest-actions">
        <button type="submit" id="backtest-run">运行回测</button>
      </div>
    </form>
    <div id="backtest-error"></div>
    <div id="backtest-results" hidden>
      <h3 class="view-heading">回测结果</h3>
      <div id="backtest-metrics"></div>
      <div class="equity-chart-wrap panel">
        <div id="equity-chart" class="equity-chart" role="img" aria-label="权益曲线"></div>
      </div>
    </div>
  </div>`;

  const form = host.querySelector("#backtest-form");
  const paramsHost = host.querySelector("#backtest-params");
  const strategySelect = form.querySelector('select[name="strategy_id"]');
  const resultsEl = host.querySelector("#backtest-results");
  const errorEl = host.querySelector("#backtest-error");
  const metricsEl = host.querySelector("#backtest-metrics");
  const chartEl = host.querySelector("#equity-chart");
  const runBtn = host.querySelector("#backtest-run");

  const currentStrategy = () =>
    strategies.find((s) => s.id === strategySelect.value) || strategies[0];

  const syncParams = () => {
    const s = currentStrategy();
    const defaults = {};
    (s?.params || []).forEach((p) => {
      defaults[p.name] = p.default;
    });
    renderParamFields(paramsHost, s, defaults);
  };

  syncParams();
  strategySelect.addEventListener("change", syncParams);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.innerHTML = "";
    resultsEl.hidden = true;
    if (disposeChart) {
      disposeChart();
      disposeChart = null;
    }

    const code = form.code.value;
    const strategy = currentStrategy();
    const body = {
      code,
      strategy_id: strategy.id,
      params: collectParams(strategy),
      start_date: form.start_date.value,
      end_date: form.end_date.value,
    };

    runBtn.disabled = true;
    runBtn.textContent = "运行中…";
    try {
      const response = await fetch(`${apiBase()}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = data.detail || response.statusText;
        errorEl.innerHTML = `<div class="banner-error">${escapeHtml(String(detail))}</div>`;
        return;
      }
      metricsEl.innerHTML = renderMetrics(data.summary || {});
      resultsEl.hidden = false;
      disposeChart = await mountEquityChart(chartEl, data.equity || []);
    } catch (err) {
      errorEl.innerHTML = `<div class="banner-error">${escapeHtml(err.message || "请求失败")}</div>`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "运行回测";
    }
  });
}
