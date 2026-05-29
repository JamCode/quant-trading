"""Read market_index_daily for Web UI."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pymysql.cursors

from fund_platform.market_index import is_cn_equity_trading_session

_CN_TZ = ZoneInfo("Asia/Shanghai")

_REGION_CN = "cn"
_REGION_HK = "hk"
_REGION_GLOBAL = "global"

_REGION_OPTIONS: list[tuple[str, str]] = [
    ("all", "全部"),
    ("cn", "A 股"),
    ("hk", "港股"),
    ("global", "全球"),
]

_HK_CODES = frozenset({"HSI", "HSCEI", "HSCCI"})


def region_options() -> list[dict[str, str]]:
    return [{"id": rid, "label": label} for rid, label in _REGION_OPTIONS]


def classify_index_region(code: str) -> str:
    c = code.strip().upper()
    if c in _HK_CODES or c.startswith("HK"):
        return _REGION_HK
    if len(c) == 6 and c.isdigit():
        return _REGION_CN
    return _REGION_GLOBAL


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(v, "__float__") and k not in ("code", "name"):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
        else:
            out[k] = v
    out["region"] = classify_index_region(str(out.get("code") or ""))
    return out


def _region_where(region: str) -> tuple[str, list[Any]]:
    reg = (region or "all").lower()
    if reg == _REGION_CN:
        return "code REGEXP '^[0-9]{6}$'", []
    if reg == _REGION_HK:
        return "code IN ('HSI', 'HSCEI', 'HSCCI')", []
    if reg == _REGION_GLOBAL:
        return (
            "code NOT REGEXP '^[0-9]{6}$' AND code NOT IN ('HSI', 'HSCEI', 'HSCCI')",
            [],
        )
    return "1=1", []


def latest_market_index_date(conn, *, region: str = "all") -> Optional[str]:
    clause, params = _region_where(region)
    cur = _cursor(conn)
    cur.execute(
        f"SELECT MAX(trade_date) AS d FROM market_index_daily WHERE {clause}",
        params,
    )
    row = cur.fetchone()
    if not row or not row["d"]:
        return None
    d = row["d"]
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def list_market_index_dates(conn, *, limit: int = 30) -> list[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT trade_date AS d FROM market_index_daily
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (max(1, min(limit, 90)),),
    )
    out: list[str] = []
    for row in cur.fetchall():
        d = row["d"]
        if isinstance(d, date):
            out.append(d.isoformat())
        else:
            out.append(str(d)[:10])
    return out


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def intraday_quote_is_live(quote_time: str, *, now: Optional[datetime] = None) -> bool:
    """Treat intraday row as live quote for UI (today, session or before daily close job)."""
    t = now or _now_cn()
    if t.tzinfo is None:
        t = t.replace(tzinfo=_CN_TZ)
    else:
        t = t.astimezone(_CN_TZ)
    qt = (quote_time or "").strip()
    if len(qt) < 10:
        return False
    if not qt.startswith(t.date().isoformat()):
        return False
    if is_cn_equity_trading_session(t):
        return True
    # Same-day snapshot after 15:00 until daily close sync (~17:00).
    return t.hour < 17 or (t.hour == 17 and t.minute < 30)


def query_latest_cn_intraday(conn) -> list[dict[str, Any]]:
    """Latest intraday snapshot per A-share index code."""
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT i.quote_time, i.code, i.name, i.last_price, i.change_pct, i.change_amt,
               i.open_px, i.high_px, i.low_px, i.prev_close, i.volume, i.amount,
               i.amplitude_pct
        FROM market_index_intraday i
        INNER JOIN (
            SELECT code, MAX(quote_time) AS max_qt
            FROM market_index_intraday
            WHERE code REGEXP '^[0-9]{6}$'
            GROUP BY code
        ) latest ON i.code = latest.code AND i.quote_time = latest.max_qt
        ORDER BY i.code ASC
        """
    )
    return [_serialize_row(r) for r in cur.fetchall()]


