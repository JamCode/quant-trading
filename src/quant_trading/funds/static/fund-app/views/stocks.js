import { apiGet, escapeHtml, fmtPct, fmtYi, pctClassNum } from "../api.js";
import { navigate } from "../router.js";

const main = () => document.getElementById("app-main");

const SORTABLE_COLUMNS = [
  { id: "code", label: "代码", className: "" },
  { id: "name", label: "名称", className: "" },
  { id: "price", label: "现价", className: "num" },
  { id: "change_pct", label: "涨跌幅", className: "num" },
  { id: "float_market_cap", label: "流通市值(亿)", className: "num" },
  { id: "turnover_pct", label: "换手%", className: "num" },
  { id: "amount", label: "成交额(亿)", className: "num" },
  { id: "pe_dynamic", label: "PE", className: "num" },
  { id: "pb", label: "PB", className: "num" },
  { id: "change_60d_pct", label: "60日", className: "num" },
  { id: "change_ytd_pct", label: "年初至今", className: "num" },
];

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

function stocksQueryParams(query, pageOverride) {
  const params = {
    trade_date: query.trade_date || "",
    q: query.q || "",
    sort: query.sort || "change_pct",
    order: query.order || "desc",
    page: pageOverride ?? query.page ?? 1,
    per_page: query.per_page || 50,
  };
  if (query.board) {
    params.board = query.board;
  }
  if (query.industry) {
    params.industry = query.industry;
  }
  return params;
}

