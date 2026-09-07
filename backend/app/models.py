from datetime import datetime

from .extensions import db


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    cpu_limit = db.Column(db.Float, nullable=False, default=1.0)
    memory_mb = db.Column(db.Integer, nullable=False, default=1024)
    disk_mb = db.Column(db.Integer, nullable=False, default=10240)
    max_file_mb = db.Column(db.Integer, nullable=False, default=200)
    weekly_token_quota = db.Column(db.Integer, nullable=False, default=200000)
    max_parallel_sessions = db.Column(db.Integer, nullable=False, default=2)
    max_parallel_automations = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(32), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "cpu_limit": self.cpu_limit,
            "memory_mb": self.memory_mb,
            "disk_mb": self.disk_mb,
            "max_file_mb": self.max_file_mb,
            "weekly_token_quota": self.weekly_token_quota,
            "max_parallel_sessions": self.max_parallel_sessions,
            "max_parallel_automations": self.max_parallel_automations,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(128), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="user")  # admin | user
    ldap_uid = db.Column(db.String(255), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenant = db.relationship("Tenant", backref="users")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "ldap_uid": self.ldap_uid,
            "tenant_id": self.tenant_id,
            "tenant": self.tenant.to_dict() if self.tenant else None,
        }


class ModelConfig(db.Model):
    __tablename__ = "model_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    model_id = db.Column(db.String(128), nullable=False)
    base_url = db.Column(db.String(512), nullable=False)
    api_key = db.Column(db.String(512), nullable=False, default="")
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, hide_key=True):
        key = self.api_key or ""
        return {
            "id": self.id,
            "name": self.name,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "api_key": ("******" + key[-4:]) if hide_key and key else key,
            "has_api_key": bool(key),
            "enabled": self.enabled,
        }


class McpServer(db.Model):
    __tablename__ = "mcp_servers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    transport = db.Column(db.String(32), nullable=False, default="sse")
    url = db.Column(db.String(512), nullable=True)
    command = db.Column(db.String(512), nullable=True)
    headers_json = db.Column(db.Text, nullable=True)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "url": self.url,
            "command": self.command,
            "headers_json": self.headers_json,
            "enabled": self.enabled,
        }


class TenantMcp(db.Model):
    __tablename__ = "tenant_mcps"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    mcp_id = db.Column(db.Integer, db.ForeignKey("mcp_servers.id"), nullable=False)
    enabled = db.Column(db.Boolean, default=True)

    mcp = db.relationship("McpServer")


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    slug = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("tenant_id", "slug", name="uq_tenant_skill_slug"),)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False, default="新会话")
    model_id = db.Column(db.Integer, db.ForeignKey("model_configs.id"), nullable=True)
    kind = db.Column(db.String(32), nullable=False, default="chat")  # chat | automation
    # idle | running | awaiting_confirm | queued | cancelled | failed
    status = db.Column(db.String(32), nullable=False, default="idle")
    queue_reason = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    model = db.relationship("ModelConfig")

    def border_status(self):
        if self.status == "running":
            return "running"
        if self.status == "awaiting_confirm":
            return "confirm"
        if self.status == "queued":
            return "queued"
        return "idle"

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "title": self.title,
            "model_id": self.model_id,
            "model_name": self.model.name if self.model else None,
            "status": self.status,
            "border_status": self.border_status(),
            "queue_reason": self.queue_reason,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    role = db.Column(db.String(32), nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    meta_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "meta_json": self.meta_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SessionEvent(db.Model):
    __tablename__ = "session_events"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    event_type = db.Column(db.String(64), nullable=False)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "payload_json": self.payload_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ConfirmGrant(db.Model):
    __tablename__ = "confirm_grants"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    scope = db.Column(db.String(32), nullable=False)  # once | session | account
    action_type = db.Column(db.String(64), nullable=False, default="destructive_delete")
    consumed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TokenUsage(db.Model):
    __tablename__ = "token_usages"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    week_start = db.Column(db.Date, nullable=False)
    prompt_tokens = db.Column(db.Integer, default=0)
    completion_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint("tenant_id", "week_start", name="uq_tenant_week"),)


class Automation(db.Model):
    __tablename__ = "automations"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    cron_expr = db.Column(db.String(64), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    skill_slug = db.Column(db.String(128), nullable=True)
    model_id = db.Column(db.Integer, db.ForeignKey("model_configs.id"), nullable=True)
    enabled = db.Column(db.Boolean, default=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    model = db.relationship("ModelConfig")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "cron_expr": self.cron_expr,
            "prompt": self.prompt,
            "skill_slug": self.skill_slug,
            "model_id": self.model_id,
            "enabled": self.enabled,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AutomationRun(db.Model):
    __tablename__ = "automation_runs"

    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(db.Integer, db.ForeignKey("automations.id"), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="queued")
    log = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    tokens_used = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    automation = db.relationship("Automation", backref="runs")

    def to_dict(self):
        return {
            "id": self.id,
            "automation_id": self.automation_id,
            "status": self.status,
            "log": self.log,
            "error_message": self.error_message,
            "tokens_used": self.tokens_used,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
