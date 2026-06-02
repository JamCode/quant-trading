"""Read helpers for crawler task monitoring (Web UI)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors

from fund_platform.time_util import format_db_time_cn

_STATUS_LABELS = {
    "running": "运行中",
    "success": "成功",
    "failed": "失败",
    "skipped": "跳过",
}


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _jsonable(val: Any) -> Any:
    if isinstance(val, datetime):
        return _format_cn_time(val)
    if isinstance(val, date):
        return val.isoformat()
    return val


def _format_cn_time(dt: datetime) -> str:
    """DB stores UTC naive timestamps; display as Asia/Shanghai."""
    return str(format_db_time_cn(dt))


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in row.items()}


def _parse_detail(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def format_run_summary(
    *,
    detail: Optional[dict[str, Any]],
    error: Optional[str],
) -> str:
    if error:
        line = str(error).strip().splitlines()[0]
        return line[:160]
    if not detail:
        return ""
    parts: list[str] = []
    if detail.get("row_count") is not None:
        parts.append(f"{detail['row_count']} 行")
    if detail.get("trade_date"):
        parts.append(str(detail["trade_date"]))
    if detail.get("ok_funds") is not None:
        parts.append(f"成功 {detail['ok_funds']} 只")
    if detail.get("source"):
        parts.append(str(detail["source"]))
    if detail.get("skipped_reason"):
        parts.append(str(detail["skipped_reason"])[:80])
    return " · ".join(parts)


def _enrich_run(row: dict[str, Any]) -> dict[str, Any]:
    out = _serialize_row(row)
    detail = _parse_detail(row.get("detail_json"))
    out["detail"] = detail
    out.pop("detail_json", None)
    out["status_label"] = _STATUS_LABELS.get(out.get("status", ""), out.get("status", ""))
    out["summary"] = format_run_summary(detail=detail, error=out.get("error"))
    return out


def list_tasks_with_latest_run(conn) -> list[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT
          t.task_key,
          t.display_name,
          t.schedule_kind,
          t.schedule_summary,
          t.enabled,
          t.sort_order,
          r.id AS last_run_id,
          r.status AS last_status,
          r.started_at AS last_started_at,
          r.finished_at AS last_finished_at,
          r.error AS last_error,
          r.detail_json AS last_detail_json
        FROM crawler_tasks t
        LEFT JOIN crawler_job_runs r ON r.id = (
          SELECT id FROM crawler_job_runs
          WHERE task_key = t.task_key
          ORDER BY started_at DESC, id DESC
          LIMIT 1
        )
        ORDER BY t.sort_order, t.task_key
        """
    )
    rows = []
    for raw in cur.fetchall():
        row = _serialize_row(dict(raw))
        detail = _parse_detail(raw.get("last_detail_json"))
        last_status = row.get("last_status")
        row["last_status_label"] = (
            _STATUS_LABELS.get(last_status, "从未运行") if last_status else "从未运行"
        )
        row["last_summary"] = format_run_summary(detail=detail, error=row.get("last_error"))
        row.pop("last_detail_json", None)
        row["enabled"] = bool(row.get("enabled"))
        rows.append(row)
    return rows


def list_runs(
    conn,
    *,
    task_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    clauses = ["1=1"]
    params: list[Any] = []
    if task_key:
        clauses.append("task_key = %s")
        params.append(task_key.strip())
    if status:
        clauses.append("status = %s")
        params.append(status.strip())
    params.extend([limit, offset])
    cur = _cursor(conn)
    cur.execute(
        f"""
        SELECT r.id, r.task_key, t.display_name, r.status, r.started_at,
               r.finished_at, r.error, r.detail_json
        FROM crawler_job_runs r
        LEFT JOIN crawler_tasks t ON t.task_key = r.task_key
        WHERE {' AND '.join(clauses)}
        ORDER BY r.started_at DESC, r.id DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )
    return [_enrich_run(dict(r)) for r in cur.fetchall()]


def crawler_last_activity(conn) -> Optional[str]:
    cur = _cursor(conn)
    cur.execute("SELECT MAX(started_at) AS t FROM crawler_job_runs")
    row = cur.fetchone()
    if not row or not row.get("t"):
        return None
    return _jsonable(row["t"])


def count_running(conn) -> int:
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM crawler_job_runs WHERE status = %s AND finished_at IS NULL",
        ("running",),
    )
    return int(cur.fetchone()["c"])
