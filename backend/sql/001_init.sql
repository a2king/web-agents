-- Web Agents 初始化表结构（前缀 wa_）
-- 先建库再执行本文件：
--   CREATE DATABASE webagent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--   USE webagent;
--   SOURCE 001_init.sql;

SET NAMES utf8mb4;

-- 租户 / 独立空间
CREATE TABLE wa_tenants (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  cpu_limit FLOAT NOT NULL DEFAULT 1.0,
  memory_mb INT NOT NULL DEFAULT 1024,
  disk_mb INT NOT NULL DEFAULT 10240,
  max_file_mb INT NOT NULL DEFAULT 200,
  weekly_token_quota INT NOT NULL DEFAULT 200000,
  max_parallel_sessions INT NOT NULL DEFAULT 2,
  max_parallel_automations INT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NULL,
  updated_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_wa_tenants_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户（一人一租户）
CREATE TABLE wa_users (
  id INT NOT NULL AUTO_INCREMENT,
  username VARCHAR(128) NOT NULL,
  password_hash VARCHAR(255) NULL,
  display_name VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  ldap_uid VARCHAR(255) NULL,
  tenant_id INT NOT NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_wa_users_username (username),
  KEY idx_wa_users_tenant_id (tenant_id),
  CONSTRAINT fk_wa_users_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 模型接入（OpenAI 兼容中转站）
CREATE TABLE wa_model_configs (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  model_id VARCHAR(128) NOT NULL,
  base_url VARCHAR(512) NOT NULL,
  api_key VARCHAR(512) NOT NULL DEFAULT '',
  enabled TINYINT(1) NULL DEFAULT 1,
  created_at DATETIME NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MCP 服务
CREATE TABLE wa_mcp_servers (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  transport VARCHAR(32) NOT NULL DEFAULT 'sse',
  url VARCHAR(512) NULL,
  command VARCHAR(512) NULL,
  headers_json TEXT NULL,
  enabled TINYINT(1) NULL DEFAULT 1,
  created_at DATETIME NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 租户勾选的 MCP
CREATE TABLE wa_tenant_mcps (
  id INT NOT NULL AUTO_INCREMENT,
  tenant_id INT NOT NULL,
  mcp_id INT NOT NULL,
  enabled TINYINT(1) NULL DEFAULT 1,
  PRIMARY KEY (id),
  KEY idx_wa_tenant_mcps_tenant_id (tenant_id),
  KEY idx_wa_tenant_mcps_mcp_id (mcp_id),
  CONSTRAINT fk_wa_tenant_mcps_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id),
  CONSTRAINT fk_wa_tenant_mcps_mcp_id FOREIGN KEY (mcp_id) REFERENCES wa_mcp_servers (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Skills（租户内 slug 唯一）
CREATE TABLE wa_skills (
  id INT NOT NULL AUTO_INCREMENT,
  tenant_id INT NOT NULL,
  user_id INT NOT NULL,
  name VARCHAR(128) NOT NULL,
  slug VARCHAR(128) NOT NULL,
  description TEXT NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_wa_skills_tenant_slug (tenant_id, slug),
  KEY idx_wa_skills_user_id (user_id),
  CONSTRAINT fk_wa_skills_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id),
  CONSTRAINT fk_wa_skills_user_id FOREIGN KEY (user_id) REFERENCES wa_users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话
CREATE TABLE wa_sessions (
  id INT NOT NULL AUTO_INCREMENT,
  tenant_id INT NOT NULL,
  user_id INT NOT NULL,
  title VARCHAR(255) NOT NULL DEFAULT '新会话',
  model_id INT NULL,
  kind VARCHAR(32) NOT NULL DEFAULT 'chat',
  status VARCHAR(32) NOT NULL DEFAULT 'idle',
  queue_reason VARCHAR(64) NULL,
  error_message TEXT NULL,
  created_at DATETIME NULL,
  updated_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_sessions_tenant_id (tenant_id),
  KEY idx_wa_sessions_user_id (user_id),
  KEY idx_wa_sessions_model_id (model_id),
  CONSTRAINT fk_wa_sessions_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id),
  CONSTRAINT fk_wa_sessions_user_id FOREIGN KEY (user_id) REFERENCES wa_users (id),
  CONSTRAINT fk_wa_sessions_model_id FOREIGN KEY (model_id) REFERENCES wa_model_configs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话消息
CREATE TABLE wa_messages (
  id INT NOT NULL AUTO_INCREMENT,
  session_id INT NOT NULL,
  role VARCHAR(32) NOT NULL,
  content TEXT NOT NULL,
  meta_json TEXT NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_messages_session_id (session_id),
  CONSTRAINT fk_wa_messages_session_id FOREIGN KEY (session_id) REFERENCES wa_sessions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话事件流
CREATE TABLE wa_session_events (
  id INT NOT NULL AUTO_INCREMENT,
  session_id INT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  payload_json TEXT NOT NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_session_events_session_id (session_id),
  CONSTRAINT fk_wa_session_events_session_id FOREIGN KEY (session_id) REFERENCES wa_sessions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 高风险操作确认授权
CREATE TABLE wa_confirm_grants (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  session_id INT NULL,
  scope VARCHAR(32) NOT NULL,
  action_type VARCHAR(64) NOT NULL DEFAULT 'destructive_delete',
  consumed TINYINT(1) NULL DEFAULT 0,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_confirm_grants_user_id (user_id),
  KEY idx_wa_confirm_grants_session_id (session_id),
  CONSTRAINT fk_wa_confirm_grants_user_id FOREIGN KEY (user_id) REFERENCES wa_users (id),
  CONSTRAINT fk_wa_confirm_grants_session_id FOREIGN KEY (session_id) REFERENCES wa_sessions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 按周 Token 用量
CREATE TABLE wa_token_usages (
  id INT NOT NULL AUTO_INCREMENT,
  tenant_id INT NOT NULL,
  user_id INT NULL,
  week_start DATE NOT NULL,
  prompt_tokens INT NULL DEFAULT 0,
  completion_tokens INT NULL DEFAULT 0,
  total_tokens INT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_wa_token_usages_tenant_week (tenant_id, week_start),
  KEY idx_wa_token_usages_user_id (user_id),
  CONSTRAINT fk_wa_token_usages_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id),
  CONSTRAINT fk_wa_token_usages_user_id FOREIGN KEY (user_id) REFERENCES wa_users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 定时自动化
CREATE TABLE wa_automations (
  id INT NOT NULL AUTO_INCREMENT,
  tenant_id INT NOT NULL,
  user_id INT NOT NULL,
  name VARCHAR(128) NOT NULL,
  cron_expr VARCHAR(64) NOT NULL,
  prompt TEXT NOT NULL,
  skill_slug VARCHAR(128) NULL,
  model_id INT NULL,
  enabled TINYINT(1) NULL DEFAULT 1,
  next_run_at DATETIME NULL,
  created_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_automations_tenant_id (tenant_id),
  KEY idx_wa_automations_user_id (user_id),
  KEY idx_wa_automations_model_id (model_id),
  CONSTRAINT fk_wa_automations_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id),
  CONSTRAINT fk_wa_automations_user_id FOREIGN KEY (user_id) REFERENCES wa_users (id),
  CONSTRAINT fk_wa_automations_model_id FOREIGN KEY (model_id) REFERENCES wa_model_configs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 自动化执行历史
CREATE TABLE wa_automation_runs (
  id INT NOT NULL AUTO_INCREMENT,
  automation_id INT NOT NULL,
  tenant_id INT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  log TEXT NULL,
  error_message TEXT NULL,
  tokens_used INT NULL DEFAULT 0,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_wa_automation_runs_automation_id (automation_id),
  KEY idx_wa_automation_runs_tenant_id (tenant_id),
  CONSTRAINT fk_wa_automation_runs_automation_id FOREIGN KEY (automation_id) REFERENCES wa_automations (id),
  CONSTRAINT fk_wa_automation_runs_tenant_id FOREIGN KEY (tenant_id) REFERENCES wa_tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
