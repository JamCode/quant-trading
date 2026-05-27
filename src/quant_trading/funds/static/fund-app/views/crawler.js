import { apiGet, escapeHtml } from "../api.js";

const main = () => document.getElementById("app-main");

function badge(status, label) {
  const s = status || "never";
  const text = label || (s === "never" ? "从未运行" : s);
  return `<span class="badge badge-${escapeHtml(s)}">${escapeHtml(text)}</span>`;
}

export async function mountCrawler() {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const tasksData = await apiGet("/crawler/tasks");
    const runsData = await apiGet("/crawler/runs", { limit: 30 });
    let taskRows = "";
    (tasksData.tasks || []).forEach((t) => {
      taskRows += `<tr>
        <td><code>${escapeHtml(t.task_key)}</code><div class="muted">${escapeHtml(t.display_name || "")}</div></td>
        <td>${escapeHtml(t.schedule_summary || t.schedule_kind || "")}</td>
        <td>${badge(t.last_status, t.last_status_label)}</td>
        <td class="num">${escapeHtml(t.last_finished_at || t.last_started_at || "—")}</td>
      </tr>`;
    });
    let runRows = "";
    (runsData.runs || []).forEach((r) => {
      runRows += `<tr>
        <td><code>${escapeHtml(r.task_key)}</code></td>
        <td>${badge(r.status, r.status_label)}</td>
        <td class="num">${escapeHtml(r.started_at || "")}</td>
        <td class="num">${escapeHtml(r.finished_at || "")}</td>
        <td class="muted">${escapeHtml((r.error || "").slice(0, 120))}</td>
      </tr>`;
    });
    host.innerHTML = `<div class="stats">
        <span>最近活动：<strong>${escapeHtml(tasksData.last_activity || "—")}</strong></span>
        <span>运行中：<strong>${tasksData.running_count ?? 0}</strong></span>
      </div>
      <section class="panel"><h2>任务清单</h2>
        <table class="data"><colgroup>
          <col style="width:36%" /><col style="width:28%" /><col style="width:16%" /><col style="width:20%" />
        </colgroup><thead><tr><th>任务</th><th>调度</th><th>状态</th><th class="num">时间</th></tr></thead>
        <tbody>${taskRows || '<tr><td colspan="4">无任务</td></tr>'}</tbody></table>
      </section>
      <section class="panel"><h2>最近运行</h2>
        <table class="data"><colgroup>
          <col style="width:22%" /><col style="width:12%" /><col style="width:18%" /><col style="width:18%" /><col style="width:30%" />
        </colgroup><thead><tr><th>任务</th><th>状态</th><th class="num">开始</th><th class="num">结束</th><th>错误</th></tr></thead>
        <tbody>${runRows || '<tr><td colspan="5">无记录</td></tr>'}</tbody></table>
      </section>`;
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
