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
    "waiting_time": 0, "priority": 0, "distance": 31204,
    "violations": []
  },
  "unassigned": [
    {"id": 4, "location": [103.7, 1.42], "location_index": 3, "type": "job", "description": "far depot"}
  ],
  "routes": [
    {
      "vehicle": 1, "cost": 2841, "setup": 0, "service": 900,
      "duration": 2841, "waiting_time": 0, "priority": 0, "distance": 31204,
      "delivery": [3], "pickup": [0],
      "description": "van one", "geometry": "encoded_polyline", "violations": [],
      "steps": [
        {"type":"start","location":[103.8198,1.3521],"setup":0,"service":0,"waiting_time":0,"arrival":0,"duration":0,"distance":0,"violations":[]},
        {"type":"job","location":[103.8514,1.2897],"location_index":1,"id":1,"job":1,"setup":0,"service":300,"waiting_time":0,"arrival":842,"duration":842,"distance":9120,"load":[2],"violations":[]},
        {"type":"end","location":[103.8198,1.3521],"setup":0,"service":0,"waiting_time":0,"arrival":2841,"duration":2841,"distance":31204,"violations":[]}
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
    assert solution.unassigned[0].location_index == 3

    assert solution.summary.delivery == [3]
    assert solution.summary.violations == []
    assert route.description == "van one"
    assert route.geometry == "encoded_polyline"
    assert job.id == 1
    assert job.location_index == 1
    assert job.load == [2]


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
                type="van",
                time_window=(28800, 43200),
                breaks=[
                    justrouting.Break(
                        id=1,
                        time_windows=[(36000, 39600)],
                        service=1800,
                        max_load=[2],
                    )
                ],
                speed_factor=0.8,
                max_tasks=3,
                max_travel_time=14400,
                max_distance=50000,
                costs=justrouting.VehicleCosts(
                    fixed=10, per_hour=2000, per_task_hour=300, per_km=2
                ),
                steps=[justrouting.VehicleStep(type="job", id=1)],
            )
        ],
        jobs=[
            justrouting.Job(
                id=1,
                location=[103.8514, 1.2897],
                setup=60,
                service=300,
                setup_per_type={"van": 120},
                service_per_type={"van": 600},
                delivery=[1],
                skills=[1],
                priority=50,
                time_windows=[(28800, 32400)],
            )
        ],
        matrices={
            "car": justrouting.CustomMatrix(
                durations=[[0, 14], [21, 0]],
                distances=[[0, 1500], [1500, 0]],
                costs=[[0, 1], [1, 0]],
            )
        },
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
    assert vehicle["type"] == "van"
    assert vehicle["speed_factor"] == 0.8
    assert vehicle["max_tasks"] == 3
    assert vehicle["max_travel_time"] == 14400
    assert vehicle["max_distance"] == 50000
    brk = vehicle["breaks"][0]
    assert brk["id"] == 1
    assert brk["service"] == 1800
    assert brk["max_load"] == [2]
    assert vehicle["costs"] == {"fixed": 10, "per_hour": 2000, "per_task_hour": 300, "per_km": 2}
    assert vehicle["steps"] == [{"type": "job", "id": 1}]

    job = body["jobs"][0]
    assert job["service"] == 300
    assert job["setup"] == 60
    assert job["setup_per_type"] == {"van": 120}
    assert job["service_per_type"] == {"van": 600}
    assert job["priority"] == 50
    assert len(job["time_windows"]) == 1

    assert body["matrices"]["car"]["durations"] == [[0, 14], [21, 0]]
    assert body["matrices"]["car"]["distances"] == [[0, 1500], [1500, 0]]
    assert body["matrices"]["car"]["costs"] == [[0, 1], [1, 0]]

    assert body["options"] == {"g": True}

    # Shipments were not set and must be omitted rather than sent as null.
    assert "shipments" not in body

    # Zero-valued fields must be omitted rather than serialized.
    assert "description" not in vehicle


# Index-only locations must pass validation and serialize without
# coordinates; row 0 must survive serialization.
def test_optimization_index_only_locations():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read_body())
        return 200, '{"code":0,"summary":{},"routes":[],"unassigned":[]}', {}

    req = justrouting.OptimizationRequest(
        vehicles=[justrouting.Vehicle(id=1, start_index=0, type="van")],
        jobs=[justrouting.Job(id=1, location_index=1, service=300)],
        matrices={
            "car": justrouting.CustomMatrix(durations=[[0, 14], [21, 0]])
        },
    )

    with new_test_client(handler) as c:
        c.optimization.solve(req)

    vehicle = seen["body"]["vehicles"][0]
    assert "start" not in vehicle
    assert vehicle["start_index"] == 0
    job = seen["body"]["jobs"][0]
    assert "location" not in job
    assert job["location_index"] == 1


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
            justrouting.InvalidRequestError,  # vehicle without start/end or indices
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
            justrouting.InvalidRequestError,  # job with neither location nor index
        ),
        (
            justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot)],
                shipments=[
                    justrouting.Shipment(
                        pickup=justrouting.ShipmentStep(id=1, location=depot),
                        delivery=justrouting.ShipmentStep(id=2),
                    )
                ],
            ),
            justrouting.InvalidRequestError,  # shipment step with neither location nor index
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
