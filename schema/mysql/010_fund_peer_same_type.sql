-- East Money pingzhongdata swithSameType: top peers per period (lazy-filled).
USE fund_svc;

CREATE TABLE IF NOT EXISTS fund_peer_same_type (
  code VARCHAR(16) NOT NULL COMMENT '当前基金代码',
  period VARCHAR(8) NOT NULL COMMENT '区间: 1w|1m|3m|6m|1y',
  rank_pos TINYINT UNSIGNED NOT NULL COMMENT '同类收益排名 1-5',
  peer_code VARCHAR(16) NOT NULL COMMENT '同类基金代码',
  peer_name VARCHAR(256) NOT NULL DEFAULT '' COMMENT '同类基金简称',
  return_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '区间收益率%',
  updated_at DATETIME(3) NOT NULL COMMENT '写入时间 UTC',
  PRIMARY KEY (code, period, rank_pos),
  KEY idx_peer_same_peer (peer_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
