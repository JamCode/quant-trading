import { apiGet, escapeHtml, pctClass } from "../api.js";
import { navigate, setQuery } from "../router.js";
import { openFundDrawer } from "../components/fund-drawer.js";

const main = () => document.getElementById("app-main");

function fmtAum(r) {
  if (r.aum_label) {
    return r.aum_label;
  }
  if (r.aum_yi != null && r.aum_yi !== "") {
    const n = Number(r.aum_yi);
    if (!Number.isNaN(n)) {
      return `${n.toFixed(2)}亿`;
    }
  }
  return "—";
}

function subscribeOpenActive(query) {
  return query.subscribe_open === "1" || query.subscribe_open === true;
}

function fundsQueryParams(query) {
  const params = {
    q: query.q || "",
    fund_type: query.fund_type || "",
    category: query.category || "",
    industry: query.industry || "",
    sort: query.sort || "code",
    order: query.order || "asc",
    page: query.page || 1,
    per_page: query.per_page || 50,
  };
  if (subscribeOpenActive(query)) {
    params.subscribe_open = 1;
  }
  return params;
}

function applyFundsFilter(query, patch) {
  const next = { ...query, ...patch, page: 1 };
  if (!next.category) {
    delete next.category;
  }
  if (!subscribeOpenActive(next)) {
    delete next.subscribe_open;
  } else {
    next.subscribe_open = "1";
  }
  navigate("/funds", { query: next });
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function renderCategoryChips(options, activeCategory) {
  return (options || [])
    .map((o) => {
      const active = (o.id || "") === (activeCategory || "") ? " active" : "";
      return `<button type="button" class="chip${active}" data-category="${escapeHtml(o.id)}">${escapeHtml(o.label)}</button>`;
    })
    .join("");
}

export async function mountFunds(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/funds");
    const page = Number(query.page || 1);
    const data = await apiGet("/funds", fundsQueryParams({ ...query, page }));

    const sortOpts = (meta.sort_options || [])
      .map(
        (o) =>
          `<option value="${escapeHtml(o.id)}"${o.id === (query.sort || "code") ? " selected" : ""}>${escapeHtml(o.label)}</option>`
      )
      .join("");

    const activeCat = query.category || "";
    const subOpen = subscribeOpenActive(query);
    const filterSummary = [];
    if (activeCat) {
      const label = (meta.category_options || []).find((o) => o.id === activeCat)?.label;
      if (label) {
        filterSummary.push(label);
      }
    }
    if (subOpen) {
      filterSummary.push("可申购");
    }
    const filterHint = filterSummary.length
      ? `筛选：${filterSummary.join(" · ")}`
      : "点击标签筛选；可叠加「可申购」";

    let rows = "";
    (data.items || []).forEach((r) => {
      rows += `<tr class="clickable" data-code="${escapeHtml(r.code)}">
        <td><code>${escapeHtml(r.code)}</code></td>
        <td>${escapeHtml(r.short_name || "")}</td>
        <td>${escapeHtml(r.fund_type || "")}</td>
        <td class="num">${escapeHtml(fmtAum(r))}</td>
        <td class="num ${pctClass(r.daily_pct)}">${escapeHtml(r.daily_pct || "—")}</td>
        <td class="num">${escapeHtml(r.nav_unit || "—")}</td>
      </tr>`;
    });
    if (!rows) {
      rows = '<tr><td colspan="6">无匹配基金</td></tr>';
    }

    host.innerHTML = `<p class="sub meta">共 ${data.total} 只 · 第 ${data.page}/${data.pages} 页</p>
      <div class="funds-filters panel">
        <p class="dim">资产类型</p>
        <div class="chip-group" id="funds-category-chips">${renderCategoryChips(meta.category_options, activeCat)}</div>
        <p class="dim">交易状态</p>
        <div class="chip-group">
          <button type="button" class="chip${subOpen ? " active" : ""}" data-subscribe-toggle>可申购</button>
        </div>
        <p class="meta funds-filter-hint">${escapeHtml(filterHint)}</p>
      </div>
      <form class="toolbar" id="funds-form">
        <label><span>搜索</span><input type="search" name="q" value="${escapeHtml(query.q || "")}" placeholder="代码/名称/拼音" /></label>
        <label><span>排序</span><select name="sort">${sortOpts}</select></label>
        <button type="submit">查询</button>
      </form>
      <section class="panel">
        <table class="data"><colgroup>
          <col style="width:12%" /><col style="width:28%" /><col style="width:18%" />
          <col style="width:14%" /><col style="width:14%" /><col style="width:14%" />
        </colgroup><thead><tr>
          <th>代码</th><th>简称</th><th>类型</th><th class="num">规模</th><th class="num">日涨跌</th><th class="num">净值</th>
        </tr></thead><tbody>${rows}</tbody></table>
      </section>
      <div class="toolbar">
        ${data.page > 1 ? `<button type="button" data-page="${data.page - 1}">上一页</button>` : ""}
        ${data.page < data.pages ? `<button type="button" data-page="${data.page + 1}">下一页</button>` : ""}
      </div>`;

    host.querySelectorAll("[data-category]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-category") || "";
        const next = id === activeCat ? "" : id;
        applyFundsFilter(query, { category: next });
      });
    });

    host.querySelector("[data-subscribe-toggle]")?.addEventListener("click", () => {
      applyFundsFilter(query, { subscribe_open: subOpen ? "" : "1" });
    });

    host.querySelector("#funds-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      applyFundsFilter(query, {
        q: fd.get("q"),
        sort: fd.get("sort"),
      });
    });

    host.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("/funds", {
          query: { ...fundsQueryParams(query), page: btn.getAttribute("data-page") },
        });
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
    });

    host.querySelectorAll("tr[data-code]").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.getAttribute("data-code");
        setQuery({ drawer: "fund", code });
        openFundDrawer({ code });
      });
    });
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
