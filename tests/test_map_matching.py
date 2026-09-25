"""Port of map_matching_test.go."""

import pytest

import justrouting
from conftest import json_handler, new_test_client

# matchFixture mirrors a real matching response: a null tracepoint for a
# coordinate that could not be matched, and one matching with confidence.
MATCH_FIXTURE = """{
  "code": "Ok",
  "tracepoints": [
    {"alternatives_count":2,"waypoint_index":0,"matchings_index":0,"name":"Marina Boulevard","hint":"aaa","distance":4.216,"location":[103.81982,1.35211]},
    null,
    {"alternatives_count":0,"waypoint_index":1,"matchings_index":0,"name":"Changi Coast Road","hint":"bbb","distance":8.104,"location":[103.99151,1.36442]}
  ],
  "matchings": [
    {
      "confidence": 0.95,
      "geometry": "aa_ceeEnAqB",
      "legs": [
        {"steps":[],"summary":"East Coast Parkway","weight":1583.4,"duration":1583.4,"distance":24512.7}
      ],
      "weight_name": "routability",
      "weight": 1583.4,
      "duration": 1583.4,
      "distance": 24512.7
    }
  ]
}"""


def simple_match():
    return justrouting.MapMatchingRequest(
        coordinates=[
            [103.8198, 1.3521],
            [103.8514, 1.2897],
            [103.9915, 1.3644],
        ]
    )


def test_map_matching_get_decodes_response():
    with new_test_client(json_handler(200, MATCH_FIXTURE)) as c:
        match = c.map_matching.get(simple_match())

    assert match.confidence == 0.95
    # Match extends Route, so its fields are available.
    assert isinstance(match, justrouting.Route)
    assert match.distance == 24512.7
    assert match.duration == 1583.4
    assert len(match.legs) == 1
    assert match.legs[0].summary == "East Coast Parkway"


# get_all additionally exposes the snapped tracepoints, including None
# entries for coordinates the engine could not match.
def test_map_matching_get_all_returns_tracepoints():
    with new_test_client(json_handler(200, MATCH_FIXTURE)) as c:
        resp = c.map_matching.get_all(simple_match())

    assert len(resp.matchings) == 1
    assert len(resp.tracepoints) == 3
    assert resp.tracepoints[1] is None, "unmatched coordinate must decode as None"
    tp = resp.tracepoints[0]
    assert tp.alternatives_count == 2
    assert tp.waypoint_index == 0
    tp = resp.tracepoints[2]
    assert tp.matchings_index == 0
    assert tp.name == "Changi Coast Road"


# An empty matchings array is a no-match condition, not a decode failure.
def test_map_matching_get_empty_matchings():
    with new_test_client(
        json_handler(200, '{"code":"Ok","tracepoints":[],"matchings":[]}')
    ) as c:
        with pytest.raises(justrouting.Error) as e:
            c.map_matching.get(simple_match())
    assert e.value.osrm_code == "NoMatch"
    assert e.value.status_code == 200


@pytest.mark.parametrize(
    "req,want_path",
    [
        (
            simple_match(),
            "/match/v1/driving/103.8198,1.3521;103.8514,1.2897;103.9915,1.3644",
        ),
        (
            justrouting.MapMatchingRequest(
                coordinates=[[103.8198, 1.3521], [103.9915, 1.3644]],
                profile="motorcycle",
            ),
            "/match/v1/motorcycle/103.8198,1.3521;103.9915,1.3644",
        ),
    ],
)
def test_map_matching_request_path_encoding(req, want_path):
    seen = {}

    def handler(request):
        seen["path"] = request.url_path()
        seen["raw"] = request.path
        return 200, MATCH_FIXTURE, {}

    with new_test_client(handler) as c:
        c.map_matching.get(req)

    assert seen["path"] == want_path
    assert seen["raw"].split("?", 1)[0] == want_path, "path must reach the server unescaped"


def test_map_matching_query_encoding():
    # defaults send no options
    seen = {}

    def handler(request):
        seen["query"] = request.query
        return 200, MATCH_FIXTURE, {}

    with new_test_client(handler) as c:
        c.map_matching.get(simple_match())
    for key in [
        "timestamps", "radiuses", "gaps", "tidy", "waypoints", "snapping",
        "steps", "geometries", "overview", "annotations",
    ]:
        assert key not in seen["query"]

    # all options
    seen.clear()
    with new_test_client(handler) as c:
        c.map_matching.get(
            justrouting.MapMatchingRequest(
                coordinates=[[103.8198, 1.3521], [103.8514, 1.2897], [103.9915, 1.3644]],
                timestamps=[1720000000, 1720000060, 1720000120],
                radiuses=[10, 15, 25],
                gaps="ignore",
                tidy=True,
                waypoints=[0, 2],
                snapping="any",
                steps=True,
                annotations=["duration", "distance"],
                geometries="geojson",
                overview="full",
                exclude=["motorway", "ferry"],
            )
        )
    for key, value in {
        "timestamps": "1720000000;1720000060;1720000120",
        # radiuses are rendered without a trailing ".0", like Go's
        # FormatFloat.
        "radiuses": "10;15;25",
        "gaps": "ignore",
        "tidy": "true",
        "waypoints": "0;2",
        "snapping": "any",
        "steps": "true",
        "annotations": "duration,distance",
        "geometries": "geojson",
        "overview": "full",
        "exclude": "motorway,ferry",
    }.items():
        assert seen["query"][key] == [value]

    # false booleans stay omitted
    seen.clear()
    with new_test_client(handler) as c:
        c.map_matching.get(
            justrouting.MapMatchingRequest(
                coordinates=[[103.8198, 1.3521], [103.9915, 1.3644]],
                tidy=False,
                steps=False,
            )
        )
    assert "tidy" not in seen["query"]
    assert "steps" not in seen["query"]


@pytest.mark.parametrize(
    "req",
    [
        None,  # nil request
        justrouting.MapMatchingRequest(  # one coordinate
            coordinates=[[103.8, 1.3]]
        ),
        justrouting.MapMatchingRequest(  # timestamp count mismatch
            coordinates=[[103.8, 1.3], [103.9, 1.3], [104.0, 1.3]],
            timestamps=[1720000000],
        ),
        justrouting.MapMatchingRequest(  # radius count mismatch
            coordinates=[[103.8, 1.3], [103.9, 1.3], [104.0, 1.3]],
            radiuses=[10, 15],
        ),
        # The engine rejects a single shared radius, so it is caught
        # locally.
        justrouting.MapMatchingRequest(  # single radius for 3 coordinates
            coordinates=[[103.8, 1.3], [103.9, 1.3], [104.0, 1.3]],
            radiuses=[10],
        ),
        justrouting.MapMatchingRequest(  # negative radius
            coordinates=[[103.8, 1.3], [103.9, 1.3]],
            radiuses=[-5],
        ),
        justrouting.MapMatchingRequest(  # waypoint index out of range
            coordinates=[[103.8, 1.3], [103.9, 1.3]],
            waypoints=[0, 5],
        ),
    ],
)
def test_map_matching_validation(req):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(justrouting.InvalidRequestError):
            c.map_matching.get(req)


# Malformed coordinates are caught locally so a request is not wasted.
def test_map_matching_rejects_bad_coordinates_locally():
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        # The classic [lat, lon] mix-up: 103.8198 is not a latitude.
        with pytest.raises(justrouting.InvalidCoordinatesError):
            c.map_matching.get(
                justrouting.MapMatchingRequest(
                    coordinates=[[1.3521, 103.8198], [103.9915, 1.3644]]
                )
            )
