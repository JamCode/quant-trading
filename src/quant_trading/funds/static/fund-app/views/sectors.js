import { apiGet, escapeHtml, fmtPct, fmtYi, pctClass, pctClassNum } from "../api.js";
import { navigate, setQuery } from "../router.js";
import { openSectorDrawer } from "../components/sector-drawer.js";

const main = () => document.getElementById("app-main");

export async function mountSectors(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/flow");
    const period =
      query.period && meta.period_options?.includes(query.period)
        ? query.period
        : meta.default_period || "即时";
    const trade_date = query.trade_date || "";
    const data = await apiGet("/sector-fund-flow", {
      period,
      trade_date,
      sort: "net_desc",
      limit: 90,
    });
    const periodOpts = (meta.period_options || [])
      .map(
        (p) =>
          `<option value="${escapeHtml(p)}"${p === period ? " selected" : ""}>${escapeHtml(p)}</option>`
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

    let rowsHtml = "";
    (data.items || []).forEach((r) => {
      rowsHtml += `<tr class="clickable" data-industry="${escapeHtml(r.industry)}">
        <td>${escapeHtml(r.industry)}</td>
        <td class="num ${pctClassNum(r.net_amt)}">${fmtYi(r.net_amt)}</td>
        <td class="num">${r.float_market_cap != null ? fmtYi(r.float_market_cap) : '<span class="meta" title="需运行行业流通市值同步">—</span>'}</td>
        <td class="num ${pctClass(r.change_pct)}">${escapeHtml(r.change_pct || "—")}</td>
        <td>${escapeHtml(r.leader_stock || "—")}</td>
      </tr>`;
    });
    if (!rowsHtml) {
      rowsHtml = '<tr><td colspan="5">暂无数据</td></tr>';
    }

    const dr = data.date_range || {};
    let rangeMeta = `数据日 <strong>${escapeHtml(data.trade_date || "—")}</strong>`;
    if (dr.start_date && dr.end_date && dr.start_date !== dr.end_date) {
      rangeMeta = `累计 <strong>${dr.start_date}</strong> ～ <strong>${dr.end_date}</strong>（${dr.days_actual || "—"} 个交易日）`;
    } else if (dr.start_date) {
      rangeMeta = `数据日 <strong>${escapeHtml(dr.end_date || data.trade_date || "—")}</strong>`;
    }

    host.innerHTML = `<p class="sub meta">同花顺行业主力资金 · 近N日累计=库内每日「即时」快照加总 · 流通市值来自成分股 JOIN</p>
      <form class="toolbar" id="sectors-form">
        <label><span>统计区间</span><select name="period">${periodOpts}</select></label>
        <label><span>截止日</span><select name="trade_date">${dateOpts}</select></label>
        <button type="submit">刷新</button>
      </form>
      <p class="meta">${rangeMeta} · 区间 <strong>${escapeHtml(period)}</strong> · 共 ${(data.items || []).length} 个行业</p>
      <section class="panel">
        <table class="data cols-sector-5"><colgroup><col /><col /><col /><col /><col /></colgroup>
          <thead><tr>
          <th>行业</th><th class="num">净额(亿)</th><th class="num">流通市值(亿)</th><th class="num">涨跌</th><th>领涨股</th>
        </tr></thead><tbody>${rowsHtml}</tbody></table>
      </section>
      <p class="footnote meta">点击行业行 → 右侧抽屉：资金摘要、近几日净流入走势、成分股列表（可点代码进 A 股详情）。</p>`;

    host.querySelector("#sectors-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      navigate("/sectors", {
        query: { period: fd.get("period"), trade_date: fd.get("trade_date") },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelectorAll("tr[data-industry]").forEach((row) => {
      row.addEventListener("click", () => {
        const industry = row.getAttribute("data-industry");
        setQuery({
          drawer: "sector",
          industry,
          period,
          trade_date: data.trade_date || trade_date,
        });
        openSectorDrawer({
          industry,
          period,
          trade_date: data.trade_date || trade_date,
        });
      });
    });
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
