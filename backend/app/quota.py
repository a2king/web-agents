from __future__ import annotations

from .extensions import db
from .models import AutomationRun, Session, Tenant, TokenUsage
from .utils import week_start


def tenant_token_usage(tenant_id: int) -> TokenUsage:
    ws = week_start()
    row = TokenUsage.query.filter_by(tenant_id=tenant_id, week_start=ws).first()
    if not row:
        row = TokenUsage(tenant_id=tenant_id, user_id=None, week_start=ws)
        db.session.add(row)
        db.session.flush()
    return row


def add_tokens(tenant_id: int, user_id: int, prompt: int, completion: int) -> TokenUsage:
    row = tenant_token_usage(tenant_id)
    row.user_id = user_id or row.user_id
    row.prompt_tokens += prompt
    row.completion_tokens += completion
    row.total_tokens += prompt + completion
    db.session.add(row)
    return row


def tokens_over_quota(tenant: Tenant) -> bool:
    used = tenant_token_usage(tenant.id).total_tokens
    return used >= tenant.weekly_token_quota


def running_sessions(tenant_id: int) -> int:
    return Session.query.filter(
        Session.tenant_id == tenant_id,
        Session.status.in_(["running", "awaiting_confirm"]),
    ).count()


def running_automations(tenant_id: int) -> int:
    return AutomationRun.query.filter(
        AutomationRun.tenant_id == tenant_id,
        AutomationRun.status.in_(["running", "queued"]),
    ).count()


def can_start_session(tenant: Tenant) -> tuple[bool, str]:
    if tenant.status != "active":
        return False, "租户已停用"
    if running_sessions(tenant.id) >= tenant.max_parallel_sessions:
        return False, "已达到最大并行会话数"
    return True, ""


def can_start_automation(tenant: Tenant) -> tuple[bool, str]:
    if tenant.status != "active":
        return False, "租户已停用"
    if running_automations(tenant.id) >= tenant.max_parallel_automations:
        return False, "已达到最大并行自动化数"
    return True, ""


def usage_payload(tenant: Tenant, user_id: int | None = None):
    row = tenant_token_usage(tenant.id)
    return {
        "week_start": row.week_start.isoformat(),
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "total_tokens": row.total_tokens,
        "weekly_token_quota": tenant.weekly_token_quota,
        "remaining": max(tenant.weekly_token_quota - row.total_tokens, 0),
        "over_quota": row.total_tokens >= tenant.weekly_token_quota,
        "user_id": user_id,
    }
