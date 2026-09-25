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
