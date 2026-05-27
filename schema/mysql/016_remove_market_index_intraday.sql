-- Remove intraday market index crawler (optional; daily close jobs remain).
USE fund_svc;

DELETE FROM crawler_job_runs WHERE task_key = 'market_index_intraday';
DELETE FROM crawler_tasks WHERE task_key = 'market_index_intraday';
