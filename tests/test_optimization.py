"""Port of optimization_test.go."""

import json

import pytest

import justrouting
from conftest import json_handler, new_test_client, simple_optimization

SOLUTION_FIXTURE = """{
  "code": 0,
  "summary": {
    "cost": 2841, "routes": 1, "unassigned": 1,
    "delivery": [3], "pickup": [0],
    "setup": 0, "service": 900, "duration": 2841,
    "waiting_time": 0, "priority": 0, "distance": 31204
  },
  "unassigned": [
    {"id": 4, "location": [103.7, 1.42], "type": "job", "description": "far depot"}
  ],
  "routes": [
    {
      "vehicle": 1, "cost": 2841, "setup": 0, "service": 900,
      "duration": 2841, "waiting_time": 0, "priority": 0, "distance": 31204,
      "delivery": [3], "pickup": [0],
      "steps": [
        {"type":"start","location":[103.8198,1.3521],"setup":0,"service":0,"waiting_time":0,"arrival":0,"duration":0,"distance":0},
        {"type":"job","location":[103.8514,1.2897],"id":1,"job":1,"setup":0,"service":300,"waiting_time":0,"arrival":842,"duration":842,"distance":9120,"load":[2]},
        {"type":"end","location":[103.8198,1.3521],"setup":0,"service":0,"waiting_time":0,"arrival":2841,"duration":2841,"distance":31204}
      ]
    }
  ]
}"""


def test_optimization_solve_decodes_response():
    with new_test_client(json_handler(200, SOLUTION_FIXTURE)) as c:
        solution = c.optimization.solve(simple_optimization())

    assert solution.code == 0
    assert solution.summary.cost == 2841
    assert solution.summary.distance == 31204

    assert len(solution.routes) == 1
    route = solution.routes[0]
    assert route.vehicle == 1
    assert len(route.steps) == 3
    assert route.steps[0].type == "start"
    assert route.steps[2].type == "end"
    job = route.steps[1]
    assert job.job == 1
    assert job.arrival == 842
    assert job.location.lon() == 103.8514

    assert len(solution.unassigned) == 1
    assert solution.unassigned[0].id == 4


def test_optimization_request_body():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url_path()
        seen["body"] = json.loads(request.read_body())
        return 200, '{"code":0,"summary":{},"routes":[],"unassigned":[]}', {}

    req = justrouting.OptimizationRequest(
        vehicles=[
            justrouting.Vehicle(
                id=1,
                start=[103.8198, 1.3521],
                end=[103.8198, 1.3521],
                capacity=[4],
                skills=[1],
                time_window=(28800, 43200),
            )
        ],
        jobs=[
            justrouting.Job(
                id=1,
                location=[103.8514, 1.2897],
                service=300,
                delivery=[1],
                time_windows=[(28800, 32400)],
            )
        ],
        options=justrouting.OptimizationOptions(geometry=True),
    )

    with new_test_client(handler) as c:
        c.optimization.solve(req)

    assert seen["method"] == "POST"
    assert seen["path"] == "/optimize"
    body = seen["body"]

    vehicles = body["vehicles"]
    assert len(vehicles) == 1
    vehicle = vehicles[0]
    # Coordinates must serialise as [lon, lat] arrays.
    assert vehicle["start"] == [103.8198, 1.3521]
    assert vehicle["time_window"] == [28800, 43200]

    job = body["jobs"][0]
    assert job["service"] == 300
    assert len(job["time_windows"]) == 1

    assert body["options"] == {"g": True}

    # Shipments were not set and must be omitted rather than sent as null.
    assert "shipments" not in body


def test_optimization_shipments():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read_body())
        return 200, '{"code":0,"summary":{},"routes":[],"unassigned":[]}', {}

    req = justrouting.OptimizationRequest(
        vehicles=[justrouting.Vehicle(id=1, start=[103.8198, 1.3521])],
        shipments=[
            justrouting.Shipment(
                pickup=justrouting.ShipmentStep(id=1, location=[103.85, 1.29]),
                delivery=justrouting.ShipmentStep(id=2, location=[103.9, 1.31]),
                amount=[1],
            )
        ],
    )

    with new_test_client(handler) as c:
        c.optimization.solve(req)

    shipments = seen["body"]["shipments"]
    assert len(shipments) == 1
    assert "jobs" not in seen["body"]


def test_optimization_validation():
    depot = justrouting.Point([103.8198, 1.3521])

    cases = [
        (None, justrouting.InvalidRequestError),  # nil request
        (
            justrouting.OptimizationRequest(jobs=[justrouting.Job(id=1, location=depot)]),
            justrouting.InvalidRequestError,  # no vehicles
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot)]
            ),
            justrouting.InvalidRequestError,  # no jobs or shipments
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1)],
                jobs=[justrouting.Job(id=1, location=depot)],
            ),
            justrouting.InvalidRequestError,  # vehicle without a start or end
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot)],
                jobs=[justrouting.Job(id=1, location=[500, 1.3])],
            ),
            justrouting.InvalidCoordinatesError,  # job with an invalid location
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot)],
                jobs=[justrouting.Job(id=1)],
            ),
            justrouting.InvalidCoordinatesError,  # job with no location
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot)],
                shipments=[
                    justrouting.Shipment(
                        pickup=justrouting.ShipmentStep(id=1, location=depot),
                        delivery=justrouting.ShipmentStep(id=2, location=[0, 91]),
                    )
                ],
            ),
            justrouting.InvalidCoordinatesError,  # shipment with an invalid delivery location
        ),
    ]

    for req, want in cases:
        def handler(request):
            raise AssertionError("no request should reach the server")

        with new_test_client(handler) as c:
            with pytest.raises(want):
                c.optimization.solve(req)


def test_optimization_plan_limits():
    for body in ['{"error":"too many jobs"}', '{"error":"too many vehicles"}']:
        with new_test_client(json_handler(400, body), max_retries=0) as c:
            with pytest.raises(justrouting.PlanLimitExceededError):
                c.optimization.solve(simple_optimization())
