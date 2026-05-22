-- Drop one-shot startup crawler tasks (replaced by cron/interval only).
USE fund_svc;

DELETE FROM crawler_job_runs
WHERE task_key IN (
  'fund_mysql_startup_sync',
  'stock_daily_startup',
  'sector_fund_flow_startup',
  'fund_holdings_startup',
  'market_index_startup'
);

DELETE FROM crawler_tasks
WHERE task_key IN (
  'fund_mysql_startup_sync',
  'stock_daily_startup',
  'sector_fund_flow_startup',
  'fund_holdings_startup',
  'market_index_startup'
);
