"""Common health/degraded-mode reporting for optional infrastructure."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ServiceHealth:
    name: str
    configured: bool
    available: bool = False
    state: str = "disabled"
    reason: str = ""
    latency_ms: float | None = None
    checked_at: str = field(default_factory=utc_now)

    @property
    def degraded(self) -> bool:
        return self.configured and not self.available

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "configured": self.configured,
            "available": self.available,
            "state": self.state,
            "degraded": self.degraded,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
        }


def unavailable(name: str, configured: bool, reason: str) -> ServiceHealth:
    return ServiceHealth(name=name, configured=configured, available=False, state="degraded" if configured else "disabled", reason=reason)
