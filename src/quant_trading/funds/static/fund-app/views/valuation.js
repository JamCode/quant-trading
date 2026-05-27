import { apiGet, escapeHtml } from "../api.js";
import { navigate } from "../router.js";

const main = () => document.getElementById("app-main");

function peNum(v) {
  if (v === null || v === undefined || v === "") {
    return "—";
  }
  return Number(v).toFixed(2);
}

function indexTableHead(region) {
  if (region === "cn") {
    return `<tr>
      <th>指数</th>
      <th class="num">滚动 PE</th>
      <th class="num">静态 PE</th>
      <th>数据日</th>
    </tr>`;
  }
  if (region === "us") {
    return `<tr>
      <th>指数</th>
      <th class="num">PE(TTM)</th>
      <th class="num">CAPE</th>
      <th>数据日</th>
    </tr>`;
  }
  return `<tr>
    <th>指数</th>
    <th class="num">PE(TTM)</th>
    <th>数据日</th>
  </tr>`;
}

function indexTableColgroup(region) {
  if (region === "cn") {
    return `<colgroup>
      <col class="col-name" style="width:40%" />
      <col style="width:20%" /><col style="width:20%" /><col style="width:20%" />
    </colgroup>`;
  }
  if (region === "us") {
    return `<colgroup>
      <col class="col-name" style="width:40%" />
      <col style="width:20%" /><col style="width:20%" /><col style="width:20%" />
    </colgroup>`;
  }
  return `<colgroup>
    <col class="col-name" style="width:50%" />
    <col style="width:25%" /><col style="width:25%" />
  </colgroup>`;
}

function indexTableRow(row, region) {
  const cells = [`<td class="name">${escapeHtml(row.index_name)}</td>`];
  if (region === "cn") {
    cells.push(
      `<td class="num">${peNum(row.pe_ttm)}</td>`,
      `<td class="num">${peNum(row.pe_static)}</td>`
    );
  } else if (region === "us") {
    cells.push(
      `<td class="num">${peNum(row.pe_ttm)}</td>`,
      `<td class="num">${peNum(row.pe_cape)}</td>`
    );
  } else {
    cells.push(`<td class="num">${peNum(row.pe_ttm)}</td>`);
  }
  cells.push(`<td>${escapeHtml(row.trade_date || "—")}</td>`);
  return cells.join("");
}

function indexTableColspan(region) {
  if (region === "cn" || region === "us") {
    return 4;
  }
  return 3;
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

let chartInstance = null;

function renderChart(points, region) {
  const canvas = document.getElementById("peChart");
  if (!canvas || !window.Chart) {
    return;
  }
  if (chartInstance) {
    chartInstance.destroy();
  }
  const labels = points.map((p) => p.d);
  const datasets = [];
  if (points.some((p) => p.ttm != null)) {
    datasets.push({
      label: "PE(TTM)",
      data: points.map((p) => p.ttm),
      borderColor: "#4da3ff",
      tension: 0.15,
    });
  }
  if (region === "cn" && points.some((p) => p.static != null)) {
    datasets.push({
      label: "静态 PE",
      data: points.map((p) => p.static),
      borderColor: "#d29922",
      tension: 0.15,
    });
  }
  if (region === "us" && points.some((p) => p.cape != null)) {
    datasets.push({
      label: "CAPE",
      data: points.map((p) => p.cape),
      borderColor: "#a371f7",
      tension: 0.15,
    });
  }
  chartInstance = new window.Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false },
  });
}

