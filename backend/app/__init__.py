from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from .bus import create_bus
from .config import Config
from .events import EventHub
from .extensions import db, jwt
from .runtime import create_runtime
from .utils import hash_password


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
            from redis import Redis
            from rq import Queue

            app.redis = Redis.from_url(redis_url)
            app.task_queue = Queue("webagent", connection=app.redis)
        except Exception:
            app.task_queue = None

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    @app.get("/")
    @app.get("/<path:path>")
    def spa(path="index.html"):
        if path.startswith("api/"):
            return {"error": "not found"}, 404
        if frontend_dist.exists():
            target = frontend_dist / path
            if target.is_file():
                return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, "index.html")
        return {"ok": True, "name": "web-agents"}

    with app.app_context():
        db.create_all()
        seed_admin(app)

    return app


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
