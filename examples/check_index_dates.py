#!/usr/bin/env python3
"""One-off: print A-share index latest dates and recent CN crawler runs."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql.cursors

from fund_platform.db import get_engine

cn = ZoneInfo("Asia/Shanghai")
print("server_now_cn", datetime.now(cn).strftime("%Y-%m-%d %H:%M %a"))

cur = get_engine().raw_connection().cursor(pymysql.cursors.DictCursor)
cur.execute(
    """
    SELECT code, MAX(name) AS name, MAX(trade_date) AS last_d, MAX(updated_at) AS updated
    FROM market_index_daily
    WHERE code REGEXP '^[0-9]{6}$'
    GROUP BY code
    ORDER BY code
    """
)
print("\nA-share max trade_date:")
for r in cur.fetchall():
    print(r["code"], r["name"], r["last_d"], r["updated"])

cur.execute(
    """
    SELECT trade_date, close_px, updated_at
    FROM market_index_daily WHERE code='000300'
    ORDER BY trade_date DESC LIMIT 5
    """
)
print("\nHS300 tail:", cur.fetchall())

cur.execute(
    """
    SELECT id, status, started_at, finished_at, error
    FROM crawler_job_runs
    WHERE task_key='market_index_daily_cn'
    ORDER BY id DESC LIMIT 8
    """
)
print("\nmarket_index_daily_cn runs:")
for r in cur.fetchall():
    err = (r.get("error") or "")[:100]
    print(r["id"], r["status"], r["started_at"], r["finished_at"], err or "-")
