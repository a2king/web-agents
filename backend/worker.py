"""RQ worker：后台执行会话任务。

    REDIS_URL=redis://127.0.0.1:6379/0 python worker.py
"""

from __future__ import annotations

from rq import Worker

from app import create_app
from app.jobs import set_worker_app
from app.redis_client import from_url as redis_from_url


def main():
    app = create_app()
    set_worker_app(app)
    conn = redis_from_url(app.config["REDIS_URL"])
    with app.app_context():
        print("worker started", flush=True)
        Worker(["webagent"], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
