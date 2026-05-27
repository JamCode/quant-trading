-- Remove sector fund flow daily crawler (East Money blocked on ECS; sync manually if needed).
USE fund_svc;

DELETE FROM crawler_job_runs WHERE task_key = 'sector_fund_flow_daily';
DELETE FROM crawler_tasks WHERE task_key = 'sector_fund_flow_daily';
