"""Read helpers for industry_pe_daily (CNINFO 国证)."""

from __future__ import annotations

from typing import Any, Optional


def list_latest_industry_pe(
    conn,
    *,
    industry_level: Optional[int] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    cur = conn.cursor()
    clauses = ["1=1"]
    params: list[Any] = []
    if industry_level is not None:
        clauses.append("v.industry_level = %s")
        params.append(int(industry_level))
    params.append(max(1, min(int(limit), 500)))
    cur.execute(
        f"""
        SELECT v.trade_date, v.industry_code, v.industry_name, v.industry_level,
               v.pe_weighted, v.pe_median, v.pe_avg,
               v.company_count, v.calc_company_count, v.source, v.updated_at
        FROM industry_pe_daily v
        INNER JOIN (
          SELECT industry_code, MAX(trade_date) AS max_date
          FROM industry_pe_daily
          GROUP BY industry_code
        ) latest
          ON v.industry_code = latest.industry_code
         AND v.trade_date = latest.max_date
        WHERE {' AND '.join(clauses)}
        ORDER BY v.industry_level, v.industry_name
        LIMIT %s
        """,
        params,
    )
    return _rows_to_dicts(cur.fetchall())


def query_industry_pe_history(
    conn,
    *,
    industry_code: str,
    limit: int = 730,
) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trade_date, industry_code, industry_name, industry_level,
               pe_weighted, pe_median, pe_avg,
               company_count, calc_company_count, source, updated_at
        FROM industry_pe_daily
        WHERE industry_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (industry_code.strip(), max(1, min(int(limit), 5000))),
    )
    rows = _rows_to_dicts(cur.fetchall())
    rows.reverse()
    return rows


def latest_industry_pe_date(conn) -> Optional[str]:
    cur = conn.cursor()
    cur.execute("SELECT MAX(trade_date) FROM industry_pe_daily")
    row = cur.fetchone()
    if not row:
        return None
    td = row[0] if not isinstance(row, dict) else row.get("MAX(trade_date)")
    if hasattr(td, "isoformat"):
        return td.isoformat()
    return str(td) if td else None


def _fnum(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows_to_dicts(rows: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            item = dict(row)
        else:
            item = {
                "trade_date": row[0],
                "industry_code": row[1],
                "industry_name": row[2],
                "industry_level": row[3],
                "pe_weighted": row[4],
                "pe_median": row[5],
                "pe_avg": row[6],
                "company_count": row[7],
                "calc_company_count": row[8],
                "source": row[9],
                "updated_at": row[10],
            }
        td = item.get("trade_date")
        if hasattr(td, "isoformat"):
            item["trade_date"] = td.isoformat()
        ua = item.get("updated_at")
        if hasattr(ua, "isoformat"):
            item["updated_at"] = ua.isoformat()
        for k in ("pe_weighted", "pe_median", "pe_avg"):
            item[k] = _fnum(item.get(k))
        if item.get("industry_level") is not None:
            item["industry_level"] = int(item["industry_level"])
        out.append(item)
    return out
