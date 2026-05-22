"""Read stock_daily joined with industry constituents."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        else:
            out[k] = v
    return out


def latest_stock_daily_date(conn) -> Optional[str]:
    cur = _cursor(conn)
    cur.execute("SELECT MAX(trade_date) AS d FROM stock_daily")
    row = cur.fetchone()
    if not row or not row["d"]:
        return None
    d = row["d"]
    return d.isoformat() if isinstance(d, date) else str(d)


def query_industry_constituents_from_db(
    conn,
    *,
    industry: str,
    trade_date: str,
) -> Optional[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT c.code,
               COALESCE(sd.name, '') AS name,
               sd.price,
               sd.change_pct,
               sd.float_market_cap,
               sd.total_market_cap,
               sd.turnover_pct,
               sd.amount,
               sd.pe_dynamic,
               sd.pb,
               sd.volume_ratio,
               sd.amplitude_pct,
               sd.change_5m_pct,
               sd.speed_pct,
               sd.change_60d_pct,
               sd.change_ytd_pct
        FROM sector_industry_constituent c
        LEFT JOIN stock_daily sd
          ON sd.trade_date = c.trade_date AND sd.code = c.code
        WHERE c.trade_date = %s AND c.industry = %s
        ORDER BY sd.change_pct IS NULL, sd.change_pct DESC
        """,
        (trade_date, industry.strip()),
    )
    rows = cur.fetchall()
    if not rows:
        return None

    items: list[dict[str, Any]] = []
    caps: list[float] = []
    missing_cap = 0
    for r in rows:
        cap = r.get("float_market_cap")
        if cap is None:
            missing_cap += 1
        else:
            caps.append(float(cap))
        amount = r.get("amount")
        def _f(key: str) -> Optional[float]:
            v = r.get(key)
            return float(v) if v is not None else None

        items.append(
            {
                "code": r["code"],
                "name": r.get("name") or "",
                "price": _f("price"),
                "change_pct": _f("change_pct"),
                "float_market_cap": float(cap) if cap is not None else None,
                "total_market_cap": _f("total_market_cap"),
                "turnover_pct": _f("turnover_pct"),
                "amount": float(amount) if amount is not None else None,
                "pe_dynamic": _f("pe_dynamic"),
                "pb": _f("pb"),
                "volume_ratio": _f("volume_ratio"),
                "amplitude_pct": _f("amplitude_pct"),
                "change_5m_pct": _f("change_5m_pct"),
                "speed_pct": _f("speed_pct"),
                "change_60d_pct": _f("change_60d_pct"),
                "change_ytd_pct": _f("change_ytd_pct"),
            }
        )
    return {
        "industry": industry,
        "trade_date": trade_date,
        "count": len(items),
        "items": items,
        "float_market_cap_sum": round(sum(caps), 2) if caps else None,
        "float_market_cap_missing": missing_cap,
        "source": "db",
    }
