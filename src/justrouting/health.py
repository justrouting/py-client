"""The Health service: API availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

__all__ = ["HealthService", "Health"]


@dataclass
class Health:
    """The API's self-reported status.

    Attributes:
        status: "ok" when every upstream is reachable, otherwise
            "degraded".
        timestamp: When the check ran, in RFC 3339 format.
        upstreams: Maps each routing engine to its reachability.
    """

    status: str = ""
    timestamp: str = ""
    upstreams: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Health":
        return cls(
            status=d.get("status", ""),
            timestamp=d.get("timestamp", ""),
            upstreams=d.get("upstreams") or {},
        )

    def ok(self) -> bool:
        """Whether every upstream is healthy."""
        return self.status == "ok"


class HealthService:
    """Reports API availability."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(self, *, timeout: Optional[float] = None) -> Health:
        """The current API status. It is the only call that works without
        an API key, which makes it useful as a connectivity check."""
        return self._client.do("GET", "/health", model=Health, timeout=timeout)
