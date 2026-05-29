"""A-share static code → name/industry (one row per listed code)."""

from __future__ import annotations

from typing import Any, Optional

_STOCK_BASIC_UPSERT_SQL = """
    INSERT INTO stock_basic (code, name, industry, updated_at)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      industry = COALESCE(VALUES(industry), industry),
      updated_at = VALUES(updated_at)
"""


def stock_basic_row_params(payload: list[dict[str, Any]], now: str) -> list[tuple[Any, ...]]:
    return [
        (
            str(r["code"]).zfill(6),
            str(r.get("name") or "").strip(),
            (str(r["industry"]).strip() if r.get("industry") else None),
            now,
        )
        for r in payload
        if r.get("code")
    ]


def upsert_stock_basic(cur, payload: list[dict[str, Any]], *, now: str, chunk_size: int = 500) -> int:
    params = stock_basic_row_params(payload, now)
    if not params:
        return 0
    for i in range(0, len(params), chunk_size):
        cur.executemany(_STOCK_BASIC_UPSERT_SQL, params[i : i + chunk_size])
    return len(params)


def update_stock_basic_industry(cur, code: str, industry: str, *, now: str) -> None:
    raw = str(code).strip()
    ind = industry.strip()
    if not raw or not ind:
        return
    sym = raw.zfill(6)
    cur.execute(
        """
        UPDATE stock_basic
        SET industry = %s, updated_at = %s
        WHERE code = %s
        """,
        (ind, now, sym),
    )
