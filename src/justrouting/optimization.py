"""The Optimization service: solve vehicle routing problems — given a fleet
and a set of tasks, it assigns tasks to vehicles and orders each vehicle's
stops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .error import Error, InvalidCoordinatesError, InvalidRequestError
from .geo import Point, PointLike

__all__ = [
    "OptimizationService",
    "OptimizationRequest",
    "OptimizationOptions",
    "TimeWindow",
    "Vehicle",
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
class Vehicle:
    """One member of the fleet.

    Attributes:
        id: Identifies the vehicle in the solution. It must be unique.
        profile: The routing profile for this vehicle.
        start: Where the vehicle begins, as [longitude, latitude]. Omit for
            a vehicle that may start anywhere.
        end: Where the vehicle must finish. Omit to end anywhere.
        capacity: A multidimensional capacity vector. Its length must match
            the ``delivery`` and ``pickup`` vectors on tasks.
        skills: Capabilities this vehicle provides.
        time_window: Bounds when the vehicle is available.
        max_tasks: Caps how many tasks the vehicle may be assigned.
        description: An opaque label echoed back in the solution.
    """

    id: int = 0
    profile: str = ""
    start: PointLike = field(default_factory=Point)
    end: PointLike = field(default_factory=Point)
    capacity: List[int] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)
    time_window: Optional[TimeWindow] = None
    max_tasks: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        self.start = _point(self.start)
        self.end = _point(self.end)

    @classmethod
    def from_dict(cls, d: dict) -> "Vehicle":
        return cls(
            id=d.get("id", 0),
            profile=d.get("profile", ""),
            start=_point(d.get("start")),
            end=_point(d.get("end")),
            capacity=d.get("capacity") or [],
            skills=d.get("skills") or [],
            time_window=tuple(d["time_window"]) if d.get("time_window") else None,
            max_tasks=d.get("max_tasks", 0),
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id}
        _omit(d, "profile", self.profile)
        _omit(d, "start", self.start)
        _omit(d, "end", self.end)
        _omit(d, "capacity", self.capacity)
        _omit(d, "skills", self.skills)
        _omit(d, "time_window", self.time_window)
        _omit(d, "max_tasks", self.max_tasks)
        _omit(d, "description", self.description)
        return d


@dataclass
class Job:
    """A task carried out at a single location.

    Attributes:
        id: Identifies the job in the solution. It must be unique.
        location: Where the job happens, as [longitude, latitude].
        setup: Fixed preparation time in seconds.
        service: Time spent on site, in seconds.
        delivery: The amount unloaded here, matching vehicle ``capacity``.
        pickup: The amount loaded here, matching vehicle ``capacity``.
        skills: Capabilities a vehicle must have to serve this job.
        priority: Ranks this job from 0 to 100 when not everything fits.
        time_windows: Constrains when the job may be served.
        description: An opaque label echoed back in the solution.
    """

    id: int = 0
    location: PointLike = field(default_factory=Point)
    setup: int = 0
    service: int = 0
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
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            delivery=d.get("delivery") or [],
            pickup=d.get("pickup") or [],
            skills=d.get("skills") or [],
            priority=d.get("priority", 0),
            time_windows=[tuple(tw) for tw in d.get("time_windows") or []],
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id, "location": self.location}
        _omit(d, "setup", self.setup)
        _omit(d, "service", self.service)
        _omit(d, "delivery", self.delivery)
        _omit(d, "pickup", self.pickup)
        _omit(d, "skills", self.skills)
        _omit(d, "priority", self.priority)
        _omit(d, "time_windows", self.time_windows)
        _omit(d, "description", self.description)
        return d


@dataclass
class ShipmentStep:
    """One half of a [Shipment]."""

    id: int = 0
    location: PointLike = field(default_factory=Point)
    setup: int = 0
    service: int = 0
    time_windows: List[TimeWindow] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.location = _point(self.location)

    @classmethod
    def from_dict(cls, d: dict) -> "ShipmentStep":
        return cls(
            id=d.get("id", 0),
            location=_point(d.get("location")),
            setup=d.get("setup", 0),
            service=d.get("service", 0),
            time_windows=[tuple(tw) for tw in d.get("time_windows") or []],
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        d = {"id": self.id, "location": self.location}
        _omit(d, "setup", self.setup)
        _omit(d, "service", self.service)
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
        options: Tunes the solver.
    """

    vehicles: List[Vehicle] = field(default_factory=list)
    jobs: List[Job] = field(default_factory=list)
    shipments: List[Shipment] = field(default_factory=list)
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

    def to_dict(self) -> dict:
        d = {"vehicles": [v.to_dict() for v in self.vehicles]}
        if self.jobs:
            d["jobs"] = [j.to_dict() for j in self.jobs]
        if self.shipments:
            d["shipments"] = [s.to_dict() for s in self.shipments]
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
    geometry: str = ""
    steps: List["RouteStep"] = field(default_factory=list)

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
            geometry=d.get("geometry", ""),
            steps=[RouteStep.from_dict(s) for s in d.get("steps") or []],
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

    @classmethod
    def from_dict(cls, d: dict) -> "RouteStep":
        return cls(
            type=d.get("type", ""),
            location=_point(d.get("location")),
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
        )


@dataclass
class Unassigned:
    """A task the solver could not fit into any route."""

    id: int = 0
    type: str = ""
    location: Point = field(default_factory=Point)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Unassigned":
        return cls(
            id=d.get("id", 0),
            type=d.get("type", ""),
            location=_point(d.get("location")),
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
            "/vroom",
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
        # Start and End are both optional, but must be valid when given.
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
        if not v.start and not v.end:
            raise InvalidRequestError(
                f"justrouting: Vehicles[{i}] needs a Start or an End"
            )

    for i, j in enumerate(req.jobs):
        try:
            j.location.validate()
        except InvalidCoordinatesError as e:
            raise InvalidCoordinatesError(f"Jobs[{i}].Location: {e}") from e

    for i, s in enumerate(req.shipments):
        if s.pickup is not None:
            try:
                s.pickup.location.validate()
            except InvalidCoordinatesError as e:
                raise InvalidCoordinatesError(
                    f"Shipments[{i}].Pickup.Location: {e}"
                ) from e
        if s.delivery is not None:
            try:
                s.delivery.location.validate()
            except InvalidCoordinatesError as e:
                raise InvalidCoordinatesError(
                    f"Shipments[{i}].Delivery.Location: {e}"
                ) from e
