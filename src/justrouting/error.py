"""Errors raised by the JustRouting client.

The Go client classifies failures with sentinel errors and ``errors.Is``.
Python expresses the same classification as an exception hierarchy, so
callers use ``except`` clauses instead of string matching::

    try:
        route = client.routes.get(req)
    except justrouting.QuotaExceededError:
        # daily allowance used up — retrying will not help
    except justrouting.RateLimitedError:
        # throttled; the client already retried
    except justrouting.CrossCountryError:
        # coordinates span more than one country
    except justrouting.NoRouteError:
        # no road connects these points

``QuotaExceededError`` is a subclass of ``RateLimitedError``, mirroring how
the Go client reports a daily-quota response as both
``ErrQuotaExceeded`` and ``ErrRateLimited``.

Every API failure — non-2xx responses and in-body engine failures alike —
raises an ``Error`` (or one of its subclasses). Catch it when the status
code, engine code, or raw body is needed::

    except justrouting.Error as e:
        log("HTTP %d: %s\n%s", e.status_code, e.message, e.body)

``Error`` carries the same fields as the Go ``*Error`` struct. Failures
that never produced an API response (local validation, transport, decoding)
raise ``InvalidRequestError``, ``TransportError`` or ``DecodeError``
instead, which are *not* subclasses of ``Error``.
"""

import http.client
import json

__all__ = [
    "JustRoutingError",
    "Error",
    "UnauthorizedError",
    "RateLimitedError",
    "QuotaExceededError",
    "PlanLimitExceededError",
    "CrossCountryError",
    "InvalidCoordinatesError",
    "NoRouteError",
    "UpstreamUnavailableError",
    "InvalidRequestError",
    "TransportError",
    "DecodeError",
]

# maxErrorBodyBytes bounds how much of a response body is retained on an
# Error, so that a large or misbehaving upstream cannot balloon a log line.
_MAX_ERROR_BODY_BYTES = 8 << 10


class JustRoutingError(Exception):
    """Base class of every error raised by this package."""


class Error(JustRoutingError):
    """A failed API call.

    It is raised whenever the API responds with a non-2xx status, and also
    when a 2xx response carries an in-body failure code — the routing and
    optimization engines can both report errors alongside HTTP 200.

    Attributes:
        status_code: The HTTP status of the response. Zero for errors that
            were produced without an HTTP response, such as local validation.
        message: The human-readable reason reported by the API.
        osrm_code: The routing engine's status code, such as ``"NoRoute"``
            or ``"InvalidValue"``. Empty when the error did not come from
            the routing engine.
        vroom_code: The optimization engine's non-zero status code. Zero
            when the error did not come from the optimization engine.
        body: The raw response body, truncated to a sane limit. Useful for
            logging responses this package does not model.
    """

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int = 0,
        osrm_code: str = "",
        vroom_code: int = 0,
        body: bytes = b"",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.osrm_code = osrm_code
        self.vroom_code = vroom_code
        self.body = body

    def __str__(self) -> str:
        # A zero status means the error was produced without an HTTP
        # response; the message then already carries the full text.
        if self.status_code == 0:
            return self.message
        parts = ["justrouting: "]
        parts.append(f"HTTP {self.status_code}")
        if self.osrm_code:
            parts.append(f" ({self.osrm_code})")
        elif self.vroom_code:
            parts.append(f" (optimization code {self.vroom_code})")
        if self.message:
            parts.append(f": {self.message}")
        return "".join(parts)


class UnauthorizedError(Error):
    """The API key is missing, invalid or revoked."""


class RateLimitedError(Error):
    """The request was throttled (per-second limit or daily quota)."""


class QuotaExceededError(RateLimitedError):
    """The plan's daily request quota is used up.

    Retrying before the quota resets will not help. Subclasses
    ``RateLimitedError`` because quota exhaustion is a form of throttling.
    """


class PlanLimitExceededError(Error):
    """The request is larger than the plan allows — too many matrix
    coordinates, jobs, or vehicles."""


