# 爬虫任务监控（Web）— 设计说明

**日期：** 2026-05-22  
**状态：** 已批准（方案 C）  
**路由：** `/crawler`  
**导航名称：** 爬虫任务

## 概述

在 Web 上展示爬虫定时任务清单、最近一次/当前执行状态，以及执行历史。爬虫与 Web 为独立进程；**所有状态以 MySQL 为准**，Web 只读数据库，不读日志、不查 systemd。

采用 **统一运行表 + 保留领域 `*_jobs` 表**（方案 C）：在 APScheduler 的 `_scheduled` 包装层写入 `crawler_job_runs`；业务同步逻辑继续写 `sync_jobs`、`stock_daily_jobs` 等，并通过 `detail_json` 关联。

## 目标

- **任务清单：** 系统配置了哪些爬虫任务、调度规则、是否启用（由 env 决定）。
- **执行状态：** 每个任务最近一次结果（成功 / 失败 / 运行中 / 跳过 / 从未运行）。
- **执行历史：** 全局及按任务筛选的 `crawler_job_runs` 列表。
- **进行中：** `status = running` 且 `finished_at IS NULL` 的记录高亮。
- **爬虫活跃度：** 全表 `MAX(started_at)` 作为「最近活动」时间（不单独做进程心跳表）。

## 明确不做

- Web 触发/停止爬虫任务（无手动 run API）。
- 读取 `crawler.log` 或 ECS systemd 状态。
- 将历史 `sync_jobs` 等旧表数据迁移到 `crawler_job_runs`。
- 用户认证、权限（与现有基金 Web 一致，内网/个人使用）。
- v1 不做「卡住超时自动标 failed」的后台巡检（仅 UI 展示 `running` 时长，文案提示可能卡住）。

## 数据模型

### 迁移文件

`schema/mysql/011_crawler_jobs.sql`

### 表 `crawler_tasks`（任务目录）

| 列 | 类型 | 说明 |
|----|------|------|
| `task_key` | VARCHAR(64) PK | 与 APScheduler `id` 一致 |
| `display_name` | VARCHAR(128) | 中文展示名 |
| `schedule_kind` | VARCHAR(16) | `cron` \| `interval` \| `once` |
| `schedule_summary` | VARCHAR(256) | 人类可读调度，如「每天 02:00」「每 15 分钟」 |
| `enabled` | TINYINT(1) | 当前配置下是否注册到 scheduler |
| `sort_order` | SMALLINT | 页面排序 |

迁移脚本 **seed** 全部 `task_key`（见下表）；爬虫进程启动时 **UPSERT** `schedule_summary` 与 `enabled`，使文案与 `settings.py` / env 一致。

### 表 `crawler_job_runs`（每次调度执行）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | BIGINT PK AI | |
| `task_key` | VARCHAR(64) | 索引 `(task_key, started_at)` |
| `status` | VARCHAR(16) | `running` \| `success` \| `failed` \| `skipped` |
| `started_at` | DATETIME(3) | UTC |
| `finished_at` | DATETIME(3) NULL | UTC |
| `error` | TEXT NULL | 失败摘要（截断 4000 字符） |
| `detail_json` | JSON NULL | 业务指标与旧表关联 |

**状态流转：** `running` →（正常结束）`success` / `failed`；（业务 skip）`skipped`。

**`detail_json` 约定（可选字段）：**

```json
{
  "row_count": 12345,
  "trade_date": "2026-05-22",
  "legacy_table": "sync_jobs",
  "legacy_id": 45,
  "skipped_reason": "outside trading hours"
}
```

各 `sync_*` 函数返回 dict 时，`_scheduled` 包装层在结束时把 `ok`、`count`/`total_rows`、`job_id`、`trade_date`、`reason` 等映射进 `detail_json`。

### 任务目录 seed（`task_key` → 默认中文名）

| task_key | display_name（默认） | schedule_kind |
|----------|---------------------|---------------|
| `fund_mysql_daily_sync` | 基金名录 + 净值快照 | cron |
| `fund_mysql_startup_sync` | 基金名录（启动一次） | once |
| `stock_daily_sync` | A 股现货日线 | cron |
| `stock_daily_startup` | A 股现货（启动一次） | once |
| `sector_fund_flow_daily` | 行业资金流向 | cron |
| `sector_fund_flow_startup` | 行业资金流（启动一次） | once |
| `fund_holdings_pipeline` | 基金持仓 + 行业暴露 | cron |
| `fund_holdings_startup` | 基金持仓管道（启动一次） | once |
| `market_index_intraday` | 市场指数盘中 | interval |
| `market_index_daily_cn` | 市场指数日收盘（A 股） | cron |
| `market_index_daily_hk` | 市场指数日收盘（港股） | cron |
| `market_index_daily_global` | 市场指数日收盘（全球） | cron |
| `market_index_startup` | 市场指数（启动一次） | once |

`enabled` 规则（启动 UPSERT 时）：

- `*_startup` 类：对应 `CRAWLER_SYNC_ON_STARTUP`、`STOCK_DAILY_ON_STARTUP`、`SECTOR_FLOW_ON_STARTUP`、`FUND_HOLDINGS_ON_STARTUP`、`MARKET_INDEX_ON_STARTUP` 等为真则 `enabled=1`，否则 `0`（任务仍 seed，页面显示「未启用」）。
- 常规定时任务：只要 crawler 进程注册该 job，则 `enabled=1`。

