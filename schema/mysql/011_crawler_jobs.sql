-- Unified crawler task catalog and run history (Web reads these tables).
USE fund_svc;

CREATE TABLE IF NOT EXISTS crawler_tasks (
  task_key VARCHAR(64) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  schedule_kind VARCHAR(16) NOT NULL COMMENT 'cron|interval|once',
  schedule_summary VARCHAR(256) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  sort_order SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (task_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS crawler_job_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_key VARCHAR(64) NOT NULL,
  status VARCHAR(16) NOT NULL COMMENT 'running|success|failed|skipped',
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  error TEXT,
  detail_json JSON DEFAULT NULL,
  PRIMARY KEY (id),
  KEY idx_crawler_job_runs_task_started (task_key, started_at),
  KEY idx_crawler_job_runs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES
  ('fund_mysql_daily_sync', '基金名录 + 净值快照', 'cron', '', 1, 10),
  ('stock_daily_sync', 'A 股现货日线', 'cron', '', 1, 20),
  ('fund_holdings_pipeline', '基金持仓 + 行业暴露', 'cron', '', 1, 40),
  ('market_index_daily_cn', '市场指数日收盘（A 股）', 'cron', '', 1, 51),
  ('market_index_daily_hk', '市场指数日收盘（港股）', 'cron', '', 1, 52),
  ('market_index_daily_global', '市场指数日收盘（全球）', 'cron', '', 1, 53)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
