"""The Routes service: fastest route between coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .consts import profile_or_default
from .error import InvalidRequestError, NoRouteError, osrm_status_error
from .geo import Geometry, LineString, Point, PointLike, Waypoint, encode_points

__all__ = [
    "RoutesService",
    "RouteRequest",
    "RouteResponse",
    "Route",
    "Leg",
    "Step",
    "Maneuver",
    "Intersection",
    "Lane",
    "Annotation",
]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


@dataclass
class RouteRequest:
    """A routing query. ``origin`` and ``destination`` are required; every
    other field is optional.

    Attributes:
        origin: Where the route starts, as [longitude, latitude].
        destination: Where the route ends, as [longitude, latitude].
        waypoints: Intermediate stops, visited in the order given.
        profile: The routing profile. Defaults to "driving".
        alternatives: Up to this many alternative routes. They are returned
            by [RoutesService.get_all]; [RoutesService.get] always yields
            the best route. The engine may return fewer, or none, if no
            reasonable alternative exists.
        steps: Request turn-by-turn instructions on each leg.
        annotations: Per-segment metadata. Valid values include "duration",
            "distance", "speed" and "nodes".
        geometries: The geometry encoding: "polyline" (the default),
            "polyline6" or "geojson". See [Geometry].
        overview: Geometry detail: "simplified" (the default), "full" or
            "false" to omit it.
        continue_straight: Force or forbid continuing straight at the first
            waypoint. ``None`` leaves the decision to the engine.
        exclude: Road classes to avoid, such as "motorway" or "ferry".
            Supported values depend on the profile.
    """

    origin: PointLike = field(default_factory=Point)
    destination: PointLike = field(default_factory=Point)
    waypoints: List[PointLike] = field(default_factory=list)
    profile: str = ""
    alternatives: int = 0
    steps: bool = False
    annotations: List[str] = field(default_factory=list)
    geometries: str = ""
    overview: str = ""
    continue_straight: Optional[bool] = None
    exclude: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.origin = _point(self.origin)
        self.destination = _point(self.destination)
        self.waypoints = [_point(p) for p in self.waypoints]

    def coordinates(self) -> List[PointLike]:
        """Flatten the request into the order the engine expects."""
        return [self.origin, *self.waypoints, self.destination]

    def query(self) -> dict:
        q = {}
        if self.alternatives > 0:
            q["alternatives"] = str(self.alternatives)
        if self.steps:
            q["steps"] = "true"
        if self.annotations:
            q["annotations"] = ",".join(self.annotations)
        if self.geometries:
            q["geometries"] = self.geometries
        if self.overview:
            q["overview"] = self.overview
        if self.continue_straight is not None:
            q["continue_straight"] = "true" if self.continue_straight else "false"
        if self.exclude:
            q["exclude"] = ",".join(self.exclude)
        return q


@dataclass
class Route:
    """A single path through the road network.

    Attributes:
        distance: The route length in metres.
        duration: The estimated travel time in seconds.
        weight: The value the engine minimised, in ``weight_name`` units.
        weight_name: The optimisation metric, such as "routability".
        geometry: The route's shape.
        legs: One entry per consecutive pair of waypoints.
    """

    distance: float = 0.0
    duration: float = 0.0
    weight: float = 0.0
    weight_name: str = ""
    geometry: Geometry = field(default_factory=Geometry)
    legs: List["Leg"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Route":
        return cls(
            distance=d.get("distance", 0.0),
            duration=d.get("duration", 0.0),
            weight=d.get("weight", 0.0),
            weight_name=d.get("weight_name", ""),
            geometry=Geometry(d.get("geometry")),
            legs=[Leg.from_dict(leg) for leg in d.get("legs") or []],
        )


@dataclass
class Leg:
    """The portion of a route between two consecutive waypoints."""

    distance: float = 0.0
    duration: float = 0.0
    weight: float = 0.0
    summary: str = ""
    steps: List["Step"] = field(default_factory=list)
    annotation: Optional["Annotation"] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Leg":
        annotation = d.get("annotation")
        return cls(
            distance=d.get("distance", 0.0),
            duration=d.get("duration", 0.0),
            weight=d.get("weight", 0.0),
            summary=d.get("summary", ""),
            steps=[Step.from_dict(step) for step in d.get("steps") or []],
            annotation=Annotation.from_dict(annotation) if annotation else None,
        )


@dataclass
class Step:
    """A single turn-by-turn instruction, returned when
    [RouteRequest.steps] is set."""

    distance: float = 0.0
    duration: float = 0.0
    weight: float = 0.0
    geometry: Geometry = field(default_factory=Geometry)
    name: str = ""
    ref: str = ""
    mode: str = ""
    maneuver: Optional["Maneuver"] = None
    intersections: List["Intersection"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        maneuver = d.get("maneuver")
        return cls(
            distance=d.get("distance", 0.0),
            duration=d.get("duration", 0.0),
            weight=d.get("weight", 0.0),
            geometry=Geometry(d.get("geometry")),
            name=d.get("name", ""),
            ref=d.get("ref", ""),
            mode=d.get("mode", ""),
            maneuver=Maneuver.from_dict(maneuver) if maneuver else None,
            intersections=[
                Intersection.from_dict(i) for i in d.get("intersections") or []
            ],
        )


@dataclass
class Maneuver:
    """The action taken at the start of a [Step]."""

    location: Point = field(default_factory=Point)
    bearing_before: int = 0
    bearing_after: int = 0
    type: str = ""
    modifier: str = ""
    exit: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Maneuver":
        return cls(
            location=Point(d["location"]) if d.get("location") else Point(),
            bearing_before=d.get("bearing_before", 0),
            bearing_after=d.get("bearing_after", 0),
            type=d.get("type", ""),
            modifier=d.get("modifier", ""),
            exit=d.get("exit", 0),
        )


@dataclass
class Intersection:
    """A junction passed during a [Step]."""

    location: Point = field(default_factory=Point)
    bearings: List[int] = field(default_factory=list)
    entry: List[bool] = field(default_factory=list)
    in_: Optional[int] = None
    out: Optional[int] = None
    lanes: List["Lane"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Intersection":
        return cls(
            location=Point(d["location"]) if d.get("location") else Point(),
            bearings=d.get("bearings") or [],
            entry=d.get("entry") or [],
            in_=d.get("in"),
            out=d.get("out"),
            lanes=[Lane.from_dict(lane) for lane in d.get("lanes") or []],
        )


@dataclass
class Lane:
    """A turn lane at an [Intersection]."""

    indications: List[str] = field(default_factory=list)
    valid: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Lane":
        return cls(
            indications=d.get("indications") or [],
            valid=d.get("valid", False),
        )


@dataclass
class Annotation:
    """Per-segment metadata, returned when [RouteRequest.annotations] is set."""

    distance: List[float] = field(default_factory=list)
    duration: List[float] = field(default_factory=list)
    speed: List[float] = field(default_factory=list)
    weight: List[float] = field(default_factory=list)
    nodes: List[int] = field(default_factory=list)
    datasources: List[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Annotation":
        return cls(
            distance=d.get("distance") or [],
            duration=d.get("duration") or [],
            speed=d.get("speed") or [],
            weight=d.get("weight") or [],
            nodes=d.get("nodes") or [],
            datasources=d.get("datasources") or [],
        )


@dataclass
class RouteResponse:
    """The full result of a routing query.

    Attributes:
        code: The engine status, "Ok" on success.
        message: Explains a non-Ok ``code``.
        routes: Ordered best first.
        waypoints: The input coordinates snapped to the road network.
    """

    code: str = ""
    message: str = ""
    routes: List[Optional[Route]] = field(default_factory=list)
    waypoints: List[Waypoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "RouteResponse":
        return cls(
            code=d.get("code", ""),
            message=d.get("message", ""),
            routes=[
                None if r is None else Route.from_dict(r) for r in d.get("routes") or []
            ],
            waypoints=[Waypoint.from_dict(w) for w in d.get("waypoints") or []],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is Ok."""
        return osrm_status_error(self.code, self.message)


