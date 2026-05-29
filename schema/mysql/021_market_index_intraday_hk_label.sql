-- Intraday task now covers A-share + HK (e.g. 恒生指数).
USE fund_svc;

UPDATE crawler_tasks
SET display_name = '市场指数盘中（A 股 + 港股）'
WHERE task_key = 'market_index_intraday_cn';
