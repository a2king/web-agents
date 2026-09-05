import hashlib
import re
from datetime import date, datetime, timedelta
from functools import wraps

import bcrypt
from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from .extensions import db
from .models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def week_start(now: datetime | None = None) -> date:
    current = now or datetime.utcnow()
    return (current - timedelta(days=current.weekday())).date()


def slugify(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or hashlib.md5(name.encode("utf-8")).hexdigest()[:8]


def current_user() -> User | None:
    verify_jwt_in_request()
    identity = get_jwt_identity()
    if identity is None:
        return None
    return db.session.get(User, int(identity))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "未登录"}), 401
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "未登录"}), 401
        claims = get_jwt()
        if user.role != "admin" and claims.get("role") != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        return fn(user, *args, **kwargs)

    return wrapper


def ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def fail(message: str, status: int = 400, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status