def merge_cn_intraday_live(
    items: list[dict[str, Any]],
    live_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Overlay today's intraday quotes onto A-share index list rows."""
    by_code = {str(r.get("code", "")).zfill(6): r for r in live_rows}
    latest_qt: Optional[str] = None
    for item in items:
        if item.get("region") != _REGION_CN:
            continue
        code = str(item.get("code", "")).zfill(6)
        live = by_code.get(code)
        if not live:
            continue
        qt = str(live.get("quote_time") or "")
        if not intraday_quote_is_live(qt):
            continue
        if latest_qt is None or qt > latest_qt:
            latest_qt = qt
        item["live"] = True
        item["quote_time"] = qt
        item["last_price"] = live.get("last_price")
        item["open_px"] = live.get("open_px") if live.get("open_px") is not None else item.get("open_px")
        item["high_px"] = live.get("high_px") if live.get("high_px") is not None else item.get("high_px")
        item["low_px"] = live.get("low_px") if live.get("low_px") is not None else item.get("low_px")
        item["prev_close"] = (
            live.get("prev_close") if live.get("prev_close") is not None else item.get("prev_close")
        )
        if live.get("change_pct") is not None:
            item["change_pct"] = live.get("change_pct")
        if live.get("change_amt") is not None:
            item["change_amt"] = live.get("change_amt")
        if live.get("amount") is not None:
            item["amount"] = live.get("amount")
        if live.get("volume") is not None:
            item["volume"] = live.get("volume")
    return items, latest_qt


def list_market_indices(
    conn,
    *,
    trade_date: Optional[str] = None,
    region: str = "all",
    live: bool = False,
) -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
    reg = (region or "all").lower()
    if reg not in ("all", _REGION_CN, _REGION_HK, _REGION_GLOBAL):
        reg = "all"
    clause, clause_params = _region_where(reg)
    cur = _cursor(conn)

    if trade_date:
        td = trade_date
        cur.execute(
            f"""
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE trade_date = %s AND ({clause})
            ORDER BY code ASC
            """,
            [td, *clause_params],
        )
    else:
        td = None
        cur.execute(
            f"""
            SELECT m.trade_date, m.code, m.name, m.open_px, m.high_px, m.low_px, m.close_px,
                   m.prev_close, m.change_pct, m.change_amt, m.volume, m.amount, m.updated_at
            FROM market_index_daily m
            INNER JOIN (
                SELECT code, MAX(trade_date) AS max_td
                FROM market_index_daily
                WHERE ({clause})
                GROUP BY code
            ) latest ON m.code = latest.code AND m.trade_date = latest.max_td
            ORDER BY m.code ASC
            """,
            clause_params,
        )

    items = [_serialize_row(r) for r in cur.fetchall()]

    def _sort_key(r: dict[str, Any]) -> tuple[int, str]:
        order = {"cn": 0, "hk": 1, "global": 2}
        return (order.get(r.get("region", "global"), 9), str(r.get("code", "")))

    items.sort(key=_sort_key)
    quote_time: Optional[str] = None
    if live and not trade_date and reg in ("all", _REGION_CN):
        live_rows = query_latest_cn_intraday(conn)
        items, quote_time = merge_cn_intraday_live(items, live_rows)
    return items, td, quote_time


def query_cn_intraday_snapshot(conn, code: str) -> Optional[dict[str, Any]]:
    sym = code.strip().zfill(6)
    if not sym.isdigit() or len(sym) != 6:
        return None
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT quote_time, code, name, last_price, change_pct, change_amt,
               open_px, high_px, low_px, prev_close, volume, amount, amplitude_pct
        FROM market_index_intraday
        WHERE code = %s
        ORDER BY quote_time DESC
        LIMIT 1
        """,
        (sym,),
    )
    row = cur.fetchone()
    if not row:
        return None
    snap = _serialize_row(row)
    qt = str(snap.get("quote_time") or "")
    if not intraday_quote_is_live(qt):
        return None
    snap["live"] = True
    snap["close_px"] = snap.get("last_price")
    snap["trade_date"] = qt[:10]
    return snap


def query_market_index_snapshot(
    conn,
    code: str,
    *,
    trade_date: Optional[str] = None,
    live: bool = False,
) -> Optional[dict[str, Any]]:
    sym = code.strip()
    if not sym:
        return None
    if live and not trade_date and classify_index_region(sym) == _REGION_CN:
        intraday = query_cn_intraday_snapshot(conn, sym)
        if intraday:
            return intraday
    cur = _cursor(conn)
    if trade_date:
        cur.execute(
            """
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE trade_date = %s AND code = %s
            """,
            (trade_date, sym),
        )
    else:
        cur.execute(
            """
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE code = %s
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (sym,),
        )
    row = cur.fetchone()
    if not row:
        return None
    return _serialize_row(row)


