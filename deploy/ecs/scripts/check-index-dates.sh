#!/bin/bash
set -euo pipefail
runuser -l wanghan -c 'cd /home/wanghan/quant-trading && set -a && source deploy/ecs/fund-stack.env && set +a && source ~/miniconda3/etc/profile.d/conda.sh && conda activate quant && python3 << "PY"
from datetime import datetime
from zoneinfo import ZoneInfo
from fund_platform.db import get_engine
import pymysql.cursors
cn = ZoneInfo("Asia/Shanghai")
print("server_now_cn", datetime.now(cn).strftime("%Y-%m-%d %H:%M %a"))
cur = get_engine().raw_connection().cursor(pymysql.cursors.DictCursor)
cur.execute("SELECT code, MAX(trade_date) d FROM market_index_daily WHERE LENGTH(code)=6 GROUP BY code ORDER BY code")
print("A-share max date:")
for r in cur.fetchall():
    print(r["code"], r["d"])
cur.execute("SELECT trade_date, close_px, updated_at FROM market_index_daily WHERE code=\"000300\" ORDER BY trade_date DESC LIMIT 3")
print("HS300:", cur.fetchall())
cur.execute("SELECT id, status, started_at, finished_at, error FROM crawler_job_runs WHERE task_key=\"market_index_daily_cn\" ORDER BY id DESC LIMIT 8")
print("cn runs:")
for r in cur.fetchall():
    print(r["id"], r["status"], r["started_at"], r["finished_at"], (r.get("error") or "-")[:80])
PY'