### 领域表（保留，不改动写入逻辑）

- `sync_jobs`、`stock_daily_jobs`、`sector_flow_jobs`、`fund_holdings_jobs` 继续由现有 `sync_*` 写入。
- 不在 v1 为 `market_index` 新增单独 `market_index_jobs` 表；指数任务仅以 `crawler_job_runs` 为准。

## 爬虫侧改动

### 新模块 `fund_platform/crawler_jobs.py`

- `upsert_task_catalog()` — 根据 `settings` 生成 `schedule_summary`，UPSERT `crawler_tasks`。
- `begin_run(task_key) -> run_id` — INSERT `crawler_job_runs` status=`running`。
- `finish_run(run_id, *, status, error=None, detail=None)` — UPDATE `finished_at`、status、error、detail_json。
- `map_result_to_detail(result: dict) -> dict` — 从各 job 返回的 dict 提取 `detail_json` 与 success/failed/skipped。

### 修改 `crawler_cli.py`

1. `main()` 在 `scheduler.start()` 之前调用 `upsert_task_catalog()`。
2. 重写 `_scheduled(job_id, fn)`：
   - 开始：`run_id = begin_run(job_id)`
   - 调用 `fn()`；各 `_run_*` 改为 **返回** `dict`（与底层 `sync_*` 一致），不再只打日志。
   - 结束：根据返回值 `finish_run`；未捕获异常 → `failed` + traceback 写入 `error`。
   - `skipped`：返回值含 `skipped: true`（如 market index intraday）。

### 与领域 `job_id` 关联

各 `sync_*` 返回体已含 `job_id` 时，`map_result_to_detail` 填入 `legacy_table` / `legacy_id`（表名按任务类型映射）。

## Web 侧改动

### 查询 `fund_platform/crawler_queries.py`

- `list_tasks_with_latest_run(conn)` — JOIN `crawler_tasks` 与每个 `task_key` 最新一条 `crawler_job_runs`（含从未运行）。
- `list_runs(conn, *, task_key=None, status=None, limit=50, offset=0)` — 历史分页。
- `crawler_last_activity(conn)` — `MAX(started_at)` 全表。
- `count_running(conn)` — 当前 `running` 条数。

### 路由（`quant_trading/funds/app.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/crawler` | HTML 页面 |
| GET | `/api/crawler/tasks` | 任务清单 + 最近状态 |
| GET | `/api/crawler/runs` | 查询参数：`task_key`、`status`、`limit`（默认 50，最大 200） |

### 页面 `templates/crawler.html`

- 继承/复用 `_fund_theme.html` 或 dashboard 表格样式。
- **顶栏摘要：** 最近活动时间、当前运行中任务数。
- **任务表：** 名称、调度、启用、最近状态（徽章色）、最近开始/结束、耗时、摘要（行数 / trade_date / 错误首行）。
- **历史表：** 时间倒序，可选下拉筛选 `task_key`；`running` 行背景高亮。
- 空状态：尚无 `crawler_job_runs` 时提示「部署 migration 并启动爬虫后可见记录」。

### 导航

在 `dashboard.html`、`index.html`、`sectors.html` 等 `nav-links` 增加：**爬虫任务** → `{bp}crawler`。

### 清理

- 基金目录 `index.html` 底部「名录同步」一行改为链接「查看爬虫任务 → `/crawler`」；可移除模板对 `last_job` 的依赖（API `/api/sync/status` 可保留兼容）。

## 错误与边界

| 场景 | 行为 |
|------|------|
| 进程崩溃 mid-run | 记录保持 `running`；UI 显示已开始时长 + 提示可能异常退出 |
| 同 task 再次触发而旧 run 仍 `running` | v1 允许并存；任务表「最近状态」取 `started_at` 最大的一条 |
| DB 不可用 | crawler 日志 exception；Web 页 500 或友好错误 |
| `detail_json` 过大 | 仅保留标量字段，错误文本不进 JSON |

## 测试

1. **迁移：** 本地执行 `011_crawler_jobs.sql`。
2. **集成：** 启动 crawler，等待或触发 startup job；查询 `crawler_job_runs` 有 `running`→`success`/`failed`。
3. **API：** `GET /api/crawler/tasks`、`/api/crawler/runs` 结构稳定、时间 UTC 序列化为字符串。
4. **UI：** 打开 `/crawler`，任务表与历史表与 DB 一致。
5. **跳过路径：** market index intraday 在非交易时段返回 skipped 时，run 状态为 `skipped`。

## 部署

- ECS / 本地：在现有 DDL 流程中追加 `011`；先 migration，再部署 crawler + web 代码。
- 无需新 env 变量（调度文案仍来自现有 `CRAWLER_*` 等变量）。

## 实现顺序建议

1. DDL `011` + `crawler_jobs.py`
2. `crawler_cli._scheduled` + `_run_*` 返回值 + 启动 UPSERT
3. `crawler_queries.py` + API + `crawler.html` + 导航
4. 移除/简化 index 页重复 sync 摘要
5. README 补充 `/crawler` 与 migration `011`
