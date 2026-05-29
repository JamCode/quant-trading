-- A-share index intraday crawler (minute poll during trading session).
USE fund_svc;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('market_index_intraday_cn', '市场指数盘中（A 股）', 'interval', '', 1, 50)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
