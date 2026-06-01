-- Group crawler tasks in the Web UI: fund block, then equities, sector, indices.
USE fund_svc;

UPDATE crawler_tasks SET sort_order = 10 WHERE task_key = 'fund_mysql_daily_sync';
UPDATE crawler_tasks SET sort_order = 11 WHERE task_key = 'fund_holdings_sync';
UPDATE crawler_tasks SET sort_order = 12 WHERE task_key = 'stock_ths_industry_sync';
UPDATE crawler_tasks SET sort_order = 13 WHERE task_key = 'fund_industry_exposure_sync';
UPDATE crawler_tasks SET sort_order = 14 WHERE task_key = 'fund_metrics_sync';
UPDATE crawler_tasks SET sort_order = 15 WHERE task_key = 'fund_stock_popularity_daily';
UPDATE crawler_tasks SET sort_order = 20 WHERE task_key = 'stock_daily_sync';
UPDATE crawler_tasks SET sort_order = 21 WHERE task_key = 'hk_stock_daily_sync';
UPDATE crawler_tasks SET sort_order = 22 WHERE task_key = 'us_stock_daily_sync';
UPDATE crawler_tasks SET sort_order = 30 WHERE task_key = 'sector_fund_flow_daily';
UPDATE crawler_tasks SET sort_order = 40 WHERE task_key = 'market_index_intraday_cn';
UPDATE crawler_tasks SET sort_order = 41 WHERE task_key = 'market_index_daily_cn';
UPDATE crawler_tasks SET sort_order = 42 WHERE task_key = 'market_index_daily_hk';
UPDATE crawler_tasks SET sort_order = 43 WHERE task_key = 'market_index_daily_global';
UPDATE crawler_tasks SET sort_order = 44 WHERE task_key = 'index_valuation_daily_sync';
UPDATE crawler_tasks SET sort_order = 45 WHERE task_key = 'industry_pe_cninfo_daily_sync';
