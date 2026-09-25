"""Port of nearest_test.go."""

import pytest

import justrouting
from conftest import json_handler, new_test_client

# nearestFixture mirrors a real nearest response with two candidates,
# including the OSM node IDs of the closest segment.
NEAREST_FIXTURE = """{
  "code": "Ok",
  "waypoints": [
    {"hint":"aaa","distance":4.216,"name":"Marina Boulevard","location":[103.81982,1.35211],"nodes":[1234,5678]},
    {"hint":"bbb","distance":21.7,"name":"Bayfront Avenue","location":[103.82001,1.35237],"nodes":[4321]}
  ]
}"""


def simple_nearest():
    return justrouting.NearestRequest(coordinate=[103.8198, 1.3521])


def test_nearest_get_decodes_response():
    with new_test_client(json_handler(200, NEAREST_FIXTURE)) as c:
        wp = c.nearest.get(simple_nearest())

    assert wp.name == "Marina Boulevard"
    assert wp.distance == 4.216
    assert wp.location.lon() == 103.81982
    assert wp.nodes == [1234, 5678]


# get returns only the closest segment; get_all exposes every candidate.
def test_nearest_get_all_returns_candidates():
    with new_test_client(json_handler(200, NEAREST_FIXTURE)) as c:
        resp = c.nearest.get_all(simple_nearest())

    assert len(resp.waypoints) == 2
    assert resp.waypoints[0].distance < resp.waypoints[1].distance, (
        "waypoints ordered best first"
    )


# An empty waypoints array on Ok is a no-segment condition, not a decode
# failure.
def test_nearest_get_empty_waypoints():
    with new_test_client(json_handler(200, '{"code":"Ok","waypoints":[]}')) as c:
        with pytest.raises(justrouting.Error) as e:
            c.nearest.get(simple_nearest())
    assert e.value.osrm_code == "NoSegment"
    assert e.value.status_code == 200


@pytest.mark.parametrize(
    "req,want_path",
    [
        (
            simple_nearest(),
            "/nearest/v1/driving/103.8198,1.3521",
        ),
        (
            justrouting.NearestRequest(
                coordinate=[103.8198, 1.3521], profile="cycling"
            ),
            "/nearest/v1/cycling/103.8198,1.3521",
        ),
    ],
)
def test_nearest_request_path_encoding(req, want_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url_path()
        seen["raw"] = request.path
        return 200, NEAREST_FIXTURE, {}

    with new_test_client(handler) as c:
        c.nearest.get(req)

    assert seen["path"] == want_path
    assert seen["raw"].split("?", 1)[0] == want_path, "path must reach the server unescaped"


def test_nearest_query_encoding():
    # defaults send no options
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, NEAREST_FIXTURE, {}

    with new_test_client(handler) as c:
        c.nearest.get(simple_nearest())
    for key in ["number", "exclude"]:
        assert key not in seen["query"]

    # all options
    seen.clear()
    with new_test_client(handler) as c:
        c.nearest.get(
            justrouting.NearestRequest(
                coordinate=[103.8198, 1.3521],
                number=3,
                exclude=["motorway", "ferry"],
            )
        )
    assert seen["query"]["number"] == ["3"]
    assert seen["query"]["exclude"] == ["motorway,ferry"]

    # number=0 (the engine default) stays omitted
    seen.clear()
    with new_test_client(handler) as c:
        c.nearest.get(justrouting.NearestRequest(coordinate=[103.8, 1.3], number=0))
    assert "number" not in seen["query"]


@pytest.mark.parametrize(
    "req",
    [
        None,  # nil request
        justrouting.NearestRequest(number=2),  # missing coordinate
        justrouting.NearestRequest(  # negative number
            coordinate=[103.8, 1.3], number=-1
        ),
    ],
)
def test_nearest_validation(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidRequestError):
            c.nearest.get(req)


# Malformed coordinates are caught locally so a request is not wasted.
def test_nearest_rejects_bad_coordinates_locally():
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        # The classic [lat, lon] mix-up: 103.8198 is not a latitude.
        with pytest.raises(justrouting.InvalidCoordinatesError):
            c.nearest.get(justrouting.NearestRequest(coordinate=[1.3521, 103.8198]))
