"""The Optimization service: solve vehicle routing problems — given a fleet
and a set of tasks, it assigns tasks to vehicles and orders each vehicle's
stops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .error import Error, InvalidCoordinatesError, InvalidRequestError
from .geo import Point, PointLike

__all__ = [
    "OptimizationService",
    "OptimizationRequest",
    "OptimizationOptions",
    "TimeWindow",
    "CustomMatrix",
    "Vehicle",
    "Break",
    "VehicleCosts",
    "VehicleStep",
    "Violation",
    "Job",
    "ShipmentStep",
    "Shipment",
    "Solution",
    "Summary",
    "VehicleRoute",
    "RouteStep",
    "Unassigned",
]

# TimeWindow is an inclusive [start, end] pair, in seconds, relative to the
# same origin used by the rest of the request.
TimeWindow = Tuple[int, int]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


def _omit(d: dict, key: str, value) -> None:
    """Set d[key] = value unless the value is empty in the Go omitempty
    sense: None, an empty sequence, an empty string, or zero (False == 0)."""
    if value is None:
        return
    if isinstance(value, (list, tuple)) and not value:
        return
    if isinstance(value, str) and not value:
        return
    if isinstance(value, (int, float)) and value == 0:
        return
    d[key] = value


@dataclass
class OptimizationOptions:
    """Tunes solver behaviour.

    Attributes:
        geometry: Request a road-following geometry for each route. It
            costs extra computation, so it is off by default.
    """

    geometry: bool = False

    def to_dict(self) -> dict:
        d = {}
        if self.geometry:
            d["g"] = True
        return d


@dataclass
class CustomMatrix:
    """A user-supplied travel-time, distance or cost matrix for one routing
    profile. Values are read as matrix[row][column]; rows and columns are
    indexed by the ``*_index`` fields on vehicles and tasks.

    Attributes:
        durations: A travel-time matrix in seconds. Providing it for every
            profile in use makes locations optional.
        distances: A distance matrix in metres. It requires ``durations``.
        costs: A cost matrix used in all route cost evaluations.
    """

    durations: List[List[int]] = field(default_factory=list)
    distances: List[List[int]] = field(default_factory=list)
    costs: List[List[int]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "CustomMatrix":
        return cls(
            durations=d.get("durations") or [],
            distances=d.get("distances") or [],
            costs=d.get("costs") or [],
        )

    def to_dict(self) -> dict:
        d = {}
        _omit(d, "durations", self.durations)
        _omit(d, "distances", self.distances)
        _omit(d, "costs", self.costs)
        return d


@dataclass
class Break:
    """A rest period scheduled during a vehicle's route.

    Attributes:
        id: Identifies the break. It must be unique within the vehicle.
        time_windows: Bound when the break may start.
        service: The break length in seconds.
        description: An opaque label echoed back in the solution.
        max_load: The maximum load, per capacity dimension, under which
            the break may happen.
    """

    id: int = 0
    time_windows: List[TimeWindow] = field(default_factory=list)
    service: int = 0
    description: str = ""
    max_load: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Break":
        return cls(
            id=d.get("id", 0),
            time_windows=[tuple(tw) for tw in d.get("time_windows") or []],
            service=d.get("service", 0),
            description=d.get("description", ""),
            max_load=d.get("max_load") or [],
        )

    def to_dict(self) -> dict:
        d = {"id": self.id}
        _omit(d, "time_windows", self.time_windows)
        _omit(d, "service", self.service)
        _omit(d, "description", self.description)
        _omit(d, "max_load", self.max_load)
        return d


@dataclass
class VehicleCosts:
    """Adjusts how the solver values one vehicle.

    Attributes:
        fixed: The one-time cost of using this vehicle. Defaults to 0.
        per_hour: The cost of one hour of travel time. Defaults to 3600.
        per_task_hour: The cost of one hour of task time (setup + service).
            Defaults to 0.
        per_km: The cost of one kilometre of travel. Defaults to 0.
    """

    fixed: int = 0
    per_hour: int = 0
    per_task_hour: int = 0
    per_km: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleCosts":
        return cls(
            fixed=d.get("fixed", 0),
            per_hour=d.get("per_hour", 0),
            per_task_hour=d.get("per_task_hour", 0),
            per_km=d.get("per_km", 0),
        )

    def to_dict(self) -> dict:
        d = {}
        _omit(d, "fixed", self.fixed)
        _omit(d, "per_hour", self.per_hour)
        _omit(d, "per_task_hour", self.per_task_hour)
        _omit(d, "per_km", self.per_km)
        return d


@dataclass
class VehicleStep:
    """One entry of a custom route on a [Vehicle]. The hosted API runs in
    solving mode, where steps warm-start the search and only the ``"job"``,
    ``"pickup"`` and ``"delivery"`` step types are used.

    Attributes:
        type: ``"job"``, ``"pickup"`` or ``"delivery"``.
        id: The task ID this step refers to.
    """

    type: str = ""
    id: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleStep":
        return cls(
            type=d.get("type", ""),
            id=d.get("id", 0),
        )

    def to_dict(self) -> dict:
        d = {"type": self.type}
        _omit(d, "id", self.id)
        return d


@dataclass
class Violation:
    """One constraint violation. Violations are always empty in solving
    mode, the only mode the hosted API runs, but the fields exist for API
    completeness.

    Attributes:
        cause: The violated constraint, e.g. "delay", "skills" or
            "missing_break".
        duration: The lateness in seconds for "delay" causes, earliness for
            "lead_time".
    """

    cause: str = ""
    duration: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Violation":
        return cls(
            cause=d.get("cause", ""),
            duration=d.get("duration", 0),
        )


@dataclass
class Vehicle:
    """One member of the fleet.

    Attributes:
        id: Identifies the vehicle in the solution. It must be unique.
        profile: The routing profile for this vehicle.
        start: Where the vehicle begins, as [longitude, latitude]. Omit for
            a vehicle that may start anywhere.
        start_index: The row/column in custom matrices that replaces
            ``start``.
        end: Where the vehicle must finish. Omit to end anywhere.
        end_index: The row/column in custom matrices that replaces ``end``.
        capacity: A multidimensional capacity vector. Its length must match
            the ``delivery`` and ``pickup`` vectors on tasks.
        skills: Capabilities this vehicle provides.
        type: Names this vehicle for per-type setup and service times on
            tasks.
        time_window: Bounds when the vehicle is available.
        breaks: Rest periods during the route.
        speed_factor: Scales all travel times for this vehicle, in (0, 5].
        max_tasks: Caps how many tasks the vehicle may be assigned.
        max_travel_time: Caps total travel time in seconds.
        max_distance: Caps total travel distance in metres.
        costs: Adjusts how the solver values this vehicle.
        steps: A custom route used to warm-start the search.
        description: An opaque label echoed back in the solution.
    """

    id: int = 0
    profile: str = ""
    start: PointLike = field(default_factory=Point)
    start_index: Optional[int] = None
    end: PointLike = field(default_factory=Point)
    end_index: Optional[int] = None
    capacity: List[int] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)
    type: str = ""
    time_window: Optional[TimeWindow] = None
    breaks: List[Break] = field(default_factory=list)
    speed_factor: float = 0.0
    max_tasks: int = 0
    max_travel_time: int = 0
    max_distance: int = 0
    costs: Optional[VehicleCosts] = None
    steps: List[VehicleStep] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.start = _point(self.start)
        self.end = _point(self.end)
        self.breaks = [
            b if isinstance(b, Break) else Break.from_dict(b) for b in self.breaks
        ]
        self.steps = [
            s if isinstance(s, VehicleStep) else VehicleStep.from_dict(s)
            for s in self.steps
        ]

    @classmethod
    def from_dict(cls, d: dict) -> "Vehicle":
        return cls(
            id=d.get("id", 0),
            profile=d.get("profile", ""),
            start=_point(d.get("start")),
            start_index=d.get("start_index"),
            end=_point(d.get("end")),
            end_index=d.get("end_index"),
            capacity=d.get("capacity") or [],
            skills=d.get("skills") or [],
            type=d.get("type", ""),
            time_window=tuple(d["time_window"]) if d.get("time_window") else None,
            breaks=[Break.from_dict(b) for b in d.get("breaks") or []],
            speed_factor=d.get("speed_factor", 0.0),
            max_tasks=d.get("max_tasks", 0),
            max_travel_time=d.get("max_travel_time", 0),
            max_distance=d.get("max_distance", 0),
            costs=VehicleCosts.from_dict(d["costs"]) if d.get("costs") else None,
            steps=[VehicleStep.from_dict(s) for s in d.get("steps") or []],
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id}
        _omit(d, "profile", self.profile)
        _omit(d, "start", self.start)
        # 0 is a valid matrix row, so indices are only omitted when unset.
        if self.start_index is not None:
            d["start_index"] = self.start_index
        _omit(d, "end", self.end)
        if self.end_index is not None:
            d["end_index"] = self.end_index
        _omit(d, "capacity", self.capacity)
        _omit(d, "skills", self.skills)
        _omit(d, "type", self.type)
        _omit(d, "time_window", self.time_window)
        if self.breaks:
            d["breaks"] = [b.to_dict() for b in self.breaks]
        _omit(d, "speed_factor", self.speed_factor)
        _omit(d, "max_tasks", self.max_tasks)
        _omit(d, "max_travel_time", self.max_travel_time)
        _omit(d, "max_distance", self.max_distance)
        if self.costs is not None:
            d["costs"] = self.costs.to_dict()
        if self.steps:
            d["steps"] = [s.to_dict() for s in self.steps]
        _omit(d, "description", self.description)
        return d


@dataclass
class Job:
    """A task carried out at a single location.

    Attributes:
        id: Identifies the job in the solution. It must be unique.
        location: Where the job happens, as [longitude, latitude]. Omit
            when custom matrices cover every profile in use; then
            ``location_index`` is required.
        location_index: The row/column in custom matrices that replaces
            ``location``.
        setup: Fixed preparation time in seconds.
        service: Time spent on site, in seconds.
        setup_per_type: Setup overrides for vehicles of each named type.
        service_per_type: Service overrides for vehicles of each named
            type.
        delivery: The amount unloaded here, matching vehicle ``capacity``.
        pickup: The amount loaded here, matching vehicle ``capacity``.
        skills: Capabilities a vehicle must have to serve this job.
        priority: Ranks this job from 0 to 100 when not everything fits.
        time_windows: Constrains when the job may be served.
        description: An opaque label echoed back in the solution.
    """

    id: int = 0
    location: PointLike = field(default_factory=Point)
    location_index: Optional[int] = None
    setup: int = 0
    service: int = 0
    setup_per_type: Dict[str, int] = field(default_factory=dict)
    service_per_type: Dict[str, int] = field(default_factory=dict)
    delivery: List[int] = field(default_factory=list)
    pickup: List[int] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)
    priority: int = 0
    time_windows: List[TimeWindow] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.location = _point(self.location)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(
            id=d.get("id", 0),
            location=_point(d.get("location")),
            location_index=d.get("location_index"),
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            setup_per_type=d.get("setup_per_type") or {},
            service_per_type=d.get("service_per_type") or {},
            delivery=d.get("delivery") or [],
            pickup=d.get("pickup") or [],
            skills=d.get("skills") or [],
            priority=d.get("priority", 0),
            time_windows=[tuple(tw) for tw in d.get("time_windows") or []],
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id}
        _omit(d, "location", self.location)
        # 0 is a valid matrix row, so the index is only omitted when unset.
        if self.location_index is not None:
            d["location_index"] = self.location_index
        _omit(d, "setup", self.setup)
        _omit(d, "service", self.service)
        _omit(d, "setup_per_type", self.setup_per_type)
        _omit(d, "service_per_type", self.service_per_type)
        _omit(d, "delivery", self.delivery)
        _omit(d, "pickup", self.pickup)
        _omit(d, "skills", self.skills)
        _omit(d, "priority", self.priority)
        _omit(d, "time_windows", self.time_windows)
        _omit(d, "description", self.description)
        return d


@dataclass
class ShipmentStep:
    """One half of a [Shipment].

    Attributes:
        location: Where the step happens, as [longitude, latitude]. Omit
            when custom matrices cover every profile in use; then
            ``location_index`` is required.
        location_index: The row/column in custom matrices that replaces
            ``location``.
        setup_per_type: Setup overrides for vehicles of each named type.
        service_per_type: Service overrides for vehicles of each named
            type.
    """

    id: int = 0
    location: PointLike = field(default_factory=Point)
    location_index: Optional[int] = None
    setup: int = 0
    service: int = 0
    setup_per_type: Dict[str, int] = field(default_factory=dict)
    service_per_type: Dict[str, int] = field(default_factory=dict)
    time_windows: List[TimeWindow] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.location = _point(self.location)

    @classmethod
    def from_dict(cls, d: dict) -> "ShipmentStep":
        return cls(
            id=d.get("id", 0),
            location=_point(d.get("location")),
            location_index=d.get("location_index"),
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            setup_per_type=d.get("setup_per_type") or {},
            service_per_type=d.get("service_per_type") or {},
            time_windows=[tuple(tw) for tw in d.get("time_windows") or []],
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id}
        _omit(d, "location", self.location)
        # 0 is a valid matrix row, so the index is only omitted when unset.
        if self.location_index is not None:
            d["location_index"] = self.location_index
        _omit(d, "setup", self.setup)
        _omit(d, "service", self.service)
        _omit(d, "setup_per_type", self.setup_per_type)
        _omit(d, "service_per_type", self.service_per_type)
        _omit(d, "time_windows", self.time_windows)
        _omit(d, "description", self.description)
        return d


@dataclass
class Shipment:
    """A pickup and a delivery that must be served in order by the same
    vehicle.

    Attributes:
        pickup: Where the load is collected.
        delivery: Where the load is dropped off.
        amount: The load carried between the two steps.
        skills: Capabilities a vehicle must have.
        priority: Ranks this shipment from 0 to 100.
    """

    pickup: Optional[ShipmentStep] = None
    delivery: Optional[ShipmentStep] = None
    amount: List[int] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)
    priority: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Shipment":
        pickup = d.get("pickup")
        delivery = d.get("delivery")
        return cls(
            pickup=ShipmentStep.from_dict(pickup) if pickup else None,
            delivery=ShipmentStep.from_dict(delivery) if delivery else None,
            amount=d.get("amount") or [],
            skills=d.get("skills") or [],
            priority=d.get("priority", 0),
        )

    def to_dict(self) -> dict:
        d = {}
        if self.pickup is not None:
            d["pickup"] = self.pickup.to_dict()
        if self.delivery is not None:
            d["delivery"] = self.delivery.to_dict()
        _omit(d, "amount", self.amount)
        _omit(d, "skills", self.skills)
        _omit(d, "priority", self.priority)
        return d


@dataclass
class OptimizationRequest:
    """A vehicle routing problem. At least one vehicle and at least one job
    or shipment are required.

    Fleet and task counts are capped by the account plan; exceeding either
    raises [PlanLimitExceededError].

    Attributes:
        vehicles: The available fleet.
        jobs: Single-location tasks.
        shipments: Pickup-and-delivery pairs handled by one vehicle.
        matrices: Custom matrices per routing profile; the map keys are
            profile names such as "car" or "motorcycle".
        options: Tunes the solver.
    """

    vehicles: List[Vehicle] = field(default_factory=list)
    jobs: List[Job] = field(default_factory=list)
    shipments: List[Shipment] = field(default_factory=list)
    matrices: Dict[str, CustomMatrix] = field(default_factory=dict)
    options: Optional[OptimizationOptions] = None

    def __post_init__(self) -> None:
        self.vehicles = [
            v if isinstance(v, Vehicle) else Vehicle.from_dict(v) for v in self.vehicles
        ]
        self.jobs = [j if isinstance(j, Job) else Job.from_dict(j) for j in self.jobs]
        self.shipments = [
            s if isinstance(s, Shipment) else Shipment.from_dict(s)
            for s in self.shipments
        ]
        self.matrices = {
            k: m if isinstance(m, CustomMatrix) else CustomMatrix.from_dict(m)
            for k, m in self.matrices.items()
        }

    def to_dict(self) -> dict:
        d = {"vehicles": [v.to_dict() for v in self.vehicles]}
        if self.jobs:
            d["jobs"] = [j.to_dict() for j in self.jobs]
        if self.shipments:
            d["shipments"] = [s.to_dict() for s in self.shipments]
        if self.matrices:
            d["matrices"] = {k: m.to_dict() for k, m in self.matrices.items()}
        if self.options is not None:
            d["options"] = self.options.to_dict()
        return d


@dataclass
class Solution:
    """The result of an optimization run.

    Attributes:
        code: The engine status, 0 on success.
        error: Explains a non-zero ``code``.
        summary: Aggregates the whole solution.
        routes: One entry per vehicle that was used.
        unassigned: Tasks that could not be served.
    """

    code: int = 0
    error: str = ""
    summary: "Summary" = field(default_factory=lambda: Summary())
    routes: List["VehicleRoute"] = field(default_factory=list)
    unassigned: List["Unassigned"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Solution":
        return cls(
            code=d.get("code", 0),
            error=d.get("error", ""),
            summary=Summary.from_dict(d.get("summary") or {}),
            routes=[VehicleRoute.from_dict(r) for r in d.get("routes") or []],
            unassigned=[Unassigned.from_dict(u) for u in d.get("unassigned") or []],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is ok."""
        if self.code == 0:
            return None
        message = self.error or f"optimization engine returned code {self.code}"
        return Error(status_code=200, vroom_code=self.code, message=message)