function applyStocksFilter(query, patch) {
  const next = { ...query, ...patch, page: 1 };
  if (!next.board) {
    delete next.board;
  }
  if (!next.industry) {
    delete next.industry;
  }
  if (!next.q) {
    delete next.q;
  }
  navigate("/stocks", { query: next });
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function renderBoardChips(options, activeBoard) {
  return (options || [])
    .map((o) => {
      const active = (o.id || "") === (activeBoard || "") ? " active" : "";
      return `<button type="button" class="chip${active}" data-board="${escapeHtml(o.id)}">${escapeHtml(o.label)}</button>`;
    })
    .join("");
}

function renderSortableHead(sort, order) {
  return SORTABLE_COLUMNS.map((col) => {
    const active = col.id === sort;
    const arrow = active ? (order === "asc" ? " ↑" : " ↓") : "";
    const cls = ["sortable", col.className, active ? "sort-active" : ""].filter(Boolean).join(" ");
    return `<th class="${cls}" data-sort="${escapeHtml(col.id)}" scope="col" title="点击排序">${escapeHtml(col.label)}${arrow}</th>`;
  }).join("");
}

function buildFilterSummary(query, meta) {
  const parts = [];
  if (query.board) {
    const label = (meta.board_options || []).find((o) => o.id === query.board)?.label;
    parts.push(label || query.board);
  }
  if (query.industry) {
    parts.push(query.industry);
  }
  if (query.q) {
    parts.push(`「${query.q}」`);
  }
  const sortLabel = (meta.sort_options || []).find((o) => o.id === (query.sort || "change_pct"))?.label;
  if (sortLabel) {
    parts.push(`排序 ${sortLabel}${query.order === "asc" ? "↑" : "↓"}`);
  }
  return parts;
}

export async function mountStocks(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const tradeDatePref = query.trade_date || "";
    const meta = await apiGet("/meta/stocks", tradeDatePref ? { trade_date: tradeDatePref } : {});
    const page = Number(query.page || 1);
    const tradeDate = tradeDatePref || meta.latest_trade_date || "";
    const sort = query.sort || "change_pct";
    const order = query.order || "desc";
    const activeBoard = query.board || "";
    const activeIndustry = query.industry || "";
    const data = await apiGet("/stocks", stocksQueryParams({ ...query, trade_date: tradeDate }, page));

    const dateOpts =
      (meta.trade_dates || []).map((d) => {
        const sel = d === (data.trade_date || tradeDate) ? " selected" : "";
        return `<option value="${escapeHtml(d)}"${sel}>${escapeHtml(d)}</option>`;
      }).join("") ||
      (data.trade_date
        ? `<option value="${escapeHtml(data.trade_date)}" selected>${escapeHtml(data.trade_date)}</option>`
        : "");

    const industryOpts =
      '<option value="">不限行业</option>' +
      (meta.industry_options || [])
        .map((ind) => {
          const sel = ind === activeIndustry ? " selected" : "";
          return `<option value="${escapeHtml(ind)}"${sel}>${escapeHtml(ind)}</option>`;
        })
        .join("");

    const perPage = Number(query.per_page || 50);
    const perPageOpts = [20, 50, 100, 200]
      .map(
        (n) =>
          `<option value="${n}"${n === perPage ? " selected" : ""}>${n}</option>`
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
        ? "无匹配股票，可放宽筛选或<a href=\"#\" data-stocks-clear>清空条件</a>"
        : '暂无数据，请确认 <a href="#" data-nav data-path="/crawler">stock_daily_sync</a> 已运行';
      rows = `<tr><td colspan="11">${hint}</td></tr>`;
    }

    const filterParts = buildFilterSummary(query, meta);
    const filterHint = filterParts.length
      ? `当前：${filterParts.join(" · ")}`
      : "点击板块标签筛选；表头点击排序";

    host.innerHTML = `<p class="sub meta">数据日 <strong>${escapeHtml(data.trade_date || "—")}</strong> · 共 ${data.total ?? 0} 只 · 第 ${data.page}/${data.pages} 页</p>
      <div class="funds-filters panel stocks-filters">
        <p class="dim">板块</p>
        <div class="chip-group" id="stocks-board-chips">${renderBoardChips(meta.board_options, activeBoard)}</div>
        <p class="meta funds-filter-hint">${escapeHtml(filterHint)}</p>
      </div>
      <form class="toolbar" id="stocks-form">
        <label><span>数据日</span><select name="trade_date">${dateOpts}</select></label>
        <label><span>搜索</span><input type="search" name="q" value="${escapeHtml(query.q || "")}" placeholder="代码/名称" /></label>
        <label><span>行业</span><select name="industry">${industryOpts}</select></label>
        <label><span>每页</span><select name="per_page">${perPageOpts}</select></label>
        <button type="submit">应用</button>
        <a class="btn secondary" href="#" id="stocks-clear">清空</a>
      </form>
      <section class="panel table-scroll">
        <table class="data stocks-table"><thead><tr>
          ${renderSortableHead(sort, order)}
        </tr></thead><tbody>${rows}</tbody></table>
      </section>
      <div class="toolbar">
        ${data.page > 1 ? `<button type="button" data-page="${data.page - 1}">上一页</button>` : ""}
        ${data.page < data.pages ? `<button type="button" data-page="${data.page + 1}">下一页</button>` : ""}
      </div>`;

    host.querySelectorAll("[data-board]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-board") || "";
        const next = id === activeBoard ? "" : id;
        applyStocksFilter(query, { board: next });
      });
    });

    host.querySelector("#stocks-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      applyStocksFilter(query, {
        trade_date: fd.get("trade_date"),
        q: fd.get("q"),
        industry: fd.get("industry"),
        per_page: fd.get("per_page"),
      });
    });

    const clearFilters = (event) => {
      if (event) {
        event.preventDefault();
      }
      navigate("/stocks", {
        query: {
          trade_date: data.trade_date || tradeDate,
          sort: "change_pct",
          order: "desc",
          per_page: 50,
        },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    };

    host.querySelector("#stocks-clear")?.addEventListener("click", clearFilters);
    host.querySelector("[data-stocks-clear]")?.addEventListener("click", clearFilters);

    host.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const col = th.getAttribute("data-sort");
        if (!col) {
          return;
        }
        const nextOrder = col === sort && order === "desc" ? "asc" : "desc";
        applyStocksFilter(query, { sort: col, order: nextOrder });
      });
    });

    host.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("/stocks", {
          query: stocksQueryParams(query, btn.getAttribute("data-page")),
        });
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
