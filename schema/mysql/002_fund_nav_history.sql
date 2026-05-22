-- Per-fund NAV history (lazy-filled on first API/page request).
USE fund_svc;

CREATE TABLE IF NOT EXISTS fund_nav_history (
  code VARCHAR(16) NOT NULL COMMENT '基金代码',
  nav_date DATE NOT NULL COMMENT '净值日期',
  nav_unit VARCHAR(32) NOT NULL DEFAULT '' COMMENT '单位净值',
  daily_pct VARCHAR(32) NOT NULL DEFAULT '' COMMENT '日增长率',
  PRIMARY KEY (code, nav_date),
  KEY idx_nav_hist_code_date (code, nav_date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
