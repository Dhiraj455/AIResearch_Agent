"""
Fail-open key/value cache with TTL.

Uses Redis when REDIS_URL is set and reachable; otherwise (or whenever Redis
errors) falls back to an in-process TTL store so the pipeline never depends
on Redis being up.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

import redis

from src.config import settings

log = logging.getLogger(__name__)

_RETRY_REDIS_AFTER_S = 30


class _MemoryStore:
    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def setex(self, key: str, ttl_s: int, value: bytes) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl_s, value)

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            if item[0] < time.time():
                del self._data[key]
                return None
            return item[1]

    def keys(self, pattern: str) -> List[str]:
        now = time.time()
        with self._lock:
            return [k for k, (exp, _) in self._data.items() if exp >= now and fnmatch.fnmatchcase(k, pattern)]


class KV:
    def __init__(self) -> None:
        self._mem = _MemoryStore()
        self._redis: Optional[redis.Redis] = None
        self._down_until = 0.0
        if settings.REDIS_URL:
            # decode_responses=False => store bytes safely (PDF, etc.)
            self._redis = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=5,
            )
        else:
            log.warning("REDIS_URL not set; using in-process cache (data is lost on restart).")

    @property
    def backend(self) -> str:
        return "redis" if self._redis_ok() else "memory"

    def _redis_ok(self) -> bool:
        return self._redis is not None and time.time() >= self._down_until

    def _mark_down(self, e: Exception) -> None:
        log.warning("Redis unavailable (%s); falling back to in-process cache for %ss.", e, _RETRY_REDIS_AFTER_S)
        self._down_until = time.time() + _RETRY_REDIS_AFTER_S

    def setex(self, key: str, ttl_s: int, value: bytes) -> None:
        if self._redis_ok():
            try:
                self._redis.setex(key, ttl_s, value)
                return
            except redis.RedisError as e:
                self._mark_down(e)
        self._mem.setex(key, ttl_s, value)

    def get(self, key: str) -> Optional[bytes]:
        if self._redis_ok():
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    return raw
            except redis.RedisError as e:
                self._mark_down(e)
        return self._mem.get(key)

    def keys(self, pattern: str) -> List[str]:
        found = set(self._mem.keys(pattern))
        if self._redis_ok():
            try:
                found.update(k.decode("utf-8") for k in self._redis.scan_iter(match=pattern, count=500))
            except redis.RedisError as e:
                self._mark_down(e)
        return sorted(found)


kv = KV()
