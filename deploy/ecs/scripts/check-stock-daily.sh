#!/bin/bash
set -euo pipefail
runuser -l wanghan -c 'cd /home/wanghan/quant-trading && set -a && source deploy/ecs/fund-stack.env && set +a && source ~/miniconda3/etc/profile.d/conda.sh && conda activate quant && python3 << "PY"
from datetime import datetime
from zoneinfo import ZoneInfo
import pymysql.cursors
from fund_platform.db import get_engine

cn = ZoneInfo("Asia/Shanghai")
print("server_now_cn", datetime.now(cn).strftime("%Y-%m-%d %H:%M %a"))
cur = get_engine().raw_connection().cursor(pymysql.cursors.DictCursor)
cur.execute(
    """
    SELECT id, status, started_at, finished_at, LEFT(error, 100) AS err
    FROM crawler_job_runs WHERE task_key=%s
    ORDER BY id DESC LIMIT 6
    """,
    ("stock_daily_sync",),
)
print("\nstock_daily_sync runs:")
for r in cur.fetchall():
    print(r)
cur.execute(
    """
    SELECT id, trade_date, ok, row_count, started_at, finished_at
    FROM stock_daily_jobs ORDER BY id DESC LIMIT 5
    """
)
print("\nstock_daily_jobs:")
for r in cur.fetchall():
    print(r)
cur.execute(
    "SELECT trade_date, COUNT(*) c FROM stock_daily GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5"
)
print("\nstock_daily row counts:")
for r in cur.fetchall():
    print(r)
PY'
