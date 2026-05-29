-- Re-enable industry sector fund flow daily sync (THS source; East Money removed).
USE fund_svc;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('sector_fund_flow_daily', '行业板块资金流向', 'cron', '', 1, 30)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind),
  enabled = VALUES(enabled);
