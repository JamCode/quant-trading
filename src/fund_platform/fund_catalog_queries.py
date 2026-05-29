"""Fund catalog list: filters, sort, pagination for /funds."""

from __future__ import annotations

from typing import Any, Optional

import pymysql.cursors

from fund_platform import settings as fp_settings
from fund_platform.queries import _cursor, _serialize_row

# (id, label) for UI chips
CATALOG_CATEGORIES: list[tuple[str, str]] = [
    ("", "全部"),
    ("stock", "股票型"),
    ("mixed", "混合型"),
    ("index", "指数型"),
    ("bond", "债券型"),
    ("money", "货币型"),
    ("qdii", "QDII"),
    ("etf", "ETF"),
    ("overseas_idx", "海外指数"),
]

CATALOG_SORT_OPTIONS: list[tuple[str, str]] = [
    ("code", "代码"),
    ("short_name", "简称"),
    ("daily_pct", "日涨跌"),
    ("nav_date", "净值日期"),
    ("return_1y", "近1年"),
    ("return_3m", "近3月"),
    ("aum_yi", "规模"),
]


def _category_clause(category: str) -> tuple[str, list[Any]]:
    """Return SQL fragment and params (prefix with AND)."""
    c = (category or "").strip()
    if not c:
        return "", []
    if c == "stock":
        return (
            " AND (f.fund_type LIKE %s AND f.fund_type NOT LIKE %s)",
            ["%股票%", "%QDII%"],
        )
    if c == "mixed":
        return " AND f.fund_type LIKE %s", ["%混合%"]
    if c == "index":
        return " AND f.fund_type LIKE %s", ["%指数%"]
    if c == "bond":
        return " AND f.fund_type LIKE %s", ["%债券%"]
    if c == "money":
        return " AND f.fund_type LIKE %s", ["%货币%"]
    if c == "qdii":
        return (
            " AND (f.fund_type LIKE %s OR f.short_name LIKE %s)",
            ["%QDII%", "%QDII%"],
        )
    if c == "etf":
        return (
            " AND (f.fund_type LIKE %s OR f.short_name LIKE %s)",
            ["%ETF%", "%ETF%"],
        )
    if c == "overseas_idx":
        return (
            " AND (f.fund_type LIKE %s OR f.short_name LIKE %s OR f.short_name LIKE %s"
            " OR f.short_name LIKE %s OR f.short_name LIKE %s OR f.short_name LIKE %s)",
            ["%海外%", "%标普%", "%纳斯达克%", "%纳指%", "%NASD%", "%500%"],
        )
    return "", []


def _daily_pct_expr() -> str:
    return (
        "CAST(NULLIF(REPLACE(REPLACE(TRIM(f.daily_pct), '%%', ''), ',', ''), '') "
        "AS DECIMAL(12,4))"
    )


def _order_clause(sort: str, sort_dir: str) -> str:
    desc = sort_dir.lower() != "asc"
    direction = "DESC" if desc else "ASC"
    nulls_last = " IS NULL," if desc else " IS NULL,"
    s = (sort or "code").strip()
    if s == "short_name":
        return f"f.short_name {direction}"
    if s == "daily_pct":
        return f"{_daily_pct_expr()}{nulls_last} {_daily_pct_expr()} {direction}"
    if s == "nav_date":
        return f"f.nav_date {direction}"
    if s == "return_1y":
        return f"m.return_1y{nulls_last} m.return_1y {direction}"
    if s == "return_3m":
        return f"m.return_3m{nulls_last} m.return_3m {direction}"
    if s == "aum_yi":
        return f"f.aum_yi{nulls_last} f.aum_yi {direction}"
    return f"f.code {direction}"


def list_industry_filter_options(conn, *, limit: int = 60) -> list[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT industry FROM fund_industry_exposure
        GROUP BY industry
        ORDER BY MAX(weight_pct) DESC
        LIMIT %s
        """,
        (max(1, limit),),
    )
    return [str(r["industry"]) for r in cur.fetchall() if r.get("industry")]


def query_funds_catalog(
    conn,
    *,
    q: Optional[str] = None,
    fund_type: Optional[str] = None,
    category: Optional[str] = None,
    industry: Optional[str] = None,
    subscribe_open: bool = False,
    sort: str = "code",
    sort_dir: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []

    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(f.short_name LIKE %s OR f.code LIKE %s OR f.pinyin_abbr LIKE %s OR f.fund_type LIKE %s)"
        )
        params.extend([like, like, like, like])

    if fund_type and fund_type.strip():
        clauses.append("f.fund_type LIKE %s")
        params.append(f"%{fund_type.strip()}%")

    cat_sql, cat_params = _category_clause(category or "")
    if cat_sql:
        clauses.append(cat_sql.strip().removeprefix("AND").strip())
        params.extend(cat_params)

    if industry and industry.strip():
        min_w = fp_settings.fund_exposure_min_pct()
        clauses.append(
            """
            f.code IN (
              SELECT e.fund_code FROM fund_industry_exposure e
              WHERE e.industry = %s AND e.weight_pct >= %s
                AND e.report_date = (SELECT MAX(report_date) FROM fund_industry_exposure)
            )
            """
        )
        params.extend([industry.strip(), min_w])

    if subscribe_open:
        clauses.append(
            "(f.subscribe_status LIKE %s OR f.subscribe_status LIKE %s OR f.subscribe_status = %s)"
        )
        params.extend(["%开放%", "%限%", "开放申购"])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    order = _order_clause(sort, sort_dir)

    cur = _cursor(conn)
    count_sql = f"SELECT COUNT(*) AS c FROM funds f {where}"
    cur.execute(count_sql, params)
    total = int(cur.fetchone()["c"])

    sql = f"""
        SELECT
          f.code,
          f.pinyin_abbr,
          f.short_name,
          f.fund_type,
          f.pinyin_full,
          f.nav_date,
          f.nav_unit,
          f.nav_acc,
          f.daily_pct,
          f.daily_change,
          f.subscribe_status,
          f.redeem_status,
          f.aum_yi,
          f.aum_label,
          f.updated_at,
          m.return_1m,
          m.return_3m,
          m.return_1y
        FROM funds f
        LEFT JOIN fund_metrics m ON m.fund_code = f.code
        {where}
        ORDER BY {order}
        LIMIT %s OFFSET %s
    """
    cur.execute(sql, [*params, limit, offset])
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    return rows, total
