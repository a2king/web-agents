"""RQ worker + 自动化调度。

    REDIS_URL=redis://127.0.0.1:6379/0 python worker.py
"""

from __future__ import annotations

import time

from rq import Worker

from app import create_app
from app.jobs import drain_token_queue, set_worker_app, tick_automations
from app.redis_client import from_url as redis_from_url


def main():
    app = create_app()
    set_worker_app(app)
    redis_url = app.config["REDIS_URL"]
    conn = redis_from_url(redis_url)
    with app.app_context():
        print("worker started", flush=True)
        last_tick = 0
        worker = Worker(["webagent"], connection=conn)
        # 简易调度：穿插 cron 检查
        while True:
            now = time.time()
            if now - last_tick > 30:
                tick_automations()
                drain_token_queue()
                last_tick = now
            worker.work(burst=True, with_scheduler=False)
            time.sleep(2)


if __name__ == "__main__":
    main()
