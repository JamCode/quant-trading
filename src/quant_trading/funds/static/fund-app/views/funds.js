import { apiGet, escapeHtml, pctClass } from "../api.js";
import { navigate, setQuery } from "../router.js";
import { openFundDrawer } from "../components/fund-drawer.js";

const main = () => document.getElementById("app-main");

export async function mountFunds(query) {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const meta = await apiGet("/meta/funds");
    const page = Number(query.page || 1);
    const data = await apiGet("/funds", {
      q: query.q || "",
      fund_type: query.fund_type || "",
      category: query.category || "",
      industry: query.industry || "",
      sort: query.sort || "code",
      order: query.order || "asc",
      page,
      per_page: query.per_page || 50,
    });
    const catOpts =
      '<option value="">全部类型</option>' +
      (meta.category_options || [])
        .map(
          (o) =>
            `<option value="${escapeHtml(o.id)}"${o.id === (query.category || "") ? " selected" : ""}>${escapeHtml(o.label)}</option>`
        )
        .join("");
    const sortOpts = (meta.sort_options || [])
      .map(
        (o) =>
          `<option value="${escapeHtml(o.id)}"${o.id === (query.sort || "code") ? " selected" : ""}>${escapeHtml(o.label)}</option>`
      )
      .join("");

    let rows = "";
    (data.items || []).forEach((r) => {
      rows += `<tr class="clickable" data-code="${escapeHtml(r.code)}">
        <td><code>${escapeHtml(r.code)}</code></td>
        <td>${escapeHtml(r.short_name || "")}</td>
        <td>${escapeHtml(r.fund_type || "")}</td>
        <td class="num ${pctClass(r.daily_pct)}">${escapeHtml(r.daily_pct || "—")}</td>
        <td class="num">${escapeHtml(r.nav_unit || "—")}</td>
      </tr>`;
    });
    if (!rows) {
      rows = '<tr><td colspan="5">无匹配基金</td></tr>';
    }

    host.innerHTML = `<p class="sub meta">共 ${data.total} 只 · 第 ${data.page}/${data.pages} 页</p>
      <form class="toolbar" id="funds-form">
        <label><span>搜索</span><input type="search" name="q" value="${escapeHtml(query.q || "")}" placeholder="代码/名称" /></label>
        <label><span>分类</span><select name="category">${catOpts}</select></label>
        <label><span>排序</span><select name="sort">${sortOpts}</select></label>
        <button type="submit">查询</button>
      </form>
      <section class="panel">
        <table class="data"><colgroup>
          <col style="width:14%" /><col style="width:32%" /><col style="width:22%" />
          <col style="width:16%" /><col style="width:16%" />
        </colgroup><thead><tr>
          <th>代码</th><th>简称</th><th>类型</th><th class="num">日涨跌</th><th class="num">净值</th>
        </tr></thead><tbody>${rows}</tbody></table>
      </section>
      <div class="toolbar">
        ${data.page > 1 ? `<button type="button" data-page="${data.page - 1}">上一页</button>` : ""}
        ${data.page < data.pages ? `<button type="button" data-page="${data.page + 1}">下一页</button>` : ""}
      </div>`;

    host.querySelector("#funds-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const fd = new FormData(event.target);
      navigate("/funds", {
        query: {
          q: fd.get("q"),
          category: fd.get("category"),
          sort: fd.get("sort"),
          page: 1,
        },
      });
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    host.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigate("/funds", { query: { ...query, page: btn.getAttribute("data-page") } });
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
