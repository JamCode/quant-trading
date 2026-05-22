-- Fund catalog & crawler metadata (MySQL 8+, utf8mb4).
-- Apply once: mysql ... < schema/mysql/001_init.sql

CREATE DATABASE IF NOT EXISTS fund_svc
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE fund_svc;

-- Full catalog refresh each crawler run (replace-all strategy).
CREATE TABLE IF NOT EXISTS funds (
  code VARCHAR(16) NOT NULL COMMENT '基金代码',
  pinyin_abbr VARCHAR(64) DEFAULT '' COMMENT '拼音缩写',
  short_name VARCHAR(256) NOT NULL COMMENT '简称',
  fund_type VARCHAR(128) DEFAULT '' COMMENT '类型（名录）',
  pinyin_full VARCHAR(512) DEFAULT '' COMMENT '拼音全称',
  nav_date VARCHAR(32) DEFAULT '' COMMENT '净值日期（快照）',
  nav_unit VARCHAR(32) DEFAULT '' COMMENT '单位净值',
  nav_acc VARCHAR(32) DEFAULT '' COMMENT '累计净值',
  prev_nav_unit VARCHAR(32) DEFAULT '' COMMENT '前一日单位净值',
  prev_nav_acc VARCHAR(32) DEFAULT '' COMMENT '前一日累计净值',
  daily_change VARCHAR(32) DEFAULT '' COMMENT '日增长值',
  daily_pct VARCHAR(32) DEFAULT '' COMMENT '日增长率',
  subscribe_status VARCHAR(32) DEFAULT '' COMMENT '申购状态',
  redeem_status VARCHAR(32) DEFAULT '' COMMENT '赎回状态',
  fee_note VARCHAR(64) DEFAULT '' COMMENT '手续费摘要',
  updated_at DATETIME(3) NOT NULL COMMENT '本条记录写入时间 UTC',
  PRIMARY KEY (code),
  KEY idx_funds_short_name (short_name(64)),
  KEY idx_funds_type (fund_type(64)),
  KEY idx_funds_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Crawler job audit trail.
CREATE TABLE IF NOT EXISTS sync_jobs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  started_at DATETIME(3) NOT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  row_count INT UNSIGNED DEFAULT NULL,
  ok TINYINT(1) NOT NULL DEFAULT 0,
  error TEXT,
  PRIMARY KEY (id),
  KEY idx_sync_jobs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Lazy detail + holdings JSON blob per fund (filled by web on demand or future crawler).
CREATE TABLE IF NOT EXISTS fund_details (
  code VARCHAR(16) NOT NULL,
  payload JSON NOT NULL COMMENT 'basic/fees/holdings from AkShare',
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
