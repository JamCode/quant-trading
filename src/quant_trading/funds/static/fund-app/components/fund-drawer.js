import { apiGet, escapeHtml, fmtPct, pctClass, pctClassNum } from "../api.js";
import { openDrawer, setDrawerBody, setDrawerLoading } from "./drawer.js";

function dlRow(label, value) {
  const v = value === null || value === undefined || value === "" ? "—" : String(value);
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(v)}</dd>`;
}

function section(title, inner) {
  return `<section class="panel"><h2>${escapeHtml(title)}</h2>${inner}</section>`;
}

function errorBlock(msg) {
  return `<p class="banner-error">${escapeHtml(msg)}</p>`;
}

function navTable(items) {
  if (!items?.length) {
    return '<p class="meta">暂无历史净值。</p>';
  }
  let rows = "";
  items.slice(0, 60).forEach((r) => {
    rows += `<tr>
      <td>${escapeHtml(r.nav_date || "")}</td>
      <td class="num">${escapeHtml(r.nav_unit ?? "—")}</td>
      <td class="num ${pctClass(r.daily_pct)}">${fmtPct(r.daily_pct)}</td>
    </tr>`;
  });
  return `<div class="drawer-scroll"><table class="data"><colgroup>
    <col style="width:38%" /><col style="width:31%" /><col style="width:31%" />
  </colgroup><thead><tr><th>日期</th><th class="num">单位净值</th><th class="num">日涨跌</th></tr></thead>
  <tbody>${rows}</tbody></table></div>
  <p class="meta">最近 ${Math.min(items.length, 60)} 个交易日（新→旧）。</p>`;
}

function rankTable(items) {
  if (!items?.length) {
    return '<p class="meta">暂无同类排名数据。</p>';
  }
  let rows = "";
  items.slice(0, 40).forEach((r) => {
    rows += `<tr>
      <td>${escapeHtml(r.rank_date || "")}</td>
      <td class="num">${r.rank_in_type ?? "—"}</td>
      <td class="num">${r.rank_total ?? "—"}</td>
    </tr>`;
  });
  return `<div class="drawer-scroll"><table class="data"><colgroup>
    <col style="width:40%" /><col style="width:30%" /><col style="width:30%" />
  </colgroup><thead><tr><th>日期</th><th class="num">同类排名</th><th class="num">全市场</th></tr></thead>
  <tbody>${rows}</tbody></table></div>`;
}

function peersHtml(groups) {
  if (!groups?.length) {
    return '<p class="meta">暂无同类 Top5。</p>';
  }
  let html = "";
  groups.forEach((g) => {
    html += `<p class="meta"><strong>${escapeHtml(g.period_label || "")}</strong></p>`;
    if (!g.peers?.length) {
      return;
    }
    let rows = "";
    g.peers.forEach((p) => {
      rows += `<tr>
        <td class="num">${p.rank_pos ?? "—"}</td>
        <td><code>${escapeHtml(p.peer_code)}</code></td>
        <td>${escapeHtml(p.peer_name || "")}</td>
        <td class="num ${pctClassNum(p.return_pct)}">${p.return_pct != null ? `${Number(p.return_pct).toFixed(2)}%` : "—"}</td>
      </tr>`;
    });
    html += `<div class="drawer-scroll"><table class="data"><thead>
      <tr><th>#</th><th>代码</th><th>简称</th><th class="num">收益</th></tr>
    </thead><tbody>${rows}</tbody></table></div>`;
  });
  return html;
}

function basicHtml(ext) {
  const basic = ext?.basic;
  if (!basic || typeof basic !== "object" || !Object.keys(basic).length) {
    return "";
  }
  let rows = "";
  Object.entries(basic).forEach(([k, v]) => {
    if (v !== null && v !== undefined && String(v).trim() !== "") {
      rows += dlRow(k, v);
    }
  });
  if (!rows) {
    return "";
  }
  return section("基金档案", `<dl class="fund-dl">${rows}</dl>`);
}

function holdingsHtml(ext) {
  const stocks = ext?.holdings?.stocks;
  if (!stocks?.length) {
    return "";
  }
  const keys = Object.keys(stocks[0]).slice(0, 4);
  let head = keys.map((k) => `<th>${escapeHtml(k)}</th>`).join("");
  let rows = "";
  stocks.slice(0, 15).forEach((row) => {
    rows += `<tr>${keys.map((k) => `<td>${escapeHtml(row[k] ?? "—")}</td>`).join("")}</tr>`;
  });
  const q = ext.holdings.stock_quarter ? `报告期 ${ext.holdings.stock_quarter}` : "";
  return section(
    "股票持仓（季报）",
    `<p class="meta">${escapeHtml(q)}</p>
    <div class="drawer-scroll"><table class="data"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`
  );
}

function renderFundBody(fund, ext, navRes, rankRes, peersRes) {
  const name = fund.short_name || fund.code;
  let html = `<p class="meta">${escapeHtml(fund.fund_type || "")} · ${escapeHtml(name)}</p>`;

  html += section(
    "行情快照",
    `<dl class="fund-dl">
      ${dlRow("净值日期", fund.nav_date)}
      ${dlRow("单位净值", fund.nav_unit)}
      ${dlRow("累计净值", fund.nav_acc)}
      ${dlRow("日增长率", fund.daily_pct)}
      ${dlRow("申购", fund.subscribe_status)}
      ${dlRow("赎回", fund.redeem_status)}
    </dl>`
  );

  if (navRes.error) {
    html += section("历史净值", errorBlock(navRes.error));
  } else {
    const src = navRes.data?.source === "cache" ? "MySQL 缓存" : navRes.data?.source || "";
    html += section(
      "历史净值",
      (src ? `<p class="meta">共 ${navRes.data?.total ?? 0} 条 · ${escapeHtml(src)}</p>` : "") +
        navTable(navRes.data?.items)
    );
  }

  if (rankRes.error) {
    html += section("同类排名", errorBlock(rankRes.error));
  } else {
    html += section(
      "同类排名（近三月）",
      `<p class="meta">名次越小越靠前 · 共 ${rankRes.data?.total ?? 0} 条</p>` + rankTable(rankRes.data?.items)
    );
  }

  if (peersRes.error) {
    html += section("同类 Top5", errorBlock(peersRes.error));
  } else {
    html += section("同类 Top5（东财）", peersHtml(peersRes.data?.groups));
  }

  html += basicHtml(ext);
  html += holdingsHtml(ext);

  return html;
}

async function loadOptional(path) {
  try {
    const data = await apiGet(path);
    return { data, error: null };
  } catch (err) {
    const msg =
      err.body?.detail || err.message || "加载失败";
    return { data: null, error: String(msg) };
  }
}

export async function openFundDrawer({ code }) {
  openDrawer({ title: `基金 ${code}`, html: "", wide: true });
  setDrawerLoading();
  try {
    const detail = await apiGet(`/funds/${encodeURIComponent(code)}`);
    const fund = detail.fund || {};
    const ext = detail.extended || {};
    const title = fund.short_name ? `${fund.short_name}（${code}）` : `基金 ${code}`;
    document.getElementById("drawer-title").textContent = title;

    const [navRes, rankRes, peersRes] = await Promise.all([
      loadOptional(`/funds/${encodeURIComponent(code)}/nav-history?limit=60&order=desc`),
      loadOptional(`/funds/${encodeURIComponent(code)}/peer-rank?limit=40&order=desc`),
      loadOptional(`/funds/${encodeURIComponent(code)}/peer-same-type`),
    ]);

    setDrawerBody(renderFundBody(fund, ext, navRes, rankRes, peersRes));
  } catch (err) {
    setDrawerBody(errorBlock(err.message || "加载失败"));
  }
}
