-- Per-fund peer ranking trend (AkShare EM 同类排名走势, lazy-filled).
USE fund_svc;

CREATE TABLE IF NOT EXISTS fund_peer_rank (
  code VARCHAR(16) NOT NULL COMMENT '基金代码',
  rank_date DATE NOT NULL COMMENT '报告日期',
  rank_in_type INT UNSIGNED DEFAULT NULL COMMENT '同类型排名-每日近三月排名(越小越强)',
  rank_total INT UNSIGNED DEFAULT NULL COMMENT '总排名-每日近三月排名(越小越强)',
  PRIMARY KEY (code, rank_date),
  KEY idx_peer_rank_code_date (code, rank_date DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
