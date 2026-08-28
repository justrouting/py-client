"""Port of transport_test.go: error classification, retries, backoff."""

import time

import pytest

import justrouting
from conftest import OK_ROUTE, json_handler, new_test_client, simple_optimization, simple_route

# Every error shape the API can produce must map onto the right exception,
# so callers never have to match on message strings themselves.
ERROR_CASES = [
    # name, status, body, content_type, want, not_want, message
    (
        "unauthorized",
        401,
        '{"error":"invalid or revoked API key"}',
        "",
        [justrouting.UnauthorizedError],
        # A 401 is not a throttle; misclassifying it would send callers
        # into a pointless retry loop.
        [justrouting.RateLimitedError],
        "invalid or revoked API key",
    ),
    (
        "rate limited per second",
        429,
        '{"error":"rate limit exceeded (RPS)"}',
        "",
        [justrouting.RateLimitedError],
        [justrouting.QuotaExceededError],
        "rate limit exceeded (RPS)",
    ),
    (
        "daily quota exhausted",
        429,
        '{"error":"daily quota exceeded (limit 100)"}',
        "",
        # Quota is a kind of throttling, so both classes match.
        [justrouting.QuotaExceededError, justrouting.RateLimitedError],
        [],
        "daily quota exceeded (limit 100)",
    ),
    (
        "cross-country request",
        400,
        '{"error":"cross-country request not supported"}',
        "",
        [justrouting.CrossCountryError],
        [],
        "cross-country request not supported",
    ),
    (
        "matrix exceeds plan",
        400,
        '{"error":"matrix size exceeds plan limit"}',
        "",
        [justrouting.PlanLimitExceededError],
        [],
        "matrix size exceeds plan limit",
    ),
    (
        "too many jobs",
        400,
        '{"error":"too many jobs"}',
        "",
        [justrouting.PlanLimitExceededError],
        [],
        "too many jobs",
    ),
    (
        "unparseable coordinates",
        400,
        '{"error":"cannot parse coordinates"}',
        "",
        [justrouting.InvalidCoordinatesError],
        [],
        "cannot parse coordinates",
    ),
    (
        "upstream down",
        502,
        '{"error":"upstream unavailable"}',
        "",
        [justrouting.UpstreamUnavailableError],
        [],
        "upstream unavailable",
    ),
    (
        # Some handlers use http.Error, which stamps text/plain on a body
        # that is still JSON. Classification must key off the body shape,
        # not the header.
        "json body sent as text/plain",
        400,
        '{"error":"cross-country request not supported"}\n',
        "text/plain; charset=utf-8",
        [justrouting.CrossCountryError],
        [],
        "cross-country request not supported",
    ),
    (
        "routing engine reports no route",
        400,
        '{"code":"NoRoute","message":"Impossible route between points"}',
        "",
        [justrouting.NoRouteError],
        [],
        "Impossible route between points",
    ),
    (
        "non-json body falls back to its text",
        400,
        "something went wrong",
        "",
        [],
        [],
        "something went wrong",
    ),
]


@pytest.mark.parametrize(
    "name,status,body,content_type,want,not_want,want_msg", ERROR_CASES
)
def test_error_classification(name, status, body, content_type, want, not_want, want_msg):
    def handler(req):
        headers = {"Content-Type": content_type} if content_type else {}
        return status, body, headers

    with new_test_client(handler, max_retries=0) as c:
        with pytest.raises(justrouting.Error) as excinfo:
            c.routes.get(simple_route())

    err = excinfo.value
    for cls in want:
        assert isinstance(err, cls), f"{name}: err = {err!r}"
    for cls in not_want:
        assert not isinstance(err, cls), f"{name}: err = {err!r}"
    assert err.status_code == status
    if want_msg:
        assert err.message == want_msg
    assert err.body, "body should retain the raw response"


def test_routing_failure_at_http_200():
    body = '{"code":"NoRoute","message":"Impossible route between points"}'
    with new_test_client(json_handler(200, body)) as c:
        with pytest.raises(justrouting.NoRouteError) as excinfo:
            c.routes.get(simple_route())
    assert excinfo.value.osrm_code == "NoRoute"
    assert excinfo.value.status_code == 200


def test_optimization_failure_at_http_200():
    with new_test_client(json_handler(200, '{"code":3,"error":"Invalid profile"}')) as c:
        with pytest.raises(justrouting.Error) as excinfo:
            c.optimization.solve(simple_optimization())
    err = excinfo.value
    assert err.vroom_code == 3
    assert err.message == "Invalid profile"


def test_optimization_success_code_zero():
    body = '{"code":0,"summary":{"cost":42,"routes":1},"routes":[{"vehicle":1,"steps":[]}],"unassigned":[]}'
    with new_test_client(json_handler(200, body)) as c:
        solution = c.optimization.solve(simple_optimization())
    assert solution.summary.cost == 42


