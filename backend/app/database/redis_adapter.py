"""Optional Redis client with bounded health checks and explicit degradation."""
from __future__ import annotations

import time
from typing import Any

from .health import ServiceHealth, unavailable


class RedisAdapter:
    def __init__(self, url: str, timeout: float = 0.5) -> None:
        self.url = url.strip()
        self.timeout = timeout
        self._client: Any = None
        self.health = self._initial_health()

    def _initial_health(self) -> ServiceHealth:
        if not self.url:
            return unavailable("redis", False, "REDIS_URL is not configured")
        try:
            import redis  # type: ignore
        except ImportError:
            return unavailable("redis", True, "redis package is not installed")
        try:
            self._client = redis.Redis.from_url(
                self.url,
                socket_connect_timeout=self.timeout,
                socket_timeout=self.timeout,
                health_check_interval=30,
                decode_responses=True,
            )
            started = time.monotonic()
            self._client.ping()
            self.health = ServiceHealth("redis", True, True, "ready", latency_ms=round((time.monotonic() - started) * 1000, 2))
        except Exception as exc:  # ConnectionError varies by redis client version.
            self.health = unavailable("redis", True, f"Redis health check failed: {type(exc).__name__}: {exc}")
            self._client = None
        return self.health

    @property
    def available(self) -> bool:
        return self.health.available and self._client is not None

    def health_check(self) -> ServiceHealth:
        if self._client is None:
            return self.health
        try:
            started = time.monotonic()
            self._client.ping()
            self.health = ServiceHealth("redis", True, True, "ready", latency_ms=round((time.monotonic() - started) * 1000, 2))
        except Exception as exc:
            self.health = unavailable("redis", True, f"Redis health check failed: {type(exc).__name__}: {exc}")
        return self.health

    def get(self, key: str) -> Any:
        if not self.available:
            raise RuntimeError("Redis is unavailable; cache operation was not performed")
        return self._client.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        if not self.available:
            raise RuntimeError("Redis is unavailable; cache operation was not performed")
        return bool(self._client.set(key, value, ex=ex))

    def close(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if close is not None:
                close()
            self._client = None
