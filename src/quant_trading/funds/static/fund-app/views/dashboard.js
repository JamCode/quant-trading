import { apiGet, escapeHtml, fmtPct, fmtYi, pctClass, pctClassNum } from "../api.js";
import { navigate, setQuery } from "../router.js";
import { openFundDrawer } from "../components/fund-drawer.js";
import { openSectorDrawer } from "../components/sector-drawer.js";

const main = () => document.getElementById("app-main");

function readState(query, meta) {
  const period =
    query.period && meta.period_options?.includes(query.period)
      ? query.period
      : meta.default_period || "即时";
  return {
    period,
    trade_date: query.trade_date || "",
    industry: query.industry || "",
    fund_sort: query.fund_sort || "return_1y",
  };
}

function flowTableRows(rows, focus, onRowClick) {
  if (!rows?.length) {
    return '<tr><td colspan="3">暂无数据</td></tr>';
  }
  return rows
    .map((r) => {
      const active = r.industry === focus ? " active-row" : "";
      return `<tr class="clickable${active}" data-industry="${escapeHtml(r.industry)}">
        <td>${escapeHtml(r.industry)}</td>
        <td class="num ${pctClassNum(r.net_amt)}">${fmtYi(r.net_amt)}</td>
        <td class="${pctClass(r.change_pct)}">${escapeHtml(r.change_pct || "—")}</td>
      </tr>`;
    })
    .join("");
}

function relatedFundsTable(funds, minPct) {
  if (!funds?.length) {
    return '<p class="meta">暂无相关基金。</p>';
  }
  const head = `<table class="data"><thead><tr>
    <th>代码</th><th>简称</th><th class="num">暴露%</th><th>日涨跌</th>
    <th class="num">近1月</th><th class="num">近3月</th><th class="num">近1年</th><th>申购</th>
  </tr></thead><tbody>`;
  const body = funds
    .map(
      (f) => `<tr>
      <td><code><a href="#" data-fund="${escapeHtml(f.code)}">${escapeHtml(f.code)}</a></code></td>
      <td>${escapeHtml(f.short_name || "—")}</td>
      <td class="num"><strong>${f.weight_pct != null ? Number(f.weight_pct).toFixed(2) : "—"}</strong></td>
      <td class="${pctClass(f.daily_pct)}">${escapeHtml(f.daily_pct || "—")}</td>
      <td class="num ${pctClassNum(f.return_1m)}">${f.return_1m != null ? `${Number(f.return_1m).toFixed(2)}%` : "—"}</td>
      <td class="num ${pctClassNum(f.return_3m)}">${f.return_3m != null ? `${Number(f.return_3m).toFixed(2)}%` : "—"}</td>
      <td class="num ${pctClassNum(f.return_1y)}">${f.return_1y != null ? `${Number(f.return_1y).toFixed(2)}%` : "—"}</td>
      <td>${escapeHtml(f.subscribe_status || "—")}</td>
    </tr>`
    )
    .join("");
  return `${head}${body}</tbody></table>`;
}

function bindDashboardEvents(state, meta) {
  const el = main();
  el.querySelector("#dash-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const fd = new FormData(event.target);
    navigate("/", {
      query: {
        period: fd.get("period"),
        trade_date: fd.get("trade_date"),
        industry: fd.get("industry"),
        fund_sort: fd.get("fund_sort"),
      },
    });
    window.dispatchEvent(new PopStateEvent("popstate"));
  });

  el.querySelectorAll("tr[data-industry]").forEach((row) => {
    row.addEventListener("click", () => {
      const industry = row.getAttribute("data-industry");
      setQuery({
        drawer: "sector",
        industry,
        period: state.period,
        trade_date: state.trade_date,
      });
      openSectorDrawer({
        industry,
        period: state.period,
        trade_date: state.trade_date,
      });
    });
  });

  el.querySelectorAll("[data-fund]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const code = link.getAttribute("data-fund");
      setQuery({ drawer: "fund", code });
      openFundDrawer({ code });
    });
  });
}

