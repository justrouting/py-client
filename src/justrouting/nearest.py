"""The Nearest service: road segments closest to a coordinate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .consts import profile_or_default
from .error import Error, InvalidRequestError, osrm_status_error
from .geo import Point, PointLike, Waypoint, encode_points

__all__ = ["NearestService", "NearestRequest", "NearestResponse"]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


@dataclass
class NearestRequest:
    """A nearest-segment query. ``coordinate`` is required.

    Attributes:
        coordinate: The point to snap, as [longitude, latitude].
        number: How many nearby segments to return, ordered by distance.
            Defaults to 1.
        profile: The routing profile. Defaults to "driving".
        exclude: Road classes to avoid, such as "motorway" or "ferry".
            Supported values depend on the profile.
        bearings: Restrict the direction of travel at the coordinate:
            ``"{bearing}"`` or ``"{bearing},{range}"`` in degrees, for
            example ``"0,20"`` for north within ±20°.
        radiuses: The snapping radius in metres for the coordinate;
            ``"unlimited"`` disables snapping.
        hints: Opaque tokens from a previous response's waypoints that
            speed up snapping.
        approaches: Restrict the road direction at the waypoint: ``"curb"``,
            ``"opposite"``, or ``"unrestricted"`` (the engine default).
        snapping: How the coordinate snaps onto the road network:
            ``"default"`` (the engine default) avoids edges that cannot be
            used as start or end points; ``"any"`` snaps to any edge.
        generate_hints: Request a ``"hint"`` on every response waypoint for
            reuse in later requests. The engine does this by default; set
            to ``False`` to omit hints.
        skip_waypoints: Omit the response waypoints. They still take part
            in the nearest-segment calculation.
    """

    coordinate: PointLike = field(default_factory=Point)
    number: int = 0
    profile: str = ""
    exclude: List[str] = field(default_factory=list)
    bearings: List[str] = field(default_factory=list)
    radiuses: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    approaches: List[str] = field(default_factory=list)
    snapping: str = ""
    generate_hints: Optional[bool] = None
    skip_waypoints: bool = False

    def __post_init__(self) -> None:
        self.coordinate = _point(self.coordinate)

    def query(self) -> dict:
        q = {}
        if self.number > 0:
            q["number"] = str(self.number)
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
class NearestResponse:
    """The result of a nearest-segment query.

    Attributes:
        code: The engine status, "Ok" on success.
        message: Explains a non-Ok ``code``.
        waypoints: The segments nearest to the coordinate, best first.
    """

    code: str = ""
    message: str = ""
    waypoints: List[Waypoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "NearestResponse":
        return cls(
            code=d.get("code", ""),
            message=d.get("message", ""),
            waypoints=[Waypoint.from_dict(w) for w in d.get("waypoints") or []],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is Ok."""
        return osrm_status_error(self.code, self.message)


class NearestService:
    """Finds the road segments closest to a coordinate."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(self, req: NearestRequest, *, timeout: Optional[float] = None) -> Waypoint:
        """The road segment closest to ``req.coordinate``.

            wp = client.nearest.get(justrouting.NearestRequest(
                coordinate=[103.8198, 1.3521],
            ))
            print(f"snapped to {wp.name}, {wp.distance:.0f} m away")

        Use [NearestService.get_all] for the second-, third-, ... nearest
        segments.
        """
        resp = self.get_all(req, timeout=timeout)
        if not resp.waypoints:
            raise Error(
                status_code=200,
                osrm_code="NoSegment",
                message="no segment found near the given coordinate",
            )
        return resp.waypoints[0]

    def get_all(
        self, req: NearestRequest, *, timeout: Optional[float] = None
    ) -> NearestResponse:
        """Up to ``req.number`` road segments near ``req.coordinate``, best
        first."""
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        if not req.coordinate:
            raise InvalidRequestError("justrouting: Coordinate is required")
        if req.number < 0:
            raise InvalidRequestError(
                f"justrouting: Number must not be negative, got {req.number}"
            )
        coords = encode_points([req.coordinate])
        return self._client.do(
            "GET",
            "/nearest/v1/" + profile_or_default(req.profile) + "/" + coords,
            query=req.query(),
            needs_auth=True,
            model=NearestResponse,
            timeout=timeout,
        )
