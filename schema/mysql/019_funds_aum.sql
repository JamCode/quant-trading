-- Latest fund AUM (规模) from Xueqiu basic info, in 亿元.
USE fund_svc;

ALTER TABLE funds
  ADD COLUMN aum_yi DECIMAL(18, 4) DEFAULT NULL COMMENT '最新规模(亿元)' AFTER fee_note,
  ADD COLUMN aum_label VARCHAR(64) DEFAULT NULL COMMENT '规模原文(如34.49亿)' AFTER aum_yi;

ALTER TABLE funds ADD KEY idx_funds_aum_yi (aum_yi);