def test_retry_on_rate_limit_then_success():
    attempts = []

    def handler(req):
        attempts.append(req)
        if len(attempts) == 1:
            return 429, '{"error":"rate limit exceeded (RPS)"}', {}
        return 200, OK_ROUTE, {}

    with new_test_client(handler) as c:
        route = c.routes.get(simple_route())
    assert route.distance == 100
    assert len(attempts) == 2


def test_retries_exhausted_returns_last_error():
    attempts = []

    def handler(req):
        attempts.append(req)
        return 502, '{"error":"upstream unavailable"}', {}

    with new_test_client(handler, max_retries=2) as c:
        with pytest.raises(justrouting.UpstreamUnavailableError):
            c.routes.get(simple_route())
    # One initial attempt plus two retries.
    assert len(attempts) == 3


def test_client_error_is_not_retried():
    attempts = []

    def handler(req):
        attempts.append(req)
        return 400, '{"error":"cross-country request not supported"}', {}

    with new_test_client(handler, max_retries=3) as c:
        with pytest.raises(justrouting.CrossCountryError):
            c.routes.get(simple_route())
    assert len(attempts) == 1


def test_retries_disabled():
    attempts = []

    def handler(req):
        attempts.append(req)
        return 500, "", {}

    with new_test_client(handler, max_retries=0) as c:
        with pytest.raises(justrouting.Error):
            c.routes.get(simple_route())
    assert len(attempts) == 1


def test_post_body_is_replayed_on_retry():
    attempts = []
    bodies = []

    def handler(req):
        bodies.append(req.read_body())
        attempts.append(req)
        if len(attempts) == 1:
            return 500, "", {}
        return 200, '{"code":0,"summary":{},"routes":[],"unassigned":[]}', {}

    with new_test_client(handler) as c:
        c.optimization.solve(simple_optimization())

    assert len(bodies) == 2
    assert bodies[0], "first request body was empty"
    assert bodies[0] == bodies[1], "replayed body differs"


def test_post_sends_json_content_type():
    seen = {}

    def handler(req):
        seen["content_type"] = req.headers.get("Content-Type")
        return 200, '{"code":0,"summary":{},"routes":[],"unassigned":[]}', {}

    with new_test_client(handler) as c:
        c.optimization.solve(simple_optimization())
    assert seen["content_type"] == "application/json"


def test_timeout_interrupts_backoff():
    attempts = []

    def handler(req):
        attempts.append(req)
        return 500, "", {}

    with new_test_client(
        handler, max_retries=5, backoff=lambda attempt: 3600.0
    ) as c:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            c.routes.get(simple_route(), timeout=0.05)

    assert time.monotonic() - start < 5, "timeout did not interrupt the backoff sleep"


def test_timeout_mid_flight():
    def handler(req):
        time.sleep(1)
        return 200, OK_ROUTE, {}

    with new_test_client(handler, max_retries=2) as c:
        with pytest.raises(TimeoutError):
            c.routes.get(simple_route(), timeout=0.05)


def test_transport_error_is_retried():
    attempts = []

    def handler(req):
        attempts.append(req)
        if len(attempts) == 1:
            # Break the connection without a response, like the hijacked
            # connection in the Go transport test.
            req.abort()
        return 200, OK_ROUTE, {}

    with new_test_client(handler) as c:
        route = c.routes.get(simple_route())
    assert route.distance == 100
    assert len(attempts) == 2


def test_parse_retry_after():
    from justrouting.transport import parse_retry_after

    cases = [
        ("", 0, False),
        ("   ", 0, False),
        ("5", 5, True),
        ("0", 0, True),
        ("-3", 0, False),
        ("not-a-number", 0, False),
        # A date in the past means "retry now".
        ("Mon, 02 Jan 2006 15:04:05 GMT", 0, True),
    ]
    for value, want, want_ok in cases:
        got, ok = parse_retry_after(value)
        assert ok == want_ok, f"value {value!r}: ok = {ok}, want {want_ok}"
        if ok:
            assert got == want, f"value {value!r}: delay = {got}, want {want}"


def test_retry_after_header_is_honoured():
    attempts = []

    def handler(req):
        attempts.append(req)
        if len(attempts) == 1:
            return 429, '{"error":"rate limit exceeded (RPS)"}', {"Retry-After": "0"}
        return 200, OK_ROUTE, {}

    def backoff(attempt):
        raise AssertionError("backoff should not be consulted when Retry-After is present")

    with new_test_client(handler, backoff=backoff) as c:
        c.routes.get(simple_route())


def test_default_backoff_grows_and_is_capped():
    from justrouting.transport import default_backoff

    for attempt in range(1, 5):
        d = default_backoff(attempt)
        assert 0 < d <= 8, f"attempt {attempt}: delay = {d}"

    # Very large attempt counts must stay bounded.
    assert 0 < default_backoff(1000) <= 8
    assert default_backoff(0) > 0


def test_malformed_json_response():
    with new_test_client(json_handler(200, '{"code":"Ok","routes":')) as c:
        with pytest.raises(justrouting.DecodeError):
            c.routes.get(simple_route())
