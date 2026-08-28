"""Port of matrix_test.go."""

import pytest

import justrouting
from conftest import json_handler, new_test_client, three_points

# matrixFixture includes a null entry, which is how the engine reports a
# pair it cannot connect.
MATRIX_FIXTURE = """{
  "code": "Ok",
  "durations": [[0, 612.4, 1583.4], [598.1, 0, null], [1601.2, null, 0]],
  "distances": [[0, 8421.5, 24512.7], [8390.2, 0, null], [24488.1, null, 0]],
  "sources": [
    {"hint":"a","distance":4.2,"name":"Marina Boulevard","location":[103.81982,1.35211]},
    {"hint":"b","distance":2.1,"name":"Orchard Road","location":[103.83,1.3048]},
    {"hint":"c","distance":8.1,"name":"Changi Coast Road","location":[103.99151,1.36442]}
  ],
  "destinations": [
    {"hint":"a","distance":4.2,"name":"Marina Boulevard","location":[103.81982,1.35211]},
    {"hint":"b","distance":2.1,"name":"Orchard Road","location":[103.83,1.3048]},
    {"hint":"c","distance":8.1,"name":"Changi Coast Road","location":[103.99151,1.36442]}
  ]
}"""


def matrix_request(**overrides):
    kwargs = {"coordinates": three_points()}
    kwargs.update(overrides)
    return justrouting.MatrixRequest(**kwargs)


def test_matrix_get_decodes_response():
    with new_test_client(json_handler(200, MATRIX_FIXTURE)) as c:
        m = c.matrix.get(matrix_request())

    assert len(m.durations) == 3
    assert len(m.sources) == 3
    assert len(m.destinations) == 3

    assert m.duration(0, 1) == 612.4
    assert m.distance(0, 2) == 24512.7


def test_matrix_unreachable_pairs():
    with new_test_client(json_handler(200, MATRIX_FIXTURE)) as c:
        m = c.matrix.get(matrix_request())

    # A null entry means unreachable. It must stay distinguishable from a
    # real zero.
    assert m.duration(1, 2) is None
    # The diagonal is a genuine zero.
    assert m.duration(0, 0) == 0


def test_matrix_accessor_bounds():
    with new_test_client(json_handler(200, MATRIX_FIXTURE)) as c:
        m = c.matrix.get(matrix_request())

    for i, j in [(-1, 0), (0, -1), (3, 0), (0, 3), (99, 99)]:
        assert m.duration(i, j) is None
        assert m.distance(i, j) is None


def test_matrix_request_encoding():
    # defaults request both annotations
    seen = {}

    def handler(request):
        seen["path"] = request.url_path()
        seen["query"] = request.query
        return 200, '{"code":"Ok"}', {}

    with new_test_client(handler) as c:
        c.matrix.get(matrix_request())
    assert seen["path"] == (
        "/osrm/table/v1/driving/103.8198,1.3521;103.83,1.3048;103.9915,1.3644"
    )
    assert seen["query"]["annotations"] == ["duration,distance"]
    assert "sources" not in seen["query"]
    assert "destinations" not in seen["query"]

    # sources and destinations subsets
    seen.clear()
    with new_test_client(handler) as c:
        c.matrix.get(matrix_request(sources=[0], destinations=[1, 2]))
    assert seen["query"]["sources"] == ["0"]
    assert seen["query"]["destinations"] == ["1;2"]

    # single annotation
    seen.clear()
    with new_test_client(handler) as c:
        c.matrix.get(matrix_request(annotations=["duration"]))
    assert seen["query"]["annotations"] == ["duration"]

    # custom profile
    seen.clear()
    with new_test_client(handler) as c:
        c.matrix.get(matrix_request(profile="walking"))
    assert seen["path"] == (
        "/osrm/table/v1/walking/103.8198,1.3521;103.83,1.3048;103.9915,1.3644"
    )


@pytest.mark.parametrize(
    "req,want",
    [
        (None, justrouting.InvalidRequestError),  # nil request
        (justrouting.MatrixRequest(), justrouting.InvalidRequestError),  # no coordinates
        # a matrix needs at least two points
        (
            justrouting.MatrixRequest(coordinates=[[103.8, 1.3]]),
            justrouting.InvalidRequestError,
        ),
        # source index beyond the coordinate list
        (
            justrouting.MatrixRequest(coordinates=three_points(), sources=[5]),
            justrouting.InvalidRequestError,
        ),
        # negative destination index
        (
            justrouting.MatrixRequest(coordinates=three_points(), destinations=[-1]),
            justrouting.InvalidRequestError,
        ),
        # invalid coordinate
        (
            justrouting.MatrixRequest(coordinates=[[103.8, 1.3], [0, 91]]),
            justrouting.InvalidCoordinatesError,
        ),
    ],
)
def test_matrix_validation(req, want):
    def handler(request):
        raise AssertionError("no request should reach the server")

    with new_test_client(handler) as c:
        with pytest.raises(want):
            c.matrix.get(req)


def test_matrix_plan_limit():
    with new_test_client(
        json_handler(400, '{"error":"matrix size exceeds plan limit"}'),
        max_retries=0,
    ) as c:
        with pytest.raises(justrouting.PlanLimitExceededError):
            c.matrix.get(matrix_request())
