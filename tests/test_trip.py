"""Port of trip_test.go."""

import pytest

import justrouting
from conftest import json_handler, new_test_client

# tripFixture mirrors a real trip response: the waypoints reordered into the
# fastest visiting order, and the round trip itself.
TRIP_FIXTURE = """{
  "code": "Ok",
  "waypoints": [
    {"hint":"aaa","distance":4.216,"name":"Marina Boulevard","location":[103.81982,1.35211]},
    {"hint":"ccc","distance":2.3,"name":"Sentosa Gateway","location":[103.8514,1.2897]},
    {"hint":"bbb","distance":8.104,"name":"Changi Coast Road","location":[103.99151,1.36442]}
  ],
  "trips": [
    {
      "geometry": "aa_ceeEnAqB",
      "legs": [
        {"steps":[],"summary":"","weight":1900.0,"duration":1900.0,"distance":30100.0}
      ],
      "weight_name": "routability",
      "weight": 1900.0,
      "duration": 1900.0,
      "distance": 30100.0
    }
  ]
}"""


def simple_trip():
    return justrouting.TripRequest(
        coordinates=[
            [103.8198, 1.3521],
            [103.8514, 1.2897],
            [103.9915, 1.3644],
        ]
    )


def test_trip_get_decodes_response():
    with new_test_client(json_handler(200, TRIP_FIXTURE)) as c:
        trip = c.trip.get(simple_trip())

    assert trip.distance == 30100.0
    assert trip.duration == 1900.0
    assert len(trip.legs) == 1


# get_all additionally exposes the waypoints, reordered into the order the
# trip visits them.
def test_trip_get_all_returns_visiting_order():
    with new_test_client(json_handler(200, TRIP_FIXTURE)) as c:
        resp = c.trip.get_all(simple_trip())

    assert len(resp.trips) == 1
    assert len(resp.waypoints) == 3
    # The input order was Marina, Sentosa, Changi; the engine may visit
    # Sentosa second.
    assert resp.waypoints[1].name == "Sentosa Gateway"


# An empty trips array is a no-trip condition, not a decode failure.
def test_trip_get_empty_trips():
    with new_test_client(
        json_handler(200, '{"code":"Ok","trips":[],"waypoints":[]}')
    ) as c:
        with pytest.raises(justrouting.Error) as e:
            c.trip.get(simple_trip())
    assert e.value.osrm_code == "NoTrip"
    assert e.value.status_code == 200


@pytest.mark.parametrize(
    "req,want_path",
    [
        (
            simple_trip(),
            "/trip/v1/driving/103.8198,1.3521;103.8514,1.2897;103.9915,1.3644",
        ),
        (
            justrouting.TripRequest(
                coordinates=[[103.8198, 1.3521], [103.9915, 1.3644]],
                profile="motorcycle",
            ),
            "/trip/v1/motorcycle/103.8198,1.3521;103.9915,1.3644",
        ),
    ],
)
def test_trip_request_path_encoding(req, want_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url_path()
        seen["raw"] = request.path
        return 200, TRIP_FIXTURE, {}

    with new_test_client(handler) as c:
        c.trip.get(req)

    assert seen["path"] == want_path
    assert seen["raw"].split("?", 1)[0] == want_path, "path must reach the server unescaped"


def test_trip_query_encoding():
    # defaults send no options
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, TRIP_FIXTURE, {}

    with new_test_client(handler) as c:
        c.trip.get(simple_trip())
    for key in [
        "roundtrip", "source", "destination", "steps", "geometries",
        "overview", "annotations",
    ]:
        assert key not in seen["query"]

    # all options, with roundtrip explicitly disabled
    seen.clear()
    with new_test_client(handler) as c:
        c.trip.get(
            justrouting.TripRequest(
                coordinates=[[103.8198, 1.3521], [103.8514, 1.2897]],
                roundtrip=False,
                source="first",
                destination="last",
                steps=True,
                annotations=["duration", "distance"],
                geometries="geojson",
                overview="full",
                exclude=["motorway", "ferry"],
            )
        )
    for key, value in {
        "roundtrip": "false",
        "source": "first",
        "destination": "last",
        "steps": "true",
        "annotations": "duration,distance",
        "geometries": "geojson",
        "overview": "full",
        "exclude": "motorway,ferry",
    }.items():
        assert seen["query"][key] == [value]

    # roundtrip=true is sent explicitly too (tri-state)
    seen.clear()
    with new_test_client(handler) as c:
        c.trip.get(
            justrouting.TripRequest(
                coordinates=[[103.8198, 1.3521], [103.9915, 1.3644]],
                roundtrip=True,
            )
        )
    assert seen["query"]["roundtrip"] == ["true"]


@pytest.mark.parametrize(
    "req",
    [
        None,  # nil request
        justrouting.TripRequest(  # one coordinate
            coordinates=[[103.8, 1.3]]
        ),
    ],
)
def test_trip_validation(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidRequestError):
            c.trip.get(req)


# Malformed coordinates are caught locally so a request is not wasted.
def test_trip_rejects_bad_coordinates_locally():
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        # The classic [lat, lon] mix-up: 103.8198 is not a latitude.
        with pytest.raises(justrouting.InvalidCoordinatesError):
            c.trip.get(
                justrouting.TripRequest(
                    coordinates=[[1.3521, 103.8198], [103.9915, 1.3644]]
                )
            )