export async function mountDashboard(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/flow");
    const state = readState(query, meta);
    const data = await apiGet("/dashboard", {
      period: state.period,
      trade_date: state.trade_date,
      industry: state.industry,
      fund_sort: state.fund_sort,
    });
    const focus = data.focus_industry || "";
    const periodOpts = (data.period_options || meta.period_options || [])
      .map(
        (p) =>
          `<option value="${escapeHtml(p)}"${p === data.period ? " selected" : ""}>${escapeHtml(p)}</option>`
      )
      .join("");
    const dateOpts =
      '<option value="">最新</option>' +
      (meta.date_options || [])
        .map(
          (d) =>
            `<option value="${escapeHtml(d)}"${d === (data.trade_date || "") ? " selected" : ""}>${escapeHtml(d)}</option>`
        )
        .join("");
    const indOpts =
      '<option value="">自动（净流入 Top1）</option>' +
      (data.industry_options || [])
        .map(
          (ind) =>
            `<option value="${escapeHtml(ind)}"${ind === focus ? " selected" : ""}>${escapeHtml(ind)}</option>`
        )
        .join("");

    let html = `<p class="sub meta">行业主力资金 + 季报持仓穿透暴露 · 相关基金按收益排序</p>
    <form class="toolbar" id="dash-form">
      <label><span>统计区间</span><select name="period">${periodOpts}</select></label>
      <label><span>交易日</span><select name="trade_date">${dateOpts}</select></label>
      <label><span>当前行业</span><select name="industry">${indOpts}</select></label>
      <label><span>基金排序</span><select name="fund_sort">
        <option value="return_1y"${state.fund_sort === "return_1y" ? " selected" : ""}>近1年</option>
        <option value="return_3m"${state.fund_sort === "return_3m" ? " selected" : ""}>近3月</option>
        <option value="daily_pct"${state.fund_sort === "daily_pct" ? " selected" : ""}>日涨跌</option>
        <option value="weight_pct"${state.fund_sort === "weight_pct" ? " selected" : ""}>暴露权重</option>
      </select></label>
      <button type="submit">刷新</button>
    </form>`;

    if (data.trade_date) {
      html += `<p class="meta">数据日 <strong>${escapeHtml(data.trade_date)}</strong> · 区间 <strong>${escapeHtml(data.period)}</strong>`;
      if (focus) {
        html += ` · 当前行业 <strong>${escapeHtml(focus)}</strong>`;
      }
      html += "</p>";
    } else {
      html += '<p class="meta">尚无行业资金数据，请确认爬虫已运行。</p>';
    }

    html += `<div class="grid-2">
      <section class="panel"><h2>净流入 Top 10</h2>
        <table class="data"><thead><tr><th>行业</th><th class="num">净额(亿)</th><th>涨跌</th></tr></thead>
        <tbody>${flowTableRows(data.top_in, focus)}</tbody></table>
      </section>
      <section class="panel"><h2>净流出 Top 10</h2>
        <table class="data"><thead><tr><th>行业</th><th class="num">净额(亿)</th><th>涨跌</th></tr></thead>
        <tbody>${flowTableRows(data.top_out, focus)}</tbody></table>
      </section>
    </div>`;

    html += `<section class="panel"><h2>当前行业 · 相关基金（暴露 ≥ ${data.min_exposure_pct ?? 10}%）</h2>`;
    if (!data.has_exposure) {
      html +=
        "<p class=\"meta\">尚无基金–行业暴露数据。请先运行持仓与行业映射管道。</p>";
    } else if (data.related_funds?.length) {
      html += `<p class="meta">暴露基于季报持仓，报告期 <strong>${escapeHtml(data.exposure_report_date || "—")}</strong>。</p>`;
      html += relatedFundsTable(data.related_funds, data.min_exposure_pct);
    } else if (focus) {
      html += `<p class="meta">行业 <strong>${escapeHtml(focus)}</strong> 下暂无满足阈值的基金。</p>`;
    } else {
      html += '<p class="meta">在上方选择行业或点击流入/流出表中的行业行。</p>';
    }
    html += "</section>";
    html += `<p class="footnote"><strong>说明：</strong>点击行业行打开成分股抽屉；下拉切换当前行业不打开抽屉。</p>`;

    host.innerHTML = html;
    bindDashboardEvents(state, meta);
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