def query_market_index_history(
    conn,
    code: str,
    *,
    limit: int = 250,
    offset: int = 0,
    order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    sym = code.strip()
    if not sym:
        return [], 0
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM market_index_daily WHERE code = %s AND close_px IS NOT NULL",
        (sym,),
    )
    total = int(cur.fetchone()["c"])
    lim = max(1, min(limit, 2000))
    off = max(0, offset)
    asc = order.lower() == "asc"
    cur.execute(
        """
        SELECT trade_date, open_px, high_px, low_px, close_px,
               change_pct, volume, amount
        FROM market_index_daily
        WHERE code = %s AND close_px IS NOT NULL
        ORDER BY trade_date ASC
        LIMIT %s OFFSET %s
        """
        if asc
        else """
        SELECT trade_date, open_px, high_px, low_px, close_px,
               change_pct, volume, amount
        FROM market_index_daily
        WHERE code = %s AND close_px IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT %s OFFSET %s
        """,
        (sym, lim, off),
    )
    rows = cur.fetchall()
    if not asc:
        rows = list(reversed(rows))

    items: list[dict[str, Any]] = []
    for row in rows:
        td = row["trade_date"]
        if isinstance(td, date):
            td = td.isoformat()
        td_s = str(td)[:10]
        close = row.get("close_px")
        items.append(
            {
                "trade_date": td_s,
                "open": float(row["open_px"]) if row.get("open_px") is not None else None,
                "high": float(row["high_px"]) if row.get("high_px") is not None else None,
                "low": float(row["low_px"]) if row.get("low_px") is not None else None,
                "close": float(close) if close is not None else None,
                "change_pct": float(row["change_pct"]) if row.get("change_pct") is not None else None,
                "volume": row.get("volume"),
                "amount": float(row["amount"]) if row.get("amount") is not None else None,
            }
        )
    return items, total


def query_market_index_bars(
    conn,
    code: str,
    *,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    sym = code.strip()
    if not sym:
        return []
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT trade_date, open_px, high_px, low_px, close_px, volume
        FROM market_index_daily
        WHERE code = %s
          AND close_px IS NOT NULL
          AND trade_date >= %s
          AND trade_date <= %s
        ORDER BY trade_date ASC
        """,
        (sym, start_date[:10], end_date[:10]),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        td = row["trade_date"]
        if isinstance(td, date):
            td = td.isoformat()
        td_s = str(td)[:10]
        close = row.get("close_px")
        items.append(
            {
                "trade_date": td_s,
                "open": float(row["open_px"]) if row.get("open_px") is not None else None,
                "high": float(row["high_px"]) if row.get("high_px") is not None else None,
                "low": float(row["low_px"]) if row.get("low_px") is not None else None,
                "close": float(close) if close is not None else None,
                "volume": row.get("volume"),
            }
        )
    return items
