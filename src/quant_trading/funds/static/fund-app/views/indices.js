import { apiGet, escapeHtml, fmtPct, pctClassNum } from "../api.js";
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

function fmtAmount(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const n = Number(value);
  if (Number.isNaN(n)) {
    return "—";
  }
  if (Math.abs(n) >= 1e8) {
    return `${(n / 1e8).toFixed(2)}亿`;
  }
  if (Math.abs(n) >= 1e4) {
    return `${(n / 1e4).toFixed(2)}万`;
  }
  return n.toFixed(0);
}

function regionLabel(region) {
  const map = { cn: "A 股", hk: "港股", global: "全球" };
  return map[region] || region || "—";
}

export async function mountIndices(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/market-indices");
    const region = query.region || "all";
    const tradeDate = query.trade_date || meta.latest_trade_date || "";
    const data = await apiGet("/market-indices", {
      trade_date: tradeDate,
      region,
    });

    const dateOpts = (meta.trade_dates || [])
      .map((d) => {
        const sel = d === (data.trade_date || tradeDate) ? " selected" : "";
        return `<option value="${escapeHtml(d)}"${sel}>${escapeHtml(d)}</option>`;
      })
      .join("");

    const regionOpts = (meta.region_options || [])
      .map(
        (o) =>
          `<option value="${escapeHtml(o.id)}"${o.id === region ? " selected" : ""}>${escapeHtml(o.label)}</option>`
      )
      .join("");

    let rows = "";
    (data.items || []).forEach((r) => {
      const code = r.code || "";
      rows += `<tr class="clickable" data-code="${escapeHtml(code)}">
        <td><code>${escapeHtml(code)}</code></td>
        <td>${escapeHtml(r.name || "")}</td>
        <td class="muted">${escapeHtml(regionLabel(r.region))}</td>
        <td class="num">${fmtNum(r.close_px)}</td>
        <td class="num ${pctClassNum(r.change_pct)}">${fmtPct(r.change_pct)}</td>
        <td class="num">${fmtNum(r.change_amt)}</td>
        <td class="num">${fmtAmount(r.amount)}</td>
      </tr>`;
    });
    if (!rows) {
      rows =
        '<tr><td colspan="7">暂无指数数据，请确认 <code>market_index_daily_*</code> 爬虫已运行</td></tr>';
    }

    host.innerHTML = `<p class="sub meta">数据日 <strong>${escapeHtml(data.trade_date || "—")}</strong> · 共 ${(data.items || []).length} 只指数 · 日收盘来自 <code>market_index_daily</code></p>
      <form class="toolbar" id="indices-form">
        <label><span>数据日</span><select name="trade_date">${dateOpts}</select></label>
        <label><span>市场</span><select name="region">${regionOpts}</select></label>
        <button type="submit">查询</button>
      </form>
      <section class="panel table-scroll">
        <table class="data"><thead><tr>
          <th>代码</th><th>名称</th><th>市场</th><th class="num">收盘</th>
          <th class="num">涨跌幅</th><th class="num">涨跌额</th><th class="num">成交额</th>
        </tr></thead><tbody>${rows}</tbody></table>
      </section>
      <p class="meta">点击行查看走势</p>`;

    host.querySelector("#indices-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      navigate("/indices", {
        query: {
          trade_date: fd.get("trade_date"),
          region: fd.get("region"),
        },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelectorAll("tr[data-code]").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.getAttribute("data-code");
        navigate(`/indices/${encodeURIComponent(code)}`, {
          query: { trade_date: data.trade_date || tradeDate },
        });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
