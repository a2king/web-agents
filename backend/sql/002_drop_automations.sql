-- 第一版去掉定时自动化：已有库执行本文件
SET NAMES utf8mb4;

DROP TABLE IF EXISTS wa_automation_runs;
DROP TABLE IF EXISTS wa_automations;

ALTER TABLE wa_tenants DROP COLUMN max_parallel_automations;
