"""缓存抽象层。

对外只暴露一个 `cache` 对象，四种操作：get / set / delete / incr。

设计要点：
    有 Redis 就用 Redis；连不上自动退回进程内字典。
    这样本地开发不需要先把 Redis 跑起来，接口代码完全不用改。

    三种用途：
        1. 生成结果缓存 —— 同样的表单 30 分钟内不重复调模型
        2. 任务状态     —— plan:task:{id} = running / done / failed
        3. 接口限流     —— rate:{ip} 计数，超过阈值拒绝
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.config import REDIS_ENABLED, REDIS_URL


class _MemoryCache:
    """进程内缓存，带过期时间。只在没有 Redis 时使用。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expire_at = item
            if expire_at is not None and expire_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            self._data[key] = (value, time.time() + ttl if ttl else None)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl: int = 60) -> int:
        with self._lock:
            item = self._data.get(key)
            now = time.time()
            if item is None or (item[1] is not None and item[1] < now):
                self._data[key] = (1, now + ttl)
                return 1
            value, expire_at = item
            self._data[key] = (value + 1, expire_at)
            return value + 1


class Cache:
    """统一的缓存入口。"""

    def __init__(self) -> None:
        self._kind = "memory"
        self._client = None

        if REDIS_ENABLED:
            try:
                import redis  # 延迟导入，没装也不影响

                client = redis.Redis.from_url(
                    REDIS_URL, decode_responses=True, socket_connect_timeout=2
                )
                client.ping()
                self._client = client
                self._kind = "redis"
            except Exception as exc:  # 连不上就降级，不抛异常
                print(f"[cache] Redis 不可用，降级为内存缓存：{type(exc).__name__}")

        if self._client is None:
            self._client = _MemoryCache()

    @property
    def kind(self) -> str:
        return self._kind

    def get(self, key: str) -> Any:
        if self._kind == "redis":
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        return self._client.get(key)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if self._kind == "redis":
            self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        else:
            self._client.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def incr(self, key: str, ttl: int = 60) -> int:
        """自增计数，用于限流。"""
        if self._kind == "redis":
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl, nx=True)
            count, _ = pipe.execute()
            return int(count)
        return self._client.incr(key, ttl)


# 全局单例
cache = Cache()
