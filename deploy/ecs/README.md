# 阿里云 ECS — quant-trading 基金栈（Web + 爬虫 + MySQL）

与 **`guitar-ai-coach`** 使用同一套 ECS 约定（见该仓库 `deploy/ecs/README.md`）。以下为**可公开的默认约定**，密码与私钥勿写入 Git。

## 默认服务器参数（与 guitar-ai-coach 对齐）

| 项 | 默认值 |
|----|--------|
| ECS 公网 IP | `47.110.78.65` |
| SSH 用户 | `wanghan` |
| 本仓库在 ECS 上的路径 | `/home/wanghan/quant-trading` |
| SSH 私钥 | 本机安全路径下的 `.pem`（你已在 **`quant-trading` 根目录**放了一份私钥时，可用该路径导出 `ECS_KEY`） |

首次在本机终端：

```bash
export ECS_HOST=47.110.78.65
export ECS_USER=wanghan
export ECS_KEY="$HOME/Documents/quant-trading/my-ecs-key2.pem"   # 按实际路径修改
chmod 600 "$ECS_KEY"
export ECS_PORT=2222   # sshd 已监听 2222；须在阿里云安全组放行 TCP 2222
```

本机 SSH 别名：`ecs47-wanghan`（2222）、过渡用 `ecs47-wanghan-22`（22）。安全组未放行 2222 前：`ssh ecs47-wanghan-22`。

## MySQL（推荐：沿用 ECS 本机已有 MySQL）

吉他项目在 ECS 上使用 **`MYSQL_HOST=localhost`**（见 `guitar-ai-coach/deploy/ecs/backend.env`）。基金栈建议使用**独立库名** `fund_svc`，避免与吉他业务库混表。

1. **上传 DDL**（任选其一）：
   - 将本仓库同步到 ECS 后，在服务器按序执行 `schema/mysql/001_init.sql` … `008_fund_industry_link.sql`（行业仪表盘依赖 **008**）。
   - 示例：`for f in /home/wanghan/quant-trading/schema/mysql/*.sql; do mysql -u root -p fund_svc < "$f"; done`
2. **创建应用账号**（示例，密码自行替换）：

```sql
CREATE USER IF NOT EXISTS 'fund_app'@'localhost' IDENTIFIED BY '强密码';
GRANT ALL PRIVILEGES ON fund_svc.* TO 'fund_app'@'localhost';
FLUSH PRIVILEGES;
```

3. 在 ECS 复制环境文件并填写 **`DATABASE_URL`**：

```bash
cp deploy/ecs/fund-stack.env.example deploy/ecs/fund-stack.env
# 编辑 deploy/ecs/fund-stack.env，勿提交 Git
```

示例：

```
DATABASE_URL=mysql+pymysql://fund_app:你的密码@127.0.0.1:3306/fund_svc
```

## 云助手 + 阿里云 CLI（本机 SSH 不可用时）

经 **OpenAPI** 在 ECS 内执行命令，不经过本机 `22/2222` SSH。适合公司 WiFi 掐 SSH、但仍能访问阿里云 API 的场景。

### 一次性配置

```bash
# 1) 安装 CLI
./deploy/ecs/install-aliyun-cli.sh

# 2) 配置 AccessKey（RAM 子账号，勿提交 Git）
aliyun configure

# 3) 环境文件
cp deploy/ecs/cloud-assistant.env.example deploy/ecs/cloud-assistant.env
# 编辑地域；实例 ID 可留空（按公网 IP 自动查）
```

控制台确认实例 **云助手 → 运行中**。RAM 用户至少需：`ecs:RunCommand`、`ecs:DescribeInvocations`、`ecs:DescribeInvocationResults`、`ecs:DescribeInstances`（建议按实例 ID 收紧，见阿里云 RAM 文档）。

### 日常命令

```bash
# 首次：在 ECS 上 git clone（若还没有仓库）
./deploy/ecs/cloud-assistant-bootstrap-git.sh

# 部署：git pull + pip + 重启 fund 服务
./deploy/ecs/cloud-assistant-deploy.sh

# 任意命令（root）
./deploy/ecs/cloud-assistant-run.sh 'systemctl --user -u wanghan status quant-trading-fund-web.service || true'
```

与 **GitHub Actions** 可并存：Actions 用 rsync 全量同步；云助手适合 `git pull` 已 clone 的仓库。

