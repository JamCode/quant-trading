-- A-share intraday refresh: overwrites today's stock_daily during session (no history).

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES (
  'stock_intraday_cn',
  'A 股盘中行情',
  'interval',
  '',
  1,
  23
)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind),
  sort_order = VALUES(sort_order);