@dataclass
class Summary:
    """Aggregates the cost and time of a whole [Solution]."""

    cost: int = 0
    routes: int = 0
    unassigned: int = 0
    delivery: List[int] = field(default_factory=list)
    pickup: List[int] = field(default_factory=list)
    setup: int = 0
    service: int = 0
    duration: int = 0
    waiting_time: int = 0
    priority: int = 0
    distance: int = 0
    violations: List[Violation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Summary":
        return cls(
            cost=d.get("cost", 0),
            routes=d.get("routes", 0),
            unassigned=d.get("unassigned", 0),
            delivery=d.get("delivery") or [],
            pickup=d.get("pickup") or [],
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            duration=d.get("duration", 0),
            waiting_time=d.get("waiting_time", 0),
            priority=d.get("priority", 0),
            distance=d.get("distance", 0),
            violations=[Violation.from_dict(v) for v in d.get("violations") or []],
        )


@dataclass
class VehicleRoute:
    """The itinerary assigned to one vehicle.

    Attributes:
        vehicle: The ID of the vehicle serving this route.
        geometry: An encoded polyline, present only when
            [OptimizationOptions.geometry] was set.
        steps: The stops in visiting order.
    """

    vehicle: int = 0
    cost: int = 0
    setup: int = 0
    service: int = 0
    duration: int = 0
    waiting_time: int = 0
    priority: int = 0
    distance: int = 0
    delivery: List[int] = field(default_factory=list)
    pickup: List[int] = field(default_factory=list)
    description: str = ""
    geometry: str = ""
    steps: List["RouteStep"] = field(default_factory=list)
    violations: List[Violation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleRoute":
        return cls(
            vehicle=d.get("vehicle", 0),
            cost=d.get("cost", 0),
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            duration=d.get("duration", 0),
            waiting_time=d.get("waiting_time", 0),
            priority=d.get("priority", 0),
            distance=d.get("distance", 0),
            delivery=d.get("delivery") or [],
            pickup=d.get("pickup") or [],
            description=d.get("description", ""),
            geometry=d.get("geometry", ""),
            steps=[RouteStep.from_dict(s) for s in d.get("steps") or []],
            violations=[Violation.from_dict(v) for v in d.get("violations") or []],
        )


@dataclass
class RouteStep:
    """A single stop on a [VehicleRoute].

    Attributes:
        type: One of "start", "job", "pickup", "delivery", "break" or "end".
        location: Where the stop happens.
        id: The task ID, for task steps.
        job: The job ID, for job steps.
        arrival: The arrival time in seconds.
        load: The vehicle load after this stop.
    """

    type: str = ""
    location: Point = field(default_factory=Point)
    location_index: int = 0
    id: int = 0
    job: int = 0
    setup: int = 0
    service: int = 0
    waiting_time: int = 0
    arrival: int = 0
    duration: int = 0
    distance: int = 0
    load: List[int] = field(default_factory=list)
    description: str = ""
    violations: List[Violation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "RouteStep":
        return cls(
            type=d.get("type", ""),
            location=_point(d.get("location")),
            location_index=d.get("location_index", 0),
            id=d.get("id", 0),
            job=d.get("job", 0),
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            waiting_time=d.get("waiting_time", 0),
            arrival=d.get("arrival", 0),
            duration=d.get("duration", 0),
            distance=d.get("distance", 0),
            load=d.get("load") or [],
            description=d.get("description", ""),
            violations=[Violation.from_dict(v) for v in d.get("violations") or []],
        )


@dataclass
class Unassigned:
    """A task the solver could not fit into any route."""

    id: int = 0
    type: str = ""
    location: Point = field(default_factory=Point)
    location_index: int = 0
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Unassigned":
        return cls(
            id=d.get("id", 0),
            type=d.get("type", ""),
            location=_point(d.get("location")),
            location_index=d.get("location_index", 0),
            description=d.get("description", ""),
        )


class OptimizationService:
    """Solves vehicle routing problems: given a fleet and a set of tasks, it
    assigns tasks to vehicles and orders each vehicle's stops."""

    def __init__(self, transport) -> None:
        self._client = transport

    def solve(
        self, req: OptimizationRequest, *, timeout: Optional[float] = None
    ) -> Solution:
        """Assign the request's tasks to its vehicles and order each route.

            solution = client.optimization.solve(justrouting.OptimizationRequest(
                vehicles=[justrouting.Vehicle(id=1, start=depot, end=depot)],
                jobs=[justrouting.Job(id=1, location=stop_a)],
            ))

        All coordinates in a request must lie within a single country;
        otherwise the call raises [CrossCountryError].
        """
        validate_request(req)

        return self._client.do(
            "POST",
            "/optimize",
            body=req.to_dict(),
            needs_auth=True,
            model=Solution,
            timeout=timeout,
        )


def validate_request(req: Optional[OptimizationRequest]) -> None:
    """Reject malformed requests locally, before a request is spent."""
    if req is None:
        raise InvalidRequestError("justrouting: request must not be None")
    if not req.vehicles:
        raise InvalidRequestError("justrouting: at least one Vehicle is required")
    if not req.jobs and not req.shipments:
        raise InvalidRequestError("justrouting: at least one Job or Shipment is required")

    for i, v in enumerate(req.vehicles):
        # Start and End are both optional, but must be valid when given. A
        # custom-matrix row counts as an anchor just like coordinates.
        if v.start:
            try:
                v.start.validate()
            except InvalidCoordinatesError as e:
                raise InvalidCoordinatesError(f"Vehicles[{i}].Start: {e}") from e
        if v.end:
            try:
                v.end.validate()
            except InvalidCoordinatesError as e:
                raise InvalidCoordinatesError(f"Vehicles[{i}].End: {e}") from e
        if (
            not v.start
            and v.start_index is None
            and not v.end
            and v.end_index is None
        ):
            raise InvalidRequestError(
                f"justrouting: Vehicles[{i}] needs a Start, StartIndex, End or EndIndex"
            )

    for i, j in enumerate(req.jobs):
        if j.location:
            try:
                j.location.validate()
            except InvalidCoordinatesError as e:
                raise InvalidCoordinatesError(f"Jobs[{i}].Location: {e}") from e
        if not j.location and j.location_index is None:
            raise InvalidRequestError(
                f"justrouting: Jobs[{i}] needs a Location or a LocationIndex"
            )

    for i, s in enumerate(req.shipments):
        if s.pickup is not None:
            if s.pickup.location:
                try:
                    s.pickup.location.validate()
                except InvalidCoordinatesError as e:
                    raise InvalidCoordinatesError(
                        f"Shipments[{i}].Pickup.Location: {e}"
                    ) from e
            if not s.pickup.location and s.pickup.location_index is None:
                raise InvalidRequestError(
                    f"justrouting: Shipments[{i}].Pickup needs a Location or a LocationIndex"
                )
        if s.delivery is not None:
            if s.delivery.location:
                try:
                    s.delivery.location.validate()
                except InvalidCoordinatesError as e:
                    raise InvalidCoordinatesError(
                        f"Shipments[{i}].Delivery.Location: {e}"
                    ) from e
            if not s.delivery.location and s.delivery.location_index is None:
                raise InvalidRequestError(
                    f"justrouting: Shipments[{i}].Delivery needs a Location or a LocationIndex"
                )
