# quant-trading

轻量级**量化交易**项目骨架：数据加载 → 策略信号 → 简单回测。适合在此基础上接真实行情 API、风控与实盘执行。

## 功能

- **策略接口**：实现 `generate_signals(ohlcv)` 返回与价格对齐的信号序列
- **示例策略**：双均线（SMA）交叉
- **回测引擎**：按 bar 回放，手续费/滑点占位，输出权益曲线与基础指标
- **基金目录（可选）**：爬虫服务每日写入 **MySQL**；Web 服务只读查询 + 详情按需抓取 AkShare（雪球档案 / 费率 / 持仓等写入 MySQL `fund_details`）

## 环境

```bash
cd quant-trading
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## 运行示例（合成数据）

```bash
python examples/run_backtest.py
```

## 基金模块架构（MySQL）

```
┌─────────────────┐      INSERT/UPDATE       ┌──────────────────┐
│ fund-crawler    │ ───────────────────────► │ MySQL fund_svc   │
│ (AkShare 抓取)   │       funds / sync_jobs   │ funds            │
└─────────────────┘                          │ sync_jobs        │
                                             │ fund_details     │
┌─────────────────┐      SELECT               └────────▲─────────┘
│ quant-trading-web│ ──────────────────────────────────┘
│ (FastAPI 只读    │      + 详情按需 UPSERT fund_details
│  + AkShare 详情) │
└─────────────────┘
```

1. **建库建表**：在 MySQL 执行 `schema/mysql/001_init.sql`（或使用仓库根目录 `docker-compose.yml` 起本地 MySQL 后再执行）。
2. **公共连接串**（两个进程都要）：`DATABASE_URL`  
   示例：`mysql+pymysql://fund:fundpass@127.0.0.1:3306/fund_svc`
3. **爬虫（每日更新）**

```bash
pip install -e ".[crawler]"
export DATABASE_URL='mysql+pymysql://fund:fundpass@127.0.0.1:3306/fund_svc'
python examples/run_crawler.py
# 或：fund-crawler
```

默认定时任务：每天 **`CRAWLER_CRON_HOUR`（默认 2）** 点、`CRAWLER_CRON_MINUTE`（默认 0）分跑全量名录 + 开放式净值快照；另有行业资金流、股票日线、持仓管道、大盘指数等 cron/interval（见 `fund-stack.env.example`）。

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | SQLAlchemy URL，必须 |
| `FUND_SYNC_INCLUDE_DAILY` | 是否合并 `fund_open_fund_daily_em`（默认 `1`） |
| `CRAWLER_CRON_HOUR` / `CRAWLER_CRON_MINUTE` | 基金名录每日定时（本地时区） |

4. **Web**

```bash
pip install -e ".[web]"
export DATABASE_URL='mysql+pymysql://fund:fundpass@127.0.0.1:3306/fund_svc'
python examples/run_web.py
# 或：quant-trading-web
```

浏览器打开 `http://127.0.0.1:8000/`（**行业仪表盘**）；基金名录在 `/funds`。

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | 与爬虫相同 |
| `FUND_DETAIL_CACHE_HOURS` | 详情扩展信息缓存 TTL（默认 `24`） |
| `FUND_WEB_HOST` / `FUND_WEB_PORT` | 监听地址与端口 |
| `FUND_EXPOSURE_MIN_PCT` | 仪表盘相关基金最低行业暴露%（默认 `10`） |
| `DASHBOARD_DEFAULT_PERIOD` | 首页默认统计区间（默认 `即时`） |

HTTP：`GET /`（仪表盘）、`GET /api/dashboard`、`GET /funds`（目录）、`GET /api/funds`、`GET /funds/{code}`、`GET /stocks`（A 股列表）、`GET /api/stocks`、`GET /api/stocks/{code}`、`GET /api/stocks/{code}/price-history`、`GET /sectors`、`GET /api/sector-fund-flow`、`GET /crawler`（爬虫任务与状态）、`GET /api/crawler/tasks`、`GET /api/crawler/runs` 等。DDL 依次执行 `001`～`017`（`017_stock_price_daily.sql` 为个股日 K 懒加载缓存；`011`/`012` 为爬虫任务表；`008_fund_industry_link.sql` 为行业–基金关联表）。

**行业–基金管道（首跑，在 DDL 008 之后）**：

```bash
export DATABASE_URL='mysql+pymysql://fund:fundpass@127.0.0.1:3306/fund_svc'
python -c "from fund_platform.stock_ths_industry import rebuild_stock_ths_industry; print(rebuild_stock_ths_industry())"
python -c "from fund_platform.fund_holdings_sync import sync_fund_holdings; print(sync_fund_holdings())"
python -c "from fund_platform.fund_exposure import rebuild_fund_industry_exposure; print(rebuild_fund_industry_exposure())"
python -c "from fund_platform.fund_metrics_sync import sync_fund_metrics; print(sync_fund_metrics())"
# 或链式：python -c "from fund_platform.fund_holdings_sync import run_fund_industry_pipeline; print(run_fund_industry_pipeline())"
```

爬虫默认定时：名录 `02:00`、全 A `stock_daily` `17:00`（链式东财个股行业补全 → `stock_daily.industry`）、行业资金流 `18:30`（链式成分 + `stock_ths_industry` + 市值）、基金持仓 **`fund_holdings_sync` 周日 `03:00`**、行业映射 **`stock_ths_industry_sync` 每天 `18:35`**、行业暴露 **`fund_industry_exposure_sync` 每天 `19:10`**、收益指标 **`fund_metrics_sync` 每天 `05:00`**（见 `deploy/ecs/fund-stack.env.example`）。DDL 含 `023_stock_daily_industry.sql`、`027_split_fund_holdings_tasks.sql`。

**说明**：全市场名录 + 净值快照由 **爬虫** 负责；详情里用户点进某基金时才会请求 AkShare 并写入 `fund_details`（可与未来「详情预取爬虫」再拆）。

### 阿里云 ECS 部署

与同账号下 **`guitar-ai-coach`** 共用 ECS 约定（公网 **`47.110.78.65`**，用户 **`wanghan`**，SSH 密钥登录）。详见本项目 **`deploy/ecs/README.md`**（含 `push-and-setup.sh`、systemd、Nginx 片段）。**不要将 `.pem` 提交到 Git**（已在 `.gitignore` 忽略）。

## 目录说明

| 路径 | 说明 |
|------|------|
| `deploy/ecs/` | 阿里云推送脚本、systemd、环境变量示例 |
| `schema/mysql/` | MySQL 表结构 DDL |
| `src/fund_platform/` | 共享：MySQL 访问、爬虫同步、详情缓存、持仓抓取 |
| `src/quant_trading/` | 回测骨架 + `funds` Web UI |
| `examples/` | 可执行示例 |
| `data/raw/` | 放置 CSV 等本地行情（默认 gitignore） |

## 下一步建议

1. 在 `quant_trading/data/` 中接入券商 / 聚合行情 API，统一成 OHLCV DataFrame  
2. 在 `strategies/` 增加因子与仓位管理（仓位上限、止损等）  
3. 将 `BacktestEngine` 替换或封装为向量回测（如 polars / numba）以提速  

## 许可

MIT
