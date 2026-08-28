"""The JustRouting client.

A client is created with an API key and, optionally, keyword options::

    client = justrouting.Client("YOUR_API_KEY")

    route = client.routes.get(justrouting.RouteRequest(
        origin=[103.8198, 1.3521],
        destination=[103.9915, 1.3644],
    ))
    print(f"Distance: {route.distance / 1000:.1f} km")

Coordinates are always [longitude, latitude], the order used by GeoJSON,
OSRM and VROOM. Every call accepts an optional ``timeout`` argument in
seconds that bounds the whole retry sequence, like a context deadline in
the Go client.

Failed calls raise a subclass of [justrouting.Error]. Use ``except`` clauses
for control flow and [justrouting.Error] when the status code or raw body is
needed::

    try:
        route = client.routes.get(req)
    except justrouting.RateLimitedError:
        # back off and retry later

Unlike the Go client, invalid constructor options raise ``ValueError``
immediately — Python constructors can fail, so there is no need to defer
the error to the first request.

The package has no dependencies outside the standard library.
"""

from __future__ import annotations

import urllib.parse
from typing import Callable, Optional

from .consts import DEFAULT_BASE_URL, DEFAULT_PROFILE, VERSION
from .health import HealthService
from .matrix import MatrixService
from .optimization import OptimizationService
from .routes import RoutesService
from .transport import Transport, default_backoff

__all__ = [
    "Client",
    "VERSION",
    "DEFAULT_BASE_URL",
    "DEFAULT_PROFILE",
]

_DEFAULT_MAX_RETRIES = 2
_DEFAULT_TIMEOUT = 30.0


def _validate_base_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("justrouting: base_url must not be empty")
    parts = urllib.parse.urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"justrouting: base_url {raw!r} is not an absolute URL")
    return raw


class Client:
    """A JustRouting API client.

    It is safe for concurrent use by multiple threads, and should be created
    once and reused.

    Args:
        api_key: The API key, sent as an ``Authorization: Bearer`` header on
            every request that needs it. An empty key is allowed but only
            [HealthService.get] will work; every other call fails with
            [UnauthorizedError] before any request is sent.
        base_url: The API endpoint, default [DEFAULT_BASE_URL]. Target a
            local or staging server with ``base_url="http://localhost:8080"``.
            Any path is kept as a prefix for every request.
        user_agent: Override the User-Agent header. Identifying your
            application helps when diagnosing traffic against the API.
        max_retries: How many times a failed request is retried, on top of
            the initial attempt. The default is 2. Pass 0 to disable
            retries. Only rate-limit (429), server (5xx) and transport
            errors are retried; other 4xx responses are returned immediately.
        backoff: Callable(attempt: int) -> float returning the delay in
            seconds before retry ``attempt`` (1 for the first retry, 2 for
            the second, and so on). The default is exponential backoff with
            jitter, starting at 500ms and capped at 8s. A Retry-After
            response header, when present, takes precedence.
        timeout: Seconds allowed for a single HTTP attempt, like
            ``http.Client.Timeout`` in Go. The default is 30. Use the
            per-call ``timeout`` argument instead to bound the whole retry
            sequence.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: Optional[str] = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff: Optional[Callable[[int], float]] = None,
        timeout: Optional[float] = _DEFAULT_TIMEOUT,
    ) -> None:
        if max_retries < 0:
            raise ValueError(
                f"justrouting: max_retries must not be negative, got {max_retries}"
            )
        if user_agent is not None and not user_agent.strip():
            raise ValueError("justrouting: user_agent must not be empty")
        if backoff is not None and not callable(backoff):
            raise ValueError("justrouting: backoff must be a callable")
        if timeout is not None and timeout <= 0:
            raise ValueError("justrouting: timeout must be positive or None")

        self._transport = Transport(
            api_key=api_key.strip(),
            base_url=_validate_base_url(base_url),
            user_agent=user_agent or f"justrouting-py/{VERSION}",
            max_retries=max_retries,
            backoff=backoff or default_backoff,
            timeout=timeout,
        )

        # Routes computes routes between two or more coordinates.
        self.routes = RoutesService(self._transport)
        # Matrix computes duration and distance matrices.
        self.matrix = MatrixService(self._transport)
        # Optimization solves vehicle routing problems.
        self.optimization = OptimizationService(self._transport)
        # Health reports API and upstream availability.
        self.health = HealthService(self._transport)

    def base_url(self) -> str:
        """The API endpoint the client sends requests to."""
        return self._transport.base_url
