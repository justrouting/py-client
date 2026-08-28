"""Integration tests run against a live API and are excluded from the
default suite (``pytest -m integration`` includes them).

Health and auth work without credentials; the rest need:

    JUSTROUTING_API_KEY=<key> pytest -m integration

Set JUSTROUTING_BASE_URL to target a local server instead of production.
"""

import os

import pytest

import justrouting

pytestmark = pytest.mark.integration


def integration_client():
    kwargs = {}
    base = os.environ.get("JUSTROUTING_BASE_URL")
    if base:
        kwargs["base_url"] = base
    return justrouting.Client(os.environ.get("JUSTROUTING_API_KEY", ""), **kwargs)


def require_api_key():
    if not os.environ.get("JUSTROUTING_API_KEY"):
        pytest.skip("set JUSTROUTING_API_KEY to run this test")


# Health needs no credentials, so it doubles as a connectivity check.
def test_integration_health():
    health = integration_client().health.get(timeout=30)
    assert health.status != ""
    assert health.timestamp != ""
    assert len(health.upstreams) > 0
    print(f"status={health.status} upstreams={health.upstreams}")
    if not health.ok():
        pytest.skip(f"API reports {health.status!r}; skipping routing assertions")


# An absent key must be rejected by the API, confirming the client sends the
# header in the form the API expects.
def test_integration_unauthorized():
    kwargs = {}
    base = os.environ.get("JUSTROUTING_BASE_URL")
    if base:
        kwargs["base_url"] = base
    client = justrouting.Client("definitely-not-a-valid-key", **kwargs)

    with pytest.raises(justrouting.UnauthorizedError):
        client.routes.get(
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521], destination=[103.9915, 1.3644]
            ),
            timeout=30,
        )


def test_integration_route():
    require_api_key()
    # Marina Bay to Changi Airport, both in Singapore.
    route = integration_client().routes.get(
        justrouting.RouteRequest(
            origin=[103.8198, 1.3521],
            destination=[103.9915, 1.3644],
            overview="full",
        ),
        timeout=30,
    )

    assert route.distance > 0
    assert route.duration > 0
    assert not route.geometry.is_zero()
    route.geometry.polyline()  # must not raise
    print(f"{route.distance / 1000:.2f} km in {route.duration / 60:.0f} min")


# The API routes each request to a per-country engine, so a request spanning
# two countries is rejected.
def test_integration_cross_country_rejected():
    require_api_key()
    # Singapore to Kuala Lumpur.
    with pytest.raises(justrouting.CrossCountryError):
        integration_client().routes.get(
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521], destination=[101.6869, 3.1390]
            ),
            timeout=30,
        )


def test_integration_matrix():
    require_api_key()
    m = integration_client().matrix.get(
        justrouting.MatrixRequest(
            coordinates=[
                [103.8198, 1.3521],
                [103.8514, 1.2897],
                [103.9915, 1.3644],
            ]
        ),
        timeout=30,
    )

    assert len(m.durations) == 3
    assert m.duration(0, 0) == 0
    assert m.duration(0, 1) is not None and m.duration(0, 1) > 0


def test_integration_optimization():
    require_api_key()
    solution = integration_client().optimization.solve(
        justrouting.OptimizationRequest(
            vehicles=[
                justrouting.Vehicle(
                    id=1,
                    start=[103.8198, 1.3521],
                    end=[103.8198, 1.3521],
                    capacity=[4],
                )
            ],
            jobs=[
                justrouting.Job(id=1, location=[103.8514, 1.2897], delivery=[1], service=300),
                justrouting.Job(id=2, location=[103.9915, 1.3644], delivery=[1], service=300),
            ],
        ),
        timeout=30,
    )

    assert solution.code == 0
    assert len(solution.routes) > 0
    assert len(solution.routes[0].steps) > 0
    print(
        f"cost={solution.summary.cost} routes={len(solution.routes)} "
        f"unassigned={len(solution.unassigned)}"
    )