## GitHub Actions 自动部署（推荐：本机 WiFi 封 SSH 时）

`push` 到 **`main`** 且变更 `src/`、`deploy/ecs/`、`pyproject.toml`、`schema/mysql/` 时，运行 [`.github/workflows/ecs-quant-deploy.yml`](../../.github/workflows/ecs-quant-deploy.yml)。

**一次性配置**（仓库 **Settings → Secrets and variables → Actions**）：

| 类型 | 名称 | 说明 |
|------|------|------|
| Secret | `ECS_SSH_PRIVATE_KEY` | `my-ecs-key2.pem` **全文**（与吉他仓库可复用同一把钥） |
| Variable | `ECS_HOST` | 可选，默认 `47.110.78.65` |
| Variable | `ECS_PORT` | 可选，默认 `2222` |

本机只需 `git push`；Runner 经 SSH 执行 `deploy/ecs/github-actions-deploy.sh`（等同 `push-and-setup` + 重启 systemd）。也可在 Actions 页 **Run workflow** 手动触发。

## 一键部署（本机 SSH 可达时）

```bash
ECS_KEY="$HOME/Documents/quant-trading/my-ecs-key2.pem" ./deploy/ecs/deploy-remote.sh
```

顺序：`rsync` → **root** 启动 `mysqld`、建库 `fund_svc`、写 `fund-stack.env` → **wanghan** 启 systemd + 补丁 Nginx。  
依赖装在 **`~/miniconda3/envs/quant`**（ECS 系统 Python 3.6 过旧）。

仅同步代码与依赖：

```bash
ECS_KEY="$HOME/Documents/quant-trading/my-ecs-key2.pem" ./deploy/ecs/push-and-setup.sh
```

## systemd（推荐：`wanghan` 用户级服务）

脚本会将单元安装到 `~/.config/systemd/user/`。首次建议开启 lingering（注销后仍跑爬虫定时）：

```bash
sudo loginctl enable-linger wanghan
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now quant-trading-fund-web.service
systemctl --user enable --now quant-trading-fund-crawler.service
systemctl --user status quant-trading-fund-web.service
curl -sS http://127.0.0.1:8010/health
```

- **Web**：默认监听 **`8010`**（避开吉他栈 chord ONNX 常用 `8000`）。
- **爬虫**：进程内 APScheduler，默认每日 **`CRAWLER_CRON_HOUR`**（默认 2）点跑全量同步；行业资金流 **18:30**；基金持仓+暴露管道 **周日 03:00**；**大盘指数** 交易日每 **5 分钟** 快照、A 股日 K **17:00** 写入（`MARKET_INDEX_DAILY_*`）。详见 `fund-stack.env.example`。

### 爬虫日志（排障）

| 项 | 默认（ECS） |
|----|-------------|
| 目录 | `CRAWLER_LOG_DIR`，示例 `/home/wanghan/quant-trading/logs/crawler` |
| 主文件 | `crawler.log`（`RotatingFileHandler`，约 5×10MB 轮转） |
| 同时输出 | stderr → `journalctl --user -u quant-trading-fund-crawler.service` |

每条定时任务在日志中有 `job start id=…` / `job end id=…`；业务失败见 `… failed:`；未捕获异常带完整 traceback。任务 id 与 APScheduler 一致，例如 `fund_mysql_daily_sync`、`stock_daily_sync`、`sector_fund_flow_daily`、`fund_holdings_pipeline`、`market_index_intraday`、`market_index_daily_cn` 等（仅 cron/interval，无启动一次性任务）。

```bash
# 最近 200 行文件日志
tail -n 200 /home/wanghan/quant-trading/logs/crawler/crawler.log

# 仅看某任务
grep 'job start id=sector_fund_flow' /home/wanghan/quant-trading/logs/crawler/crawler.log

# systemd 标准输出（与文件内容相同格式）
journalctl --user -u quant-trading-fund-crawler.service -n 100 --no-pager
```

**行业仪表盘首跑**（008 已执行、名录已有数据后，在 ECS 激活 conda 环境）：

```bash
cd /home/wanghan/quant-trading && source ~/miniconda3/etc/profile.d/conda.sh && conda activate quant
set -a && source deploy/ecs/fund-stack.env && set +a
python -c "from fund_platform.fund_holdings_sync import run_fund_industry_pipeline; print(run_fund_industry_pipeline())"
```