export async function mountValuation(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  const tab = query.tab === "industry" ? "industry" : "index";
  const region = query.region || "cn";
  const industryLevel = Number(query.industry_level || 2);

  try {
    if (tab === "index") {
      const latest = await apiGet("/valuation/indices", { region, limit: 100 });
      const items = latest.items || [];
      const indexCode = query.index_code || (items[0] && items[0].index_code) || "000300.SH";
      let history = { points: [] };
      if (indexCode) {
        history = await apiGet("/valuation/indices/history", {
          region,
          index_code: indexCode,
          limit: 730,
        });
      }
      let rows = "";
      items.forEach((row) => {
        const active = row.index_code === indexCode ? " active-row" : "";
        rows += `<tr class="clickable${active}" data-code="${escapeHtml(row.index_code)}">${indexTableRow(row, region)}</tr>`;
      });
      const colspan = indexTableColspan(region);
      host.innerHTML = `
        <div class="region-tabs" id="val-tabs">
          <a href="#" data-tab="index" class="active">宽基指数</a>
          <a href="#" data-tab="industry">行业 PE</a>
        </div>
        <div class="region-tabs">
          ${["cn", "hk", "us"]
            .map(
              (r) =>
                `<a href="#" data-region="${r}" class="${r === region ? "active" : ""}">${r === "cn" ? "A股" : r === "hk" ? "港股" : "美股"}</a>`
            )
            .join("")}
        </div>
        <section class="panel"><h2>${region === "cn" ? "A股" : region === "hk" ? "港股" : "美股"} · 最新 PE</h2>
          <table class="pe-table">${indexTableColgroup(region)}<thead>${indexTableHead(region)}</thead>
          <tbody>${rows || `<tr><td colspan="${colspan}" class="empty">暂无</td></tr>`}</tbody></table>
        </section>
        <section class="panel"><h2>${escapeHtml(history.index_name || indexCode)} · 历史</h2>
          <div class="chart-wrap" style="height:320px"><canvas id="peChart"></canvas></div>
        </section>`;
      bindValuationNav(query, tab, region, industryLevel);
      host.querySelectorAll("tr[data-code]").forEach((row) => {
        row.addEventListener("click", () => {
          navigate("/valuation", {
            query: { tab: "index", region, index_code: row.getAttribute("data-code") },
          });
          window.dispatchEvent(new PopStateEvent("popstate"));
        });
      });
      await loadChartJs();
      renderChart(history.points || [], region);
    } else {
      const latest = await apiGet("/valuation/industry", { industry_level: industryLevel, limit: 200 });
      const items = latest.items || [];
      const industryCode =
        query.industry_code || (items[0] && items[0].industry_code) || "";
      let history = { points: [] };
      if (industryCode) {
        history = await apiGet("/valuation/industry/history", {
          industry_code: industryCode,
          limit: 730,
        });
      }
      let rows = "";
      items.forEach((row) => {
        const active = row.industry_code === industryCode ? " active-row" : "";
        rows += `<tr class="clickable${active}" data-code="${escapeHtml(row.industry_code)}">
          <td class="name">${escapeHtml(row.industry_name)}</td>
          <td class="num">${peNum(row.pe_weighted)}</td>
          <td class="num">${peNum(row.pe_median)}</td>
          <td class="num">${peNum(row.pe_avg)}</td>
          <td>${escapeHtml(row.trade_date || "—")}</td>
        </tr>`;
      });
      host.innerHTML = `
        <div class="region-tabs" id="val-tabs">
          <a href="#" data-tab="index">宽基指数</a>
          <a href="#" data-tab="industry" class="active">行业 PE</a>
        </div>
        <p class="meta">库内最新 ${escapeHtml(latest.trade_date || "—")}</p>
        <section class="panel"><h2>国证行业 · 最新静态 PE</h2>
          <table class="pe-table">
            <colgroup>
              <col class="col-name" style="width:32%" />
              <col style="width:17%" /><col style="width:17%" /><col style="width:17%" /><col style="width:17%" />
            </colgroup>
            <thead><tr>
              <th>行业</th><th class="num">加权 PE</th><th class="num">中位数</th><th class="num">算术平均</th><th>数据日</th>
            </tr></thead>
          <tbody>${rows || '<tr><td colspan="5" class="empty">暂无</td></tr>'}</tbody></table>
        </section>
        <section class="panel"><h2>${escapeHtml(history.industry_name || "")} · 历史</h2>
          <div class="chart-wrap" style="height:320px"><canvas id="peChart"></canvas></div>
        </section>`;
      bindValuationNav(query, tab, region, industryLevel);
      host.querySelectorAll("tr[data-code]").forEach((row) => {
        row.addEventListener("click", () => {
          navigate("/valuation", {
            query: {
              tab: "industry",
              industry_level: industryLevel,
              industry_code: row.getAttribute("data-code"),
            },
          });
          window.dispatchEvent(new PopStateEvent("popstate"));
        });
      });
      await loadChartJs();
      const pts = (history.points || []).map((p) => ({
        d: p.d,
        ttm: p.weighted,
        static: p.median,
      }));
      renderChart(pts, "cn");
    }
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}

function bindValuationNav(query, tab, region, industryLevel) {
  document.getElementById("val-tabs")?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-tab]");
    if (!link) {
      return;
    }
    event.preventDefault();
    const t = link.getAttribute("data-tab");
    navigate("/valuation", {
      query: t === "industry" ? { tab: "industry", industry_level: industryLevel } : { tab: "index", region },
    });
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  document.querySelectorAll("[data-region]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate("/valuation", {
        query: { tab: "index", region: link.getAttribute("data-region") },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
  });
}
