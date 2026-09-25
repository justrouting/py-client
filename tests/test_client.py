"""Port of client_test.go."""

import pytest

import justrouting
from conftest import (
    OK_HEALTH,
    OK_ROUTE,
    TEST_API_KEY,
    json_handler,
    new_test_client,
    simple_route,
    serve,
)


def test_client_defaults():
    c = justrouting.Client("key")

    assert c.base_url() == justrouting.DEFAULT_BASE_URL
    assert c._transport.max_retries == 2
    assert c._transport.user_agent == f"justrouting-py/{justrouting.VERSION}"
    assert c.routes is not None
    assert c.matrix is not None
    assert c.map_matching is not None
    assert c.trip is not None
    assert c.nearest is not None
    assert c.geocode is not None
    assert c.optimization is not None
    assert c.health is not None


def test_client_trims_api_key():
    c = justrouting.Client("  spaced-key\n")
    assert c._transport.api_key == "spaced-key"


def test_options_validation():
    # Invalid options raise immediately; Python constructors can fail, so
    # there is no deferred initErr like the Go client carries.
    with pytest.raises(ValueError):
        justrouting.Client("k", base_url="localhost:8080")
    with pytest.raises(ValueError):
        justrouting.Client("k", base_url="  ")
    with pytest.raises(ValueError):
        justrouting.Client("k", user_agent="")
    with pytest.raises(ValueError):
        justrouting.Client("k", max_retries=-1)
    with pytest.raises(ValueError):
        justrouting.Client("k", backoff="not-a-callable")
    with pytest.raises(ValueError):
        justrouting.Client("k", timeout=0)

    # Trailing slashes and path prefixes are preserved.
    assert justrouting.Client("k", base_url="http://localhost:8080/").base_url() == (
        "http://localhost:8080/"
    )


def test_request_headers():
    seen = {}

    def handler(req):
        seen["headers"] = req.headers
        return 200, OK_ROUTE, {}

    with new_test_client(handler, user_agent="test-agent/1.0") as c:
        c.routes.get(simple_route())

    headers = seen["headers"]
    assert headers.get("Authorization") == "Bearer " + TEST_API_KEY
    assert headers.get("User-Agent") == "test-agent/1.0"
    assert headers.get("Accept") == "application/json"
    # GET requests carry no body, so no Content-Type should be sent.
    assert headers.get("Content-Type") is None


def test_missing_api_key_fails_fast():
    called = []

    def handler(req):
        called.append(req)
        return 200, OK_ROUTE, {}

    with serve(handler) as base_url:
        c = justrouting.Client("", base_url=base_url)
        with pytest.raises(justrouting.UnauthorizedError):
            c.routes.get(simple_route())

    assert called == [], "no request should have been sent"


def test_health_works_without_api_key():
    body = (
        '{"status":"ok","timestamp":"2026-08-26T12:00:00Z",'
        '"upstreams":{"osrm":true,"vroom":true}}'
    )
    with serve(json_handler(200, body)) as base_url:
        c = justrouting.Client("", base_url=base_url)
        health = c.health.get()
    assert health.ok() is True
    assert health.upstreams["osrm"] is True


def test_health_degraded():
    body = (
        '{"status":"degraded","timestamp":"2026-08-26T12:00:00Z",'
        '"upstreams":{"osrm":true,"vroom":false}}'
    )
    with new_test_client(json_handler(200, body)) as c:
        health = c.health.get()
    assert health.ok() is False


def test_base_url_path_prefix_is_preserved():
    seen = {}

    def handler(req):
        seen["path"] = req.url_path()
        return 200, OK_HEALTH, {}

    with serve(handler) as base_url:
        c = justrouting.Client(TEST_API_KEY, base_url=base_url + "/gateway")
        c.health.get()

    assert seen["path"] == "/gateway/health"
