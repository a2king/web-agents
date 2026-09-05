from __future__ import annotations

from datetime import datetime

from croniter import croniter

from .agent import Cancelled, NeedConfirm, run_agent_turn
from .extensions import db
from .models import Automation, AutomationRun, Message, Session, Tenant
from . import quota


def enqueue(app, func, *args, **kwargs):
    if app.config.get("WORKER_INLINE"):
        return func(app, *args, **kwargs)
    queue = getattr(app, "task_queue", None)
    if queue is None:
        return func(app, *args, **kwargs)
    return queue.enqueue(func, app, *args, **kwargs)


def process_session(app, session_id: int, user_text: str, resume: bool = False):
    with app.app_context():
        session = db.session.get(Session, session_id)
        if not session:
            return
        tenant = db.session.get(Tenant, session.tenant_id)
        if quota.tokens_over_quota(tenant):
            session.status = "queued"
            session.queue_reason = "token_quota"
            db.session.commit()
            app.events.emit(session.id, "queued", {"reason": "token_quota"})
            return
        ok, reason = quota.can_start_session(tenant)
        if not ok and session.status != "running":
            session.status = "queued"
            session.queue_reason = "parallel"
            db.session.commit()
            app.events.emit(session.id, "queued", {"reason": reason})
            return
        session.status = "running"
        session.queue_reason = None
        session.error_message = None
        db.session.commit()
        try:
            run_agent_turn(app, session_id, user_text, resume=resume)
            session = db.session.get(Session, session_id)
            if session and session.status != "awaiting_confirm":
                session.status = "idle"
                db.session.commit()
        except NeedConfirm as exc:
            session = db.session.get(Session, session_id)
            session.status = "awaiting_confirm"
            session.error_message = exc.payload.get("reason")
            db.session.commit()
            app.events.emit(session.id, "confirm", exc.payload)
        except Cancelled:
            session = db.session.get(Session, session_id)
            session.status = "cancelled"
            db.session.commit()
            app.events.emit(session.id, "status", {"status": "cancelled"})
        except Exception as exc:  # noqa: BLE001
            session = db.session.get(Session, session_id)
            session.status = "failed"
            session.error_message = str(exc)
            db.session.commit()
            app.events.emit(session.id, "error", {"message": str(exc)})
        app.cancel_flags.pop(session_id, None)


def process_automation(app, automation_id: int):
    with app.app_context():
        auto = db.session.get(Automation, automation_id)
        if not auto or not auto.enabled:
            return
        tenant = db.session.get(Tenant, auto.tenant_id)
        run = AutomationRun(automation_id=auto.id, tenant_id=auto.tenant_id, status="queued")
        db.session.add(run)
        db.session.commit()
        if quota.tokens_over_quota(tenant):
            run.status = "queued"
            run.error_message = "token 超额，等待管理员分配"
            db.session.commit()
            return
        ok, reason = quota.can_start_automation(tenant)
        if not ok:
            run.status = "queued"
            run.error_message = reason
            db.session.commit()
            return
        run.status = "running"
        db.session.commit()
        session = Session(
            tenant_id=auto.tenant_id,
            user_id=auto.user_id,
            title=f"[自动化] {auto.name}",
            model_id=auto.model_id,
            kind="automation",
            status="running",
        )
        db.session.add(session)
        db.session.commit()
        prompt = auto.prompt
        if auto.skill_slug and not prompt.startswith("/"):
            prompt = f"/{auto.skill_slug} {prompt}"
        db.session.add(Message(session_id=session.id, role="user", content=prompt))
        db.session.commit()
        logs = []
        try:
            text = run_agent_turn(app, session.id, prompt)
            logs.append(text or "")
            session.status = "idle"
            run.status = "success"
            run.log = "\n".join(logs)
            run.finished_at = datetime.utcnow()
        except NeedConfirm as exc:
            session.status = "awaiting_confirm"
            run.status = "awaiting_confirm"
            run.error_message = exc.payload.get("reason")
            run.log = str(exc.payload)
        except Exception as exc:  # noqa: BLE001
            session.status = "failed"
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
        auto.next_run_at = next_cron(auto.cron_expr)
        db.session.commit()


def next_cron(expr: str, now: datetime | None = None) -> datetime:
    base = now or datetime.utcnow()
    return croniter(expr, base).get_next(datetime)


def tick_automations(app):
    with app.app_context():
        now = datetime.utcnow()
        due = Automation.query.filter(Automation.enabled.is_(True), Automation.next_run_at <= now).all()
        for auto in due:
            enqueue(app, process_automation, auto.id)


def drain_token_queue(app):
    """管理员上调额度后，尝试拉起因 token 超额排队的会话。"""
    with app.app_context():
        queued = Session.query.filter_by(status="queued", queue_reason="token_quota").all()
        for session in queued:
            tenant = db.session.get(Tenant, session.tenant_id)
            if quota.tokens_over_quota(tenant):
                continue
            last_user = (
                Message.query.filter_by(session_id=session.id, role="user")
                .order_by(Message.id.desc())
                .first()
            )
            if last_user:
                enqueue(app, process_session, session.id, last_user.content, True)