验证：`SELECT industry, COUNT(*) FROM fund_industry_exposure WHERE weight_pct>=10 GROUP BY industry LIMIT 5;`  
打开 `https://你的域名/quant-funds/`（或 `curl -sS http://127.0.0.1:8010/`）为**单页应用**入口（左侧导航 + 行业/基金抽屉）。旧书签 `/quant-funds/sectors/某行业`、`/quant-funds/funds/代码` 会自动重定向并打开抽屉。

**基金 AI 助手**（提示词生成 + 粘贴解析）：`https://你的域名/quant-funds/advisor`（本机调试：`http://127.0.0.1:8010/advisor`）。

**大盘指数日 K 历史初始化**（009 表已建、环境变量与 `MARKET_INDEX_*` 一致后）：

```bash
cd ~/quant-trading && source ~/miniconda3/etc/profile.d/conda.sh && conda activate quant
set -a && source deploy/ecs/fund-stack.env && set +a
# 默认回填约 730 天；MARKET_INDEX_BACKFILL_DAYS=0 表示接口能拉到的全部历史
python -c "from fund_platform.market_index import backfill_market_index_daily; import json; print(json.dumps(backfill_market_index_daily(), ensure_ascii=False, indent=2))"

# 仅补失败的海外/港股（分页拉取，勿用超大 lmt）
python -c "from fund_platform.market_index import backfill_market_index_daily; import json; print(json.dumps(backfill_market_index_daily(skip_cn=True, only_global_names=['纳斯达克','道琼斯','日经225','恒生指数']), ensure_ascii=False, indent=2))"
```

验证：`SELECT code, COUNT(*) c, MIN(trade_date), MAX(trade_date) FROM market_index_daily GROUP BY code;`

**A 股指数全历史 + 成交额（一次性，限速防封）** — 先新浪 OHLCV、再补成交额（东财优先，ECS 上东财常被限流时用**腾讯**补齐 1990 年起历史），支持断点续跑：

```bash
set -a && source deploy/ecs/fund-stack.env && set +a
python examples/backfill_cn_index_full_history.py --dry-run   # 仅看能拉多少条
python examples/backfill_cn_index_full_history.py             # 正式写入（约 15–25 分钟）
# 仅补成交额（不覆盖已有东财成交额，只填 NULL/0）：
python examples/backfill_cn_index_full_history.py --phase amount --reset-amount --no-resume --gap-em 8
python examples/backfill_cn_index_amount.py   # 同上逻辑的轻量入口
```

验证成交额是否铺满：`SELECT code, MIN(trade_date) AS first_amt FROM market_index_daily WHERE amount>0 GROUP BY code;` 应与该指数最早 K 线日期一致（如 000001 → 1990-12-19）。

**策略回测（SPA）** — 侧边栏「策略回测」或路径 `/backtest`：选 A 股指数 + 已注册策略参数，同步回测。新策略在 `src/quant_trading/strategies/registry.py` 注册后部署即可。

可调：`--gap-sina 8 --gap-em 25 --jitter 4 --gap-between-phases 120 --em-attempts 6`

## Nginx 反代（可选）

将 `deploy/ecs/nginx-location-snippet.conf` 合并进现有站点配置（例如吉他项目的 `guitar-server.conf`），对外路径可按域名调整；改完后 **`nginx -t && reload`**。

OpenClaw Control UI（本机 Gateway `127.0.0.1:18789`，需在 `~/.openclaw/openclaw.json` 设置 `gateway.controlUi.basePath: "/openclaw"`）：

- 片段：`deploy/ecs/nginx-openclaw-snippet.conf` → 对外 `https://wanghanai.xyz/openclaw/`
- 访问：页面 `https://wanghanai.xyz/openclaw/#token=<TOKEN>`（`#token` 比 `?token` 更安全）；WebSocket 填 **`wss://wanghanai.xyz/__openclaw__/ws`**（不是 `/openclaw`）
- token 在 ECS：`python3 -c 'import json; print(json.load(open("/home/wanghan/.openclaw/openclaw.json"))["gateway"]["auth"]["token"])'`

## 防火墙与安全组

若仅本机 Nginx 反代：安全组可不对外开放 `8010`，只保留 `80/443`。若临时调试可放行你的 IP。

## 私钥与 Git

**不要将 `.pem` 提交到仓库**。本仓库 `.gitignore` 已忽略 `*.pem`。