class CrossCountryError(Error):
    """The coordinates span more than one country.

    Every coordinate in a request must fall within a single country.
    """


class InvalidCoordinatesError(Error):
    """A coordinate was malformed, out of range, or could not be parsed."""


class NoRouteError(Error):
    """No route exists between the given coordinates."""


class UpstreamUnavailableError(Error):
    """The routing engine behind the API could not be reached.

    This is usually transient.
    """


class InvalidRequestError(Error):
    """The request was rejected before being sent because required fields
    were missing or inconsistent.

    These errors carry no HTTP status; the message holds the reason.
    """


class TransportError(JustRoutingError):
    """A network-level failure while contacting the API.

    The original exception is available as ``__cause__``. Transport errors
    are transient and are retried like 429 and 5xx responses.
    """


class DecodeError(JustRoutingError):
    """A successful response could not be decoded.

    The original exception is available as ``__cause__``.
    """


def _truncate(body: bytes, max_bytes: int) -> bytes:
    if len(body) <= max_bytes:
        return body
    return body[:max_bytes]


def osrm_status_error(code: str, message: str) -> "Error | None":
    """Convert a routing engine status code into an Error, or None when the
    response was successful."""
    if not code or code.lower() == "ok":
        return None
    if not message:
        message = f"routing engine returned {code}"
    cls = _classify_error(http.client.OK, message, code)
    return cls(status_code=http.client.OK, osrm_code=code, message=message)


def error_from_response(status_code: int, body: bytes) -> "Error":
    """Build the right Error subclass for an HTTP error response.

    Bodies are classified by shape rather than Content-Type: some API
    handlers emit a JSON body while leaving the header set to text/plain.
    """
    message, osrm_code, vroom_code = "", "", 0

    payload = None
    try:
        stripped = body.strip()
        if stripped:
            payload = json.loads(stripped)
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        # {"error": ...}                       gateway errors
        # {"code": "NoRoute", "message": ...}  routing engine (string code)
        # {"code": 3, "error": ...}            optimization engine (int code)
        message = payload.get("error") or payload.get("message") or ""
        code = payload.get("code")
        if isinstance(code, str) and code.lower() != "ok":
            osrm_code = code
        elif isinstance(code, int):
            vroom_code = code

    if not message:
        message = _fallback_message(status_code, body)

    cls = _classify_error(status_code, message, osrm_code)
    return cls(
        status_code=status_code,
        message=message,
        osrm_code=osrm_code,
        vroom_code=vroom_code,
        body=_truncate(body, _MAX_ERROR_BODY_BYTES),
    )


def _classify_error(status_code: int, message: str, osrm_code: str):
    """Pick the exception class for a failure, in the same priority order
    the Go client's Error.Is uses."""
    msg = message.lower()
    if status_code == http.client.UNAUTHORIZED:
        return UnauthorizedError
    if status_code == http.client.TOO_MANY_REQUESTS:
        if "daily quota" in msg:
            return QuotaExceededError
        return RateLimitedError
    if status_code == http.client.BAD_GATEWAY or "upstream unavailable" in msg:
        return UpstreamUnavailableError
    if "cross-country" in msg:
        return CrossCountryError
    if "exceeds plan limit" in msg or "too many jobs" in msg or "too many vehicles" in msg:
        return PlanLimitExceededError
    if osrm_code.lower() == "noroute":
        return NoRouteError
    if "cannot parse coordinates" in msg or "invalid coordinates" in msg:
        return InvalidCoordinatesError
    return Error


def _fallback_message(status_code: int, body: bytes) -> str:
    """Produce a message for responses with no recognisable error field,
    such as an HTML error page from an intermediary proxy."""
    s = body.decode("utf-8", errors="replace").strip()
    if s and not s.startswith("{") and not s.startswith("<") and len(s) <= 200:
        return s
    if text := http.client.responses.get(status_code, ""):
        return text.lower()
    return "unexpected response"
