-- Replace monolithic fund_holdings_pipeline with four independent crawler tasks.
USE fund_svc;

DELETE FROM crawler_job_runs WHERE task_key = 'fund_holdings_pipeline';
DELETE FROM crawler_tasks WHERE task_key = 'fund_holdings_pipeline';

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('fund_holdings_sync', '基金季报持仓', 'cron', '', 1, 11),
  ('stock_ths_industry_sync', '股票行业映射', 'cron', '', 1, 12),
  ('fund_industry_exposure_sync', '基金行业暴露', 'cron', '', 1, 13),
  ('fund_metrics_sync', '基金收益指标', 'cron', '', 1, 14)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind),
  sort_order = VALUES(sort_order);
