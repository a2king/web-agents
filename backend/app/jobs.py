from __future__ import annotations

from flask import current_app

from .agent import Cancelled, NeedConfirm, run_agent_turn
from .extensions import db
from .models import Message, Session, Tenant
from . import quota

_worker_app = None


def set_worker_app(app) -> None:
    global _worker_app
    _worker_app = app


def _app():
    try:
        return current_app._get_current_object()
    except RuntimeError:
        if _worker_app is None:
            raise
        return _worker_app


def enqueue(app, func, *args, **kwargs):
    """入队时不能把 Flask app 塞进 RQ：app 含局部函数，无法 pickle。"""
    if app.config.get("WORKER_INLINE") or getattr(app, "task_queue", None) is None:
        with app.app_context():
            return func(*args, **kwargs)
    return app.task_queue.enqueue(func, *args, **kwargs)


def process_session(session_id: int, user_text: str, resume: bool = False):
    app = _app()
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


def drain_token_queue():
    """管理员上调额度后，尝试拉起因 token 超额排队的会话。"""
    app = _app()
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
