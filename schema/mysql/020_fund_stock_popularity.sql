-- Nightly aggregate: stocks held by many funds (from fund_holdings latest report per fund).
USE fund_svc;

CREATE TABLE IF NOT EXISTS fund_stock_popularity (
  stock_code VARCHAR(32) NOT NULL COMMENT '股票代码',
  stock_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '常见名称',
  fund_count INT UNSIGNED NOT NULL COMMENT '持有该股的基金数(最近一季)',
  avg_weight_pct DECIMAL(10, 4) DEFAULT NULL COMMENT '平均占净值比例%',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (stock_code),
  KEY idx_fund_stock_pop_fund_count (fund_count DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO crawler_tasks (task_key, display_name, schedule_kind, schedule_summary, enabled, sort_order)
VALUES (
  'fund_stock_popularity_daily',
  '基金重仓股统计',
  'cron',
  '每天 04:30',
  1,
  45
)
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  schedule_kind = VALUES(schedule_kind);
