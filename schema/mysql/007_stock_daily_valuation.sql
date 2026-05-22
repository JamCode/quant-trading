-- Valuation & extra quote fields from East Money A-share spot.
USE fund_svc;

ALTER TABLE stock_daily
  ADD COLUMN pe_dynamic DECIMAL(16, 4) DEFAULT NULL COMMENT '市盈率(动态)' AFTER amount,
  ADD COLUMN pb DECIMAL(16, 4) DEFAULT NULL COMMENT '市净率' AFTER pe_dynamic,
  ADD COLUMN volume_ratio DECIMAL(16, 4) DEFAULT NULL COMMENT '量比' AFTER pb,
  ADD COLUMN amplitude_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '振幅%' AFTER volume_ratio,
  ADD COLUMN change_5m_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '5分钟涨跌%' AFTER amplitude_pct,
  ADD COLUMN speed_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨速%' AFTER change_5m_pct,
  ADD COLUMN change_60d_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '60日涨跌幅%' AFTER speed_pct,
  ADD COLUMN change_ytd_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '年初至今涨跌幅%' AFTER change_60d_pct;
