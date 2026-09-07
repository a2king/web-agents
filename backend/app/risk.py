from __future__ import annotations

import re

from .extensions import db
from .models import ConfirmGrant

DESTRUCTIVE_RE = re.compile(
    r"("
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b"
    r"|\brm\s+-r\b"
    r"|\bshutil\.rmtree\b"
    r"|\bos\.removedirs\b"
    r"|\brmdir\s+/s\b"
    r")",
    re.IGNORECASE,
)

DELETE_DIR_HINTS = re.compile(r"(删除目录|清空目录|recursive\s+delete|rmtree)", re.IGNORECASE)


def is_destructive_delete(command: str = "", path: str = "", recursive: bool = False) -> bool:
    text = f"{command} {path}"
    if recursive and path:
        return True
    if DESTRUCTIVE_RE.search(text):
        return True
    if DELETE_DIR_HINTS.search(text) and path:
        return True
    return False


def has_grant(user_id: int, session_id: int, action_type: str = "destructive_delete") -> bool:
    grants = ConfirmGrant.query.filter_by(user_id=user_id, action_type=action_type, consumed=False).all()
    for grant in grants:
        if grant.scope == "account":
            return True
        if grant.scope == "session" and grant.session_id == session_id:
            return True
        if grant.scope == "once" and grant.session_id == session_id:
            grant.consumed = True
            db.session.add(grant)
            db.session.commit()
            return True
    return False


def add_grant(user_id: int, session_id: int, scope: str, action_type: str = "destructive_delete"):
    grant = ConfirmGrant(
        user_id=user_id,
        session_id=session_id if scope != "account" else None,
        scope=scope,
        action_type=action_type,
        consumed=False,
    )
    db.session.add(grant)
    db.session.commit()
    return grant
