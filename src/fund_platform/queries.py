"""Read helpers for the fund web UI (MySQL)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _jsonable(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, date):
        return val.isoformat()
    return val


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in row.items()}


def latest_sync_summary(conn) -> Optional[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT id, started_at, finished_at, row_count, ok, error
        FROM sync_jobs
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    return _serialize_row(row)


def fund_count(conn) -> int:
    cur = _cursor(conn)
    cur.execute("SELECT COUNT(*) AS c FROM funds")
    return int(cur.fetchone()["c"])


def get_fund_row(conn, code: str) -> Optional[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute("SELECT * FROM funds WHERE code = %s", (code.strip(),))
    row = cur.fetchone()
    if not row:
        return None
    return _serialize_row(row)


def get_funds_by_codes(conn, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Map fund code -> {code, short_name} for codes present in catalog."""
    cleaned = []
    seen: set[str] = set()
    for raw in codes:
        c = str(raw).strip()
        if len(c) == 6 and c.isdigit() and c not in seen:
            seen.add(c)
            cleaned.append(c)
    if not cleaned:
        return {}
    cur = _cursor(conn)
    placeholders = ", ".join(["%s"] * len(cleaned))
    cur.execute(
        f"SELECT code, short_name FROM funds WHERE code IN ({placeholders})",
        cleaned,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        code = str(row["code"])
        out[code] = {"code": code, "short_name": row.get("short_name")}
    return out


def query_funds(
    conn,
    q: Optional[str],
    fund_type: Optional[str],
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(short_name LIKE %s OR code LIKE %s OR pinyin_abbr LIKE %s)")
        params.extend([like, like, like])
    if fund_type and fund_type.strip():
        clauses.append("fund_type = %s")
        params.append(fund_type.strip())
    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    cur = _cursor(conn)
    cur.execute(f"SELECT COUNT(*) AS c FROM funds {where}", params)
    total = int(cur.fetchone()["c"])

    sql = f"""
        SELECT
          code,
          pinyin_abbr,
          short_name,
          fund_type,
          pinyin_full,
          nav_date,
          nav_unit,
          nav_acc,
          daily_pct,
          subscribe_status,
          redeem_status,
          updated_at
        FROM funds {where}
        ORDER BY code
        LIMIT %s OFFSET %s
    """
    cur.execute(sql, [*params, limit, offset])
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    return rows, total
