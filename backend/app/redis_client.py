"""Redis 客户端。RQ 2.x 会用多字段 HSET，Redis 3.x 不支持，需回退到 HMSET。"""

from __future__ import annotations

import logging

from redis import Redis
from redis.client import Pipeline

logger = logging.getLogger(__name__)

_hset_patched = False


def _parse_version(raw: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for token in str(raw).split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits or 0))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def _redis_version(client: Redis) -> str:
    try:
        return str(client.info("server").get("redis_version") or "0.0.0")
    except Exception:
        return "0.0.0"


def _needs_legacy_hset(client: Redis) -> bool:
    return _parse_version(_redis_version(client)) < (4, 0, 0)


def _compat_hset(self, name, key=None, value=None, mapping=None, items=None):
    data = {}
    if key is not None:
        data[key] = value
    if mapping:
        data.update(mapping)
    if items:
        seq = list(items)
        if len(seq) % 2 != 0:
            raise ValueError("hset items must contain field/value pairs")
        data.update(dict(zip(seq[::2], seq[1::2])))
    if not data:
        return 0
    if len(data) == 1:
        field, val = next(iter(data.items()))
        return self.execute_command("HSET", name, field, val)
    pairs: list = []
    for field, val in data.items():
        pairs.extend((field, val))
    # redis-py 5 的 hmset() 内部仍会调用多字段 HSET，必须直接发 HMSET
    return self.execute_command("HMSET", name, *pairs)


def _patch_hset_for_redis3() -> None:
    global _hset_patched
    if _hset_patched:
        return
    Redis.hset = _compat_hset  # type: ignore[method-assign]
    Pipeline.hset = _compat_hset  # type: ignore[method-assign]
    _hset_patched = True


def from_url(url: str, **kwargs) -> Redis:
    client = Redis.from_url(url, **kwargs)
    version = _redis_version(client)
    if _needs_legacy_hset(client):
        logger.warning("Redis %s 不支持多字段 HSET，已回退为 HMSET", version)
        _patch_hset_for_redis3()
    return client
