from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque


class MemoryBus:
    def __init__(self):
        self._channels: dict[str, deque] = defaultdict(lambda: deque(maxlen=2000))
        self._lock = threading.Lock()

    def publish(self, channel: str, event: dict) -> None:
        with self._lock:
            self._channels[channel].append(event)

    def history(self, channel: str) -> list[dict]:
        with self._lock:
            return list(self._channels[channel])

    def listen(self, channel: str, after_id: int = 0, timeout: float = 25.0):
        deadline = time.time() + timeout
        last = after_id
        while time.time() < deadline:
            with self._lock:
                events = [e for e in self._channels[channel] if int(e.get("seq", 0)) > last]
            if events:
                return events
            time.sleep(0.3)
        return []


class RedisBus:
    def __init__(self, redis_client):
        self.redis = redis_client

    def publish(self, channel: str, event: dict) -> None:
        self.redis.rpush(channel, json.dumps(event, ensure_ascii=False))
        self.redis.expire(channel, 7 * 24 * 3600)
        self.redis.publish(f"{channel}:pub", json.dumps(event, ensure_ascii=False))

    def history(self, channel: str) -> list[dict]:
        items = self.redis.lrange(channel, 0, -1)
        out = []
        for raw in items:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            out.append(json.loads(raw))
        return out

    def listen(self, channel: str, after_id: int = 0, timeout: float = 25.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            events = [e for e in self.history(channel) if int(e.get("seq", 0)) > after_id]
            if events:
                return events
            time.sleep(0.4)
        return []


def create_bus(app):
    url = app.config.get("REDIS_URL") or ""
    if not url:
        return MemoryBus()
    try:
        from .redis_client import from_url as redis_from_url

        client = redis_from_url(url)
        client.ping()
        return RedisBus(client)
    except Exception:
        return MemoryBus()
