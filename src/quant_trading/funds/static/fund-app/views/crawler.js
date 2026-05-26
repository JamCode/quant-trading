import { apiGet, escapeHtml } from "../api.js";

const main = () => document.getElementById("app-main");

function badge(status) {
  const s = status || "never";
  return `<span class="badge badge-${escapeHtml(s)}">${escapeHtml(s)}</span>`;
}

export async function mountCrawler() {
  const host = main();
  host.innerHTML = '<p class="loading">加载中…</p>';
  try {
    const tasksData = await apiGet("/crawler/tasks");
    const runsData = await apiGet("/crawler/runs", { limit: 30 });
    let taskRows = "";
    (tasksData.tasks || []).forEach((t) => {
      const last = t.last_run || {};
      taskRows += `<tr>
        <td><code>${escapeHtml(t.task_key)}</code><div class="muted">${escapeHtml(t.title || "")}</div></td>
        <td>${escapeHtml(t.schedule_summary || "")}</td>
        <td>${badge(last.status)}</td>
        <td>${escapeHtml(last.finished_at || last.started_at || "—")}</td>
      </tr>`;
    });
    let runRows = "";
    (runsData.runs || []).forEach((r) => {
      runRows += `<tr>
        <td><code>${escapeHtml(r.task_key)}</code></td>
        <td>${badge(r.status)}</td>
        <td>${escapeHtml(r.started_at || "")}</td>
        <td>${escapeHtml(r.finished_at || "")}</td>
        <td class="muted">${escapeHtml((r.error || "").slice(0, 120))}</td>
      </tr>`;
    });
    host.innerHTML = `<div class="stats">
        <span>最近活动：<strong>${escapeHtml(tasksData.last_activity || "—")}</strong></span>
        <span>运行中：<strong>${tasksData.running_count ?? 0}</strong></span>
      </div>
      <section class="panel"><h2>任务清单</h2>
        <table class="data"><thead><tr><th>任务</th><th>调度</th><th>状态</th><th>时间</th></tr></thead>
        <tbody>${taskRows || '<tr><td colspan="4">无任务</td></tr>'}</tbody></table>
      </section>
      <section class="panel"><h2>最近运行</h2>
        <table class="data"><thead><tr><th>任务</th><th>状态</th><th>开始</th><th>结束</th><th>错误</th></tr></thead>
        <tbody>${runRows || '<tr><td colspan="5">无记录</td></tr>'}</tbody></table>
      </section>`;
  } catch (err) {
    host.innerHTML = `<div class="banner-error">加载失败：${escapeHtml(err.message)}</div>`;
  }
}