class RoutesService:
    """Computes the fastest route between coordinates."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(self, req: RouteRequest, *, timeout: Optional[float] = None) -> Route:
        """The best route for ``req``.

            route = client.routes.get(justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
            ))
            print(f"{route.distance / 1000:.1f} km")

        Raises [NoRouteError] when the coordinates cannot be connected. Use
        [RoutesService.get_all] for alternatives and snapped waypoints.
        """
        resp = self.get_all(req, timeout=timeout)
        if not resp.routes or resp.routes[0] is None:
            raise NoRouteError(
                status_code=200,
                osrm_code="NoRoute",
                message="no route found between the given coordinates",
            )
        return resp.routes[0]

    def get_all(
        self, req: RouteRequest, *, timeout: Optional[float] = None
    ) -> RouteResponse:
        """Every route the engine produced for ``req``, along with the
        snapped input waypoints."""
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        if not req.origin:
            raise InvalidRequestError("justrouting: Origin is required")
        if not req.destination:
            raise InvalidRequestError("justrouting: Destination is required")
        coords = encode_points(req.coordinates())
        return self._client.do(
            "GET",
            "/osrm/route/v1/" + profile_or_default(req.profile) + "/" + coords,
            query=req.query(),
            needs_auth=True,
            model=RouteResponse,
            timeout=timeout,
        )
