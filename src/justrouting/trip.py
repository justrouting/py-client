"""The Trip service: fastest order to visit a set of coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .consts import profile_or_default
from .error import Error, InvalidRequestError, osrm_status_error
from .geo import Point, PointLike, Waypoint, encode_points
from .routes import Route

__all__ = ["TripService", "TripRequest", "TripResponse"]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


@dataclass
class TripRequest:
    """A trip query. ``coordinates`` is required and must hold at least two
    points.

    The engine solves the travelling-salesman problem with a greedy
    heuristic: the returned trip visits every coordinate once, in whatever
    order is fastest.

    Attributes:
        coordinates: The points to visit, in any order.
        roundtrip: Whether the trip ends where it started. ``None`` leaves
            the engine default, which is true.
        source: Where the trip starts: "any" (the default) or "first".
        destination: Where the trip ends: "any" (the default) or "last".
        profile: The routing profile. Defaults to "driving".
        steps: Request turn-by-turn instructions on each leg.
        annotations: Per-segment metadata. Valid values include "duration",
            "distance", "speed" and "nodes".
        geometries: The geometry encoding: "polyline" (the default),
            "polyline6" or "geojson". See [Geometry].
        overview: Geometry detail: "simplified" (the default), "full" or
            "false" to omit it.
        exclude: Road classes to avoid, such as "motorway" or "ferry".
            Supported values depend on the profile.
        bearings: Restrict the direction of travel at each coordinate, one
            entry per coordinate in visiting order: ``"{bearing}"`` or
            ``"{bearing},{range}"`` in degrees, for example ``"0,20"`` for
            north within ±20°. Coordinates without a restriction use the
            default when their entry is missing at the end of the list.
        radiuses: The snapping radius in metres per coordinate, one entry
            per coordinate in visiting order; ``"unlimited"`` disables
            snapping for that coordinate.
        hints: Opaque tokens from a previous response's waypoints that
            speed up snapping, one entry per coordinate in visiting order.
        approaches: Restrict the road direction at each waypoint, one
            entry per waypoint in visiting order: ``"curb"``, ``"opposite"``,
            or ``"unrestricted"`` (the engine default). An empty entry also
            selects the default.
        snapping: How coordinates snap onto the road network: ``"default"``
            (the engine default) avoids edges that cannot be used as start
            or end points; ``"any"`` snaps to any edge.
        generate_hints: Request a ``"hint"`` on every response waypoint for
            reuse in later requests. The engine does this by default; set
            to ``False`` to omit hints.
        skip_waypoints: Omit the response waypoints. They still take part
            in the trip calculation.
    """

    coordinates: List[PointLike] = field(default_factory=list)
    roundtrip: Optional[bool] = None
    source: str = ""
    destination: str = ""
    profile: str = ""
    steps: bool = False
    annotations: List[str] = field(default_factory=list)
    geometries: str = ""
    overview: str = ""
    exclude: List[str] = field(default_factory=list)
    bearings: List[str] = field(default_factory=list)
    radiuses: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    approaches: List[str] = field(default_factory=list)
    snapping: str = ""
    generate_hints: Optional[bool] = None
    skip_waypoints: bool = False

    def __post_init__(self) -> None:
        self.coordinates = [_point(p) for p in self.coordinates]

    def query(self) -> dict:
        q = {}
        if self.roundtrip is not None:
            q["roundtrip"] = "true" if self.roundtrip else "false"
        if self.source:
            q["source"] = self.source
        if self.destination:
            q["destination"] = self.destination
        if self.steps:
            q["steps"] = "true"
        if self.annotations:
            q["annotations"] = ",".join(self.annotations)
        if self.geometries:
            q["geometries"] = self.geometries
        if self.overview:
            q["overview"] = self.overview
        if self.exclude:
            q["exclude"] = ",".join(self.exclude)
        if self.bearings:
            q["bearings"] = ";".join(self.bearings)
        if self.radiuses:
            q["radiuses"] = ";".join(self.radiuses)
        if self.hints:
            q["hints"] = ";".join(self.hints)
        if self.approaches:
            q["approaches"] = ";".join(self.approaches)
        if self.snapping:
            q["snapping"] = self.snapping
        if self.generate_hints is not None:
            q["generate_hints"] = "true" if self.generate_hints else "false"
        if self.skip_waypoints:
            q["skip_waypoints"] = "true"
        return q


@dataclass
class TripResponse:
    """The full result of a trip query.

    Attributes:
        code: The engine status, "Ok" on success.
        message: Explains a non-Ok ``code``.
        trips: The candidate round trips, best first.
        waypoints: The input coordinates snapped to the road network, in
            the order the trip visits them.
    """

    code: str = ""
    message: str = ""
    trips: List[Optional[Route]] = field(default_factory=list)
    waypoints: List[Waypoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "TripResponse":
        return cls(
            code=d.get("code", ""),
            message=d.get("message", ""),
            trips=[
                None if t is None else Route.from_dict(t) for t in d.get("trips") or []
            ],
            waypoints=[Waypoint.from_dict(w) for w in d.get("waypoints") or []],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is Ok."""
        return osrm_status_error(self.code, self.message)


class TripService:
    """Finds the fastest order to visit a set of coordinates."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(self, req: TripRequest, *, timeout: Optional[float] = None) -> Route:
        """The best trip for ``req``.

            trip = client.trip.get(justrouting.TripRequest(
                coordinates=[depot, stop_a, stop_b],
            ))
            print(f"fastest order covers {trip.distance / 1000:.1f} km")

        The waypoints in [TripResponse.waypoints] are ordered as visited.
        Use [TripService.get_all] to retrieve them.
        """
        resp = self.get_all(req, timeout=timeout)
        if not resp.trips or resp.trips[0] is None:
            raise Error(
                status_code=200,
                osrm_code="NoTrip",
                message="no trip found for the given coordinates",
            )
        return resp.trips[0]

    def get_all(
        self, req: TripRequest, *, timeout: Optional[float] = None
    ) -> TripResponse:
        """Every trip the engine produced for ``req``, along with the
        snapped waypoints in visiting order."""
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        if len(req.coordinates) < 2:
            raise InvalidRequestError(
                f"justrouting: Coordinates needs at least 2 points, got {len(req.coordinates)}"
            )
        coords = encode_points(req.coordinates)
        return self._client.do(
            "GET",
            "/trip/v1/" + profile_or_default(req.profile) + "/" + coords,
            query=req.query(),
            needs_auth=True,
            model=TripResponse,
            timeout=timeout,
        )
