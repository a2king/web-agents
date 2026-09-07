from __future__ import annotations

import os
import time
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .bus import create_bus
from .config import Config
from .events import EventHub
from .extensions import db, jwt
from .runtime import create_runtime
from .utils import hash_password

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def spa(path="index.html"):
    if path.startswith("api/"):
        return {"error": "not found"}, 404
    if _FRONTEND_DIST.exists():
        target = _FRONTEND_DIST / path
        if target.is_file():
            return send_from_directory(_FRONTEND_DIST, path)
        return send_from_directory(_FRONTEND_DIST, "index.html")
    return {"ok": True, "name": "web-agents"}


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object or Config)
    Path(app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    jwt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from .api import bp

    app.register_blueprint(bp)

    app.runtime = create_runtime(app)
    app.bus = create_bus(app)
    app.events = EventHub(app.bus)
    app.cancel_flags = {}
    app.task_queue = None

    redis_url = app.config.get("REDIS_URL")
    if redis_url and not app.config.get("WORKER_INLINE"):
        try:
            from rq import Queue

            from .redis_client import from_url as redis_from_url

            app.redis = redis_from_url(redis_url)
            app.task_queue = Queue("webagent", connection=app.redis)
        except Exception:
            app.task_queue = None

    app.add_url_rule("/", endpoint="spa_index", view_func=spa)
    app.add_url_rule("/<path:path>", endpoint="spa", view_func=spa)

    with app.app_context():
        _wait_for_schema(app)

    return app


def _wait_for_schema(app: Flask, attempts: int = 30, delay: float = 2.0) -> None:
    last_error: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            if app.config.get("TESTING"):
                db.create_all()
            else:
                db.session.execute(text("SELECT 1"))
            seed_admin(app)
            return
        except OperationalError as exc:
            last_error = exc
            app.logger.warning("等待数据库就绪 (%s/%s): %s", i, attempts, exc)
            time.sleep(delay)
        except ProgrammingError:
            app.logger.error("数据表不存在，请先执行 backend/sql/001_init.sql")
            raise
    raise last_error


def seed_admin(app: Flask) -> None:
    from .models import Tenant, User

    username = app.config["DEFAULT_ADMIN_USER"]
    if User.query.filter_by(username=username).first():
        return
    tenant = Tenant(
        name="admin-space",
        cpu_limit=2,
        memory_mb=2048,
        disk_mb=20480,
        max_file_mb=200,
        weekly_token_quota=500000,
        max_parallel_sessions=3,
        max_parallel_automations=1,
    )
    db.session.add(tenant)
    db.session.flush()
    admin = User(
        username=username,
        password_hash=hash_password(app.config["DEFAULT_ADMIN_PASSWORD"]),
        display_name="管理员",
        role="admin",
        ldap_uid=username,
        tenant_id=tenant.id,
    )
    db.session.add(admin)
    db.session.commit()
    app.runtime.ensure_workspace(tenant.id)


def create_test_app():
    from .config import TestConfig

    os.environ.setdefault("WORKER_INLINE", "1")
    return create_app(TestConfig)
