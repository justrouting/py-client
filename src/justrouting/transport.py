"""HTTP transport: request execution, retries, backoff, and decoding."""

from __future__ import annotations

import email.utils
import itertools
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from .error import (
    DecodeError,
    Error,
    JustRoutingError,
    TransportError,
    UnauthorizedError,
    _MAX_ERROR_BODY_BYTES,
    _truncate,
    error_from_response,
)

# maxResponseBytes bounds how much of a response is read. A 500x500 matrix
# with both annotations is a few megabytes, so the limit is generous.
MAX_RESPONSE_BYTES = 32 << 20

# Retryable statuses: throttling and server errors. Client errors other
# than throttling will fail the same way every time and would still
# consume quota, so they are returned immediately.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUSES


def parse_retry_after(value: str) -> tuple:
    """Understand both forms of the Retry-After header: a delay in seconds,
    or an HTTP date. Returns (delay_seconds, ok)."""
    value = value.strip()
    if not value:
        return 0, False
    try:
        seconds = int(value)
    except ValueError:
        pass
    else:
        if seconds < 0:
            return 0, False
        return seconds, True
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return 0, False
    remaining = (dt - datetime.now(timezone.utc)).total_seconds()
    if remaining > 0:
        return remaining, True
    # A date in the past means "retry now".
    return 0, True


def default_backoff(attempt: int) -> float:
    """Exponential backoff from 500ms to a cap of 8s, with jitter to keep
    concurrent clients from retrying in lockstep."""
    base, max_delay = 0.5, 8.0
    attempt = max(attempt, 1)
    delay = max_delay
    if attempt <= 20:
        shifted = base * (1 << (attempt - 1))
        if shifted < max_delay:
            delay = shifted
    # Jitter across [delay/2, delay].
    half = delay / 2
    return half + random.random() * half


class Transport:
    """Executes requests for a Client: one attempt, retries, and decoding.

    The deadline (a monotonic timestamp, or None) bounds the whole retry
    sequence, like a Go context deadline. The client's per-attempt timeout
    applies to each individual HTTP attempt.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        user_agent: str,
        max_retries: int,
        backoff,
        timeout: Optional[float],
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout

    def do(
        self,
        method: str,
        path: str,
        *,
        query: Optional[dict] = None,
        body: Any = None,
        needs_auth: bool = False,
        model=None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Execute a request, retrying transient failures, and decode a
        successful response into the given model class (None to discard the
        body)."""
        if needs_auth and not self.api_key:
            raise UnauthorizedError(
                status_code=401,
                message="no API key configured; pass one to Client",
            )

        # Marshal once and replay the bytes on each attempt, so a retried
        # POST sends an identical body.
        data = None
        if body is not None:
            try:
                data = json.dumps(body, allow_nan=False).encode("utf-8")
            except (TypeError, ValueError) as e:
                raise Error(f"justrouting: encoding request body: {e}") from e

        endpoint = self._endpoint(path, query)
        deadline = time.monotonic() + timeout if timeout is not None else None

        last_err = None
        delay = 0.0
        headers = None
        for attempt in itertools.count():
            if attempt > 0:
                self._wait(delay, deadline)
            try:
                payload, status, headers = self._round_trip(method, endpoint, data, deadline)
            except TransportError as err:
                # A cancelled or expired deadline is final, not transient.
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("justrouting: deadline exceeded") from err
                last_err = err
            else:
                if 200 <= status < 300:
                    return self._decode(payload, model)
                api_err = error_from_response(status, payload)
                if not retryable_status(status):
                    raise api_err
                last_err = api_err

            if attempt >= self.max_retries:
                raise last_err
            delay = self._next_delay(attempt + 1, headers)

    def _round_trip(self, method, endpoint, data, deadline):
        """Perform one HTTP attempt and return (body, status, headers)."""
        timeout = self.timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("justrouting: deadline exceeded")
            if timeout is None or remaining < timeout:
                timeout = remaining

        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        if data is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as err:
            # HTTPError is a subclass of URLError and carries the response.
            payload = err.read(MAX_RESPONSE_BYTES + 1)
            try:
                err.close()
            except OSError:
                pass
            return payload[:MAX_RESPONSE_BYTES], err.code, err.headers
        except (urllib.error.URLError, OSError) as err:
            raise TransportError(f"justrouting: {method} {endpoint}: {err}") from err

        try:
            with resp:
                payload = resp.read(MAX_RESPONSE_BYTES + 1)
        except OSError as err:
            raise TransportError(f"justrouting: reading response: {err}") from err
        return payload[:MAX_RESPONSE_BYTES], resp.status, resp.headers

    def _decode(self, payload, model):
        """Parse a successful response and check any in-body status code,
        which both engines can use to report failure alongside HTTP 200."""
        if model is None:
            return None
        try:
            data = json.loads(payload)
        except ValueError as err:
            raise DecodeError(f"justrouting: decoding response: {err}") from err
        try:
            obj = model.from_dict(data)
        except JustRoutingError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            raise DecodeError(f"justrouting: decoding response: {err}") from err
        api_err = obj.api_error() if hasattr(obj, "api_error") else None
        if api_err is not None:
            api_err.body = _truncate(payload, _MAX_ERROR_BODY_BYTES)
            raise api_err
        return obj

    def _endpoint(self, path: str, query: Optional[dict]) -> str:
        """Build the absolute URL for a request path, preserving any path
        prefix on the configured base URL. The coordinate separators "," and
        ";" are legal in a path segment and must survive unescaped."""
        scheme, netloc, base_path, _, _ = urllib.parse.urlsplit(self.base_url)
        full_path = base_path.rstrip("/") + path
        query_string = urllib.parse.urlencode(query) if query else ""
        return urllib.parse.urlunsplit((scheme, netloc, full_path, query_string, ""))

    def _next_delay(self, attempt: int, headers) -> float:
        """How long to wait before the given retry attempt, preferring a
        Retry-After header when the server sends one."""
        if headers is not None:
            retry_after = headers.get("Retry-After")
            if retry_after:
                delay, ok = parse_retry_after(retry_after)
                if ok:
                    return delay
        return self.backoff(attempt)

    def _wait(self, delay: float, deadline) -> None:
        """Sleep for delay seconds, returning early if the deadline passes."""
        if delay <= 0:
            # Still observe the deadline when the delay is zero.
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("justrouting: deadline exceeded")
            return
        end = time.monotonic() + delay
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("justrouting: deadline exceeded")
            now = time.monotonic()
            if now >= end:
                return
            time.sleep(min(0.1, end - now))
