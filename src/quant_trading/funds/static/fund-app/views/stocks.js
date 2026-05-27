import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
import { navigate } from "../router.js";

const main = () => document.getElementById("app-main");

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

export async function mountStocks(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/stocks");
    const page = Number(query.page || 1);
    const tradeDate = query.trade_date || meta.latest_trade_date || "";
    const sort = query.sort || "change_pct";
    const order = query.order || "desc";
    const data = await apiGet("/stocks", {
      trade_date: tradeDate,
      q: query.q || "",
      sort,
      order,
      page,
      per_page: query.per_page || 50,
    });

    const dateOpts =
      (meta.trade_dates || []).map((d) => {
        const sel = d === (data.trade_date || tradeDate) ? " selected" : "";
        return `<option value="${escapeHtml(d)}"${sel}>${escapeHtml(d)}</option>`;
      }).join("") ||
      (data.trade_date
        ? `<option value="${escapeHtml(data.trade_date)}" selected>${escapeHtml(data.trade_date)}</option>`
        : "");

    const sortOpts = (meta.sort_options || [])
      .map(
        (o) =>
          `<option value="${escapeHtml(o.id)}"${o.id === sort ? " selected" : ""}>${escapeHtml(o.label)}</option>`
      )
      .join("");

    let rows = "";
    (data.items || []).forEach((r) => {
      rows += `<tr class="clickable" data-code="${escapeHtml(r.code)}">
        <td><code>${escapeHtml(r.code)}</code></td>
        <td>${escapeHtml(r.name || "")}</td>
        <td class="num">${fmtNum(r.price)}</td>
        <td class="num ${pctClassNum(r.change_pct)}">${fmtPct(r.change_pct)}</td>
        <td class="num">${fmtYi(r.float_market_cap)}</td>
        <td class="num">${fmtNum(r.turnover_pct)}</td>
        <td class="num">${fmtYi(r.amount)}</td>
        <td class="num">${fmtNum(r.pe_dynamic)}</td>
        <td class="num">${fmtNum(r.pb)}</td>
        <td class="num ${pctClassNum(r.change_60d_pct)}">${fmtPct(r.change_60d_pct)}</td>
        <td class="num ${pctClassNum(r.change_ytd_pct)}">${fmtPct(r.change_ytd_pct)}</td>
      </tr>`;
    });
    if (!rows) {
      const hint = data.trade_date
        ? "该日暂无股票快照"
        : '暂无数据，请确认 <a href="#" data-nav data-path="/crawler">stock_daily_sync</a> 已运行';
      rows = `<tr><td colspan="11">${hint}</td></tr>`;
    }

    const orderNext = order === "desc" ? "asc" : "desc";

    host.innerHTML = `<p class="sub meta">数据日 <strong>${escapeHtml(data.trade_date || "—")}</strong> · 共 ${data.total ?? 0} 只 · 第 ${data.page}/${data.pages} 页</p>
      <form class="toolbar" id="stocks-form">
        <label><span>数据日</span><select name="trade_date">${dateOpts}</select></label>
        <label><span>搜索</span><input type="search" name="q" value="${escapeHtml(query.q || "")}" placeholder="代码/名称" /></label>
        <label><span>排序</span><select name="sort">${sortOpts}</select></label>
        <label><span>顺序</span><select name="order">
          <option value="desc"${order === "desc" ? " selected" : ""}>降序</option>
          <option value="asc"${order === "asc" ? " selected" : ""}>升序</option>
        </select></label>
        <button type="submit">查询</button>
        <button type="button" id="stocks-toggle-order">切换为${orderNext === "asc" ? "升" : "降"}序</button>
      </form>
      <section class="panel table-scroll">
        <table class="data"><thead><tr>
          <th>代码</th><th>名称</th><th class="num">现价</th><th class="num">涨跌幅</th>
          <th class="num">流通市值(亿)</th><th class="num">换手%</th><th class="num">成交额(亿)</th>
          <th class="num">PE</th><th class="num">PB</th><th class="num">60日</th><th class="num">年初至今</th>
        </tr></thead><tbody>${rows}</tbody></table>
      </section>
      <div class="toolbar">
        ${data.page > 1 ? `<button type="button" data-page="${data.page - 1}">上一页</button>` : ""}
        ${data.page < data.pages ? `<button type="button" data-page="${data.page + 1}">下一页</button>` : ""}
      </div>`;

    host.querySelector("#stocks-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      navigate("/stocks", {
        query: {
          trade_date: fd.get("trade_date"),
          q: fd.get("q"),
          sort: fd.get("sort"),
          order: fd.get("order"),
          page: 1,
        },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelector("#stocks-toggle-order")?.addEventListener("click", () => {
      navigate("/stocks", { query: { ...query, order: orderNext, page: 1 } });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("/stocks", { query: { ...query, page: btn.getAttribute("data-page") } });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });

    host.querySelectorAll("tr[data-code]").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.getAttribute("data-code");
        navigate(`/stocks/${code}`, { query: {} });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });

    host.querySelectorAll("[data-nav]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const path = link.getAttribute("data-path") || "/";
        navigate(path, { query: {} });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
