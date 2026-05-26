"""Read helpers for broad index PE."""

from __future__ import annotations

from typing import Any, Optional


def _fnum(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize_index_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        td = row.get("trade_date")
        ua = row.get("updated_at")
        return {
            "trade_date": td.isoformat() if hasattr(td, "isoformat") else td,
            "region": row.get("region"),
            "index_code": row.get("index_code"),
            "index_name": row.get("index_name"),
            "source": row.get("source"),
            "pe_ttm": _fnum(row.get("pe_ttm")),
            "pe_static": _fnum(row.get("pe_static")),
            "pe_cape": _fnum(row.get("pe_cape")),
            "index_close": _fnum(row.get("index_close")),
            "updated_at": ua.isoformat() if hasattr(ua, "isoformat") else ua,
        }
    return {
        "trade_date": row[0].isoformat() if hasattr(row[0], "isoformat") else row[0],
        "region": row[1],
        "index_code": row[2],
        "index_name": row[3],
        "source": row[4],
        "pe_ttm": _fnum(row[5]),
        "pe_static": _fnum(row[6]),
        "pe_cape": _fnum(row[7]),
        "index_close": _fnum(row[8]),
        "updated_at": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
    }


def list_latest_index_valuation(
    conn,
    *,
    region: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    cur = conn.cursor()
    params: list[Any] = []
    region_clause = ""
    if region:
        region_clause = "WHERE region = %s"
        params.append(region.strip().lower())
    params.append(max(1, min(int(limit), 200)))
    cur.execute(
        f"""
        SELECT v.trade_date, v.region, v.index_code, v.index_name, v.source,
               v.pe_ttm, v.pe_static, v.pe_cape, v.index_close, v.updated_at
        FROM index_valuation_daily v
        INNER JOIN (
          SELECT region, index_code, MAX(trade_date) AS max_date
          FROM index_valuation_daily
          {region_clause}
          GROUP BY region, index_code
        ) latest
          ON v.region = latest.region
         AND v.index_code = latest.index_code
         AND v.trade_date = latest.max_date
        ORDER BY v.region, v.index_name
        LIMIT %s
        """,
        params,
    )
    return [_serialize_index_row(row) for row in cur.fetchall()]


def query_index_valuation_history(
    conn,
    *,
    region: str,
    index_code: str,
    limit: int = 730,
) -> list[dict[str, Any]]:
    """Chronological PE series for one index (oldest first)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trade_date, region, index_code, index_name, source,
               pe_ttm, pe_static, pe_cape, index_close, updated_at
        FROM index_valuation_daily
        WHERE region = %s AND index_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (region.strip().lower(), index_code.strip(), max(1, min(int(limit), 5000))),
    )
    rows = [_serialize_index_row(row) for row in cur.fetchall()]
    rows.reverse()
    return rows


def group_latest_by_region(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"cn": [], "hk": [], "us": []}
    for item in items:
        reg = str(item.get("region") or "").lower()
        if reg in grouped:
            grouped[reg].append(item)
    return grouped
