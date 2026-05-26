import { apiBase, escapeHtml } from "../api.js";
import { openFundDrawer } from "../components/fund-drawer.js";
import { setQuery } from "../router.js";

const main = () => document.getElementById("app-main");

export async function mountAdvisor() {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const res = await fetch(`${apiBase()}/advisor/options`);
    const { tag_options: tags } = await res.json();
    const state = { industries: [], fund_types: [], style: "", observation: "" };

    host.innerHTML = `
      <section class="panel"><h2>① 收窄范围</h2>
        <p class="meta">点击标签；不选则生成通用提示词。</p>
        <label class="dim">行业</label>
        <div class="chip-group" data-group="industries">${(tags.industries || [])
          .map((v) => `<button type="button" class="chip" data-value="${escapeHtml(v)}">${escapeHtml(v)}</button>`)
          .join("")}</div>
        <label class="dim">基金类型</label>
        <div class="chip-group" data-group="fund_types">${(tags.fund_types || [])
          .map((v) => `<button type="button" class="chip" data-value="${escapeHtml(v)}">${escapeHtml(v)}</button>`)
          .join("")}</div>
      </section>
      <section class="panel"><h2>② 提示词</h2>
        <textarea id="prompt-preview" style="width:100%;min-height:12rem"></textarea>
        <p id="prompt-status" class="meta"></p>
        <div class="toolbar">
          <button type="button" id="btn-copy">复制</button>
          <button type="button" id="btn-regen">重新生成</button>
        </div>
      </section>
      <section class="panel"><h2>③ 粘贴 AI 回答</h2>
        <textarea id="paste-input" style="width:100%;min-height:8rem" placeholder="粘贴 DeepSeek 回复…"></textarea>
        <button type="button" id="btn-parse">解析基金代码</button>
        <p id="parse-err" class="banner-error" hidden></p>
      </section>
      <section class="panel" id="result-section" hidden>
        <h2>④ 解析结果</h2>
        <table class="data"><thead><tr><th>代码</th><th>名称</th><th></th></tr></thead>
        <tbody id="result-body"></tbody></table>
      </section>`;

    const promptEl = host.querySelector("#prompt-preview");
    const promptStatus = host.querySelector("#prompt-status");

    function buildQuery() {
      const q = new URLSearchParams();
      state.industries.forEach((v) => q.append("industries", v));
      state.fund_types.forEach((v) => q.append("fund_types", v));
      if (state.style) {
        q.set("style", state.style);
      }
      if (state.observation) {
        q.set("observation", state.observation);
      }
      return q.toString();
    }

    async function refreshPrompt() {
      promptStatus.textContent = "更新中…";
      const qs = buildQuery();
      const url = `${apiBase()}/advisor/prompt${qs ? `?${qs}` : ""}`;
      const r = await fetch(url);
      const data = await r.json();
      promptEl.value = data.prompt || "";
      promptStatus.textContent = "已更新";
    }

    host.querySelectorAll(".chip-group").forEach((group) => {
      const key = group.dataset.group;
      group.addEventListener("click", (event) => {
        const btn = event.target.closest(".chip");
        if (!btn) {
          return;
        }
        btn.classList.toggle("active");
        state[key] = Array.from(group.querySelectorAll(".chip.active")).map((b) => b.dataset.value);
        refreshPrompt();
      });
    });

    host.querySelector("#btn-regen")?.addEventListener("click", refreshPrompt);
    host.querySelector("#btn-copy")?.addEventListener("click", async () => {
      await navigator.clipboard.writeText(promptEl.value);
      promptStatus.textContent = "已复制";
    });

    host.querySelector("#btn-parse")?.addEventListener("click", async () => {
      const errEl = host.querySelector("#parse-err");
      errEl.hidden = true;
      const r = await fetch(`${apiBase()}/advisor/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: host.querySelector("#paste-input").value }),
      });
      if (!r.ok) {
        errEl.textContent = "解析失败";
        errEl.hidden = false;
        return;
      }
      const data = await r.json();
      const tbody = host.querySelector("#result-body");
      tbody.innerHTML = "";
      (data.items || []).forEach((item) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><code>${escapeHtml(item.code)}</code></td>
          <td>${escapeHtml(item.name || "")}</td>
          <td><a href="#" data-fund="${escapeHtml(item.code)}">详情</a></td>`;
        tbody.appendChild(tr);
      });
      host.querySelector("#result-section").hidden = false;
      tbody.querySelectorAll("[data-fund]").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const code = link.getAttribute("data-fund");
          setQuery({ drawer: "fund", code });
          openFundDrawer({ code });
        });
      });
    });

    await refreshPrompt();
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
