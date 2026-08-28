"""Port of routes_test.go."""

import pytest

import justrouting
from conftest import OK_ROUTE, json_handler, new_test_client, simple_route

# routeFixture mirrors a real routing response, including the snapped
# waypoints and a polyline geometry.
ROUTE_FIXTURE = """{
  "code": "Ok",
  "waypoints": [
    {"hint":"aaa","distance":4.216,"name":"Marina Boulevard","location":[103.81982,1.35211]},
    {"hint":"bbb","distance":8.104,"name":"Changi Coast Road","location":[103.99151,1.36442]}
  ],
  "routes": [
    {
      "geometry": "ka|`@_ceeEnAqB",
      "legs": [
        {"steps":[],"summary":"East Coast Parkway","weight":1583.4,"duration":1583.4,"distance":24512.7}
      ],
      "weight_name": "routability",
      "weight": 1583.4,
      "duration": 1583.4,
      "distance": 24512.7
    },
    {
      "geometry": "ab|`@_ceeEnAqB",
      "legs": [],
      "weight_name": "routability",
      "weight": 1712.9,
      "duration": 1712.9,
      "distance": 26104.2
    }
  ]
}"""


def test_routes_get_decodes_response():
    with new_test_client(json_handler(200, ROUTE_FIXTURE)) as c:
        route = c.routes.get(simple_route())

    assert route.distance == 24512.7
    assert route.duration == 1583.4
    assert route.weight_name == "routability"
    assert len(route.legs) == 1
    assert route.legs[0].summary == "East Coast Parkway"

    # The quickstart divides by 1000 to get kilometres.
    km = route.distance / 1000
    assert 24.5 <= km <= 24.6


def test_routes_get_all_returns_alternatives_and_waypoints():
    with new_test_client(json_handler(200, ROUTE_FIXTURE)) as c:
        resp = c.routes.get_all(simple_route())

    assert len(resp.routes) == 2
    assert resp.routes[0].distance < resp.routes[1].distance, "routes ordered best first"
    assert len(resp.waypoints) == 2
    assert resp.waypoints[0].name == "Marina Boulevard"
    assert resp.waypoints[0].location.lon() == 103.81982


def test_routes_get_empty_routes():
    with new_test_client(json_handler(200, '{"code":"Ok","routes":[],"waypoints":[]}')) as c:
        with pytest.raises(justrouting.NoRouteError):
            c.routes.get(simple_route())


# The coordinate separators "," and ";" are legal in a path segment and must
# reach the server unescaped, or the API cannot parse them.
@pytest.mark.parametrize(
    "req,want_path",
    [
        (
            simple_route(),
            "/osrm/route/v1/driving/103.8198,1.3521;103.9915,1.3644",
        ),
        (
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
                waypoints=[[103.85, 1.29], [103.9, 1.31]],
            ),
            "/osrm/route/v1/driving/103.8198,1.3521;103.85,1.29;103.9,1.31;103.9915,1.3644",
        ),
        (
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
                profile="cycling",
            ),
            "/osrm/route/v1/cycling/103.8198,1.3521;103.9915,1.3644",
        ),
        (
            justrouting.RouteRequest(
                origin=[-0.1276474, 51.5073219],
                destination=[-3.188267, 55.953251],
            ),
            "/osrm/route/v1/driving/-0.1276474,51.5073219;-3.188267,55.953251",
        ),
    ],
)
def test_routes_request_path_encoding(req, want_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url_path()
        seen["raw"] = request.path
        return 200, OK_ROUTE, {}

    with new_test_client(handler) as c:
        c.routes.get(req)

    assert seen["path"] == want_path
    assert seen["raw"].split("?", 1)[0] == want_path, "path must reach the server unescaped"


def test_routes_query_encoding():
    # defaults send no options
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, OK_ROUTE, {}

    with new_test_client(handler) as c:
        c.routes.get(simple_route())
    for key in ["alternatives", "steps", "geometries", "overview", "annotations"]:
        assert key not in seen["query"]

    # all options
    seen.clear()
    with new_test_client(handler) as c:
        c.routes.get(
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
                alternatives=3,
                steps=True,
                annotations=["duration", "distance"],
                geometries="geojson",
                overview="full",
                continue_straight=True,
                exclude=["motorway", "ferry"],
            )
        )
    want = {
        "alternatives": "3",
        "steps": "true",
        "annotations": "duration,distance",
        "geometries": "geojson",
        "overview": "full",
        "continue_straight": "true",
        "exclude": "motorway,ferry",
    }
    for key, value in want.items():
        assert seen["query"][key] == [value]

    # overview can be disabled
    seen.clear()
    with new_test_client(handler) as c:
        c.routes.get(
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
                overview="false",
            )
        )
    assert seen["query"]["overview"] == ["false"]


@pytest.mark.parametrize(
    "req",
    [
        None,  # nil request
        justrouting.RouteRequest(destination=[103.9, 1.3]),  # missing origin
        justrouting.RouteRequest(origin=[103.8, 1.3]),  # missing destination
    ],
)
def test_routes_validation(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidRequestError):
            c.routes.get(req)


# Malformed coordinates are caught locally so a request is not wasted.
@pytest.mark.parametrize(
    "req",
    [
        # wrong number of values
        justrouting.RouteRequest(origin=[103.8], destination=[103.9, 1.3]),
        # longitude out of range
        justrouting.RouteRequest(origin=[200, 1.3], destination=[103.9, 1.3]),
        # the classic [lat, lon] mix-up: 103.8 is not a latitude
        justrouting.RouteRequest(origin=[1.3521, 103.8198], destination=[103.9, 1.3]),
    ],
)
def test_routes_rejects_bad_coordinates_locally(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidCoordinatesError):
            c.routes.get(req)
