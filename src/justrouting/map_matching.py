"""The Map Matching service: snap GPS traces onto the road network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .consts import profile_or_default
from .error import Error, InvalidRequestError, osrm_status_error
from .geo import Point, PointLike, _format_coord, encode_points
from .matrix import encode_indices
from .routes import Route

__all__ = [
    "MapMatchingService",
    "MapMatchingRequest",
    "MapMatchingResponse",
    "Match",
    "Tracepoint",
]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


@dataclass
class MapMatchingRequest:
    """A map-matching query. ``coordinates`` is required and must hold at
    least two points in chronological order.

    Attributes:
        coordinates: The trace to match, in chronological order.
        timestamps: UNIX seconds for each coordinate. When set, its length
            must equal the number of coordinates.
        radiuses: The maximum distance in metres each coordinate may snap,
            one value per coordinate. The engine's default snap distance
            is only a few metres, so GPS points further from the road need
            this set.
        gaps: How a trace with gaps is matched: "split" (the default) or
            "ignore".
        tidy: Drop tracepoints that cannot be matched from the response.
        waypoints: Which coordinates to use as waypoints, by index into
            ``coordinates``. Empty means all of them.
        snapping: Edge snapping: "default" or "any".
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
    timestamps: List[int] = field(default_factory=list)
    radiuses: List[float] = field(default_factory=list)
    gaps: str = ""
    tidy: bool = False
    waypoints: List[int] = field(default_factory=list)
    snapping: str = ""
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
        if self.timestamps:
            q["timestamps"] = ";".join(str(ts) for ts in self.timestamps)
        if self.radiuses:
            q["radiuses"] = ";".join(_format_coord(r) for r in self.radiuses)
        if self.gaps:
            q["gaps"] = self.gaps
        if self.tidy:
            q["tidy"] = "true"
        if self.waypoints:
            q["waypoints"] = encode_indices(
                "Waypoints", self.waypoints, len(self.coordinates)
            )
        if self.snapping:
            q["snapping"] = self.snapping
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
class Tracepoint:
    """One input coordinate snapped to the road network.

    Attributes:
        alternatives_count: How many other plausible matches exist for this
            tracepoint.
        waypoint_index: The index of this point within the matched route's
            waypoints.
        matchings_index: Which entry of ``matchings`` this tracepoint
            belongs to.
        distance: The metres between the input coordinate and ``location``.
        name: The street the coordinate snapped to, if known.
        location: The snapped position.
        hint: An opaque token that can speed up subsequent requests.
    """

    alternatives_count: int = 0
    waypoint_index: int = 0
    matchings_index: int = 0
    distance: float = 0.0
    name: str = ""
    location: Point = field(default_factory=Point)
    hint: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Tracepoint":
        return cls(
            alternatives_count=d.get("alternatives_count", 0),
            waypoint_index=d.get("waypoint_index", 0),
            matchings_index=d.get("matchings_index", 0),
            distance=d.get("distance", 0.0),
            name=d.get("name", ""),
            location=Point(d["location"]) if d.get("location") else Point(),
            hint=d.get("hint", ""),
        )


@dataclass
class Match(Route):
    """One route assembled from a trace. It extends [Route], adding the
    engine's confidence in the match.

    Attributes:
        confidence: The engine's trust in the match, from 0 to 1.
    """

    confidence: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "Match":
        base = Route.from_dict(d)
        return cls(
            distance=base.distance,
            duration=base.duration,
            weight=base.weight,
            weight_name=base.weight_name,
            geometry=base.geometry,
            legs=base.legs,
            confidence=d.get("confidence", 0.0),
        )


@dataclass
class MapMatchingResponse:
    """The full result of a map-matching query.

    Attributes:
        code: The engine status, "Ok" on success.
        message: Explains a non-Ok ``code``.
        tracepoints: The input coordinates snapped to the road network,
            aligned with [MapMatchingRequest.coordinates]. An entry is None
            when that coordinate could not be matched.
        matchings: The routes assembled from the trace, best first.
    """

    code: str = ""
    message: str = ""
    tracepoints: List[Optional[Tracepoint]] = field(default_factory=list)
    matchings: List[Optional[Match]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "MapMatchingResponse":
        return cls(
            code=d.get("code", ""),
            message=d.get("message", ""),
            tracepoints=[
                None if tp is None else Tracepoint.from_dict(tp)
                for tp in d.get("tracepoints") or []
            ],
            matchings=[
                None if m is None else Match.from_dict(m)
                for m in d.get("matchings") or []
            ],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is Ok."""
        return osrm_status_error(self.code, self.message)


class MapMatchingService:
    """Snaps a noisy GPS trace onto the road network and assembles the
    driven route."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(
        self, req: MapMatchingRequest, *, timeout: Optional[float] = None
    ) -> Match:
        """The best matching for ``req``.

            match = client.map_matching.get(justrouting.MapMatchingRequest(
                coordinates=trace,  # GPS points, in order
            ))
            print(f"{match.confidence * 100:.0f}% confidence, "
                  f"{match.distance / 1000:.1f} km")

        Raises [Error] with ``osrm_code`` "NoMatch" when no coordinate can
        be matched. Use [MapMatchingService.get_all] for the snapped
        tracepoints.
        """
        resp = self.get_all(req, timeout=timeout)
        if not resp.matchings or resp.matchings[0] is None:
            raise Error(
                status_code=200,
                osrm_code="NoMatch",
                message="no matching found for the given coordinates",
            )
        return resp.matchings[0]

    def get_all(
        self, req: MapMatchingRequest, *, timeout: Optional[float] = None
    ) -> MapMatchingResponse:
        """Every matching the engine produced for ``req``, along with the
        snapped tracepoints."""
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        if len(req.coordinates) < 2:
            raise InvalidRequestError(
                f"justrouting: Coordinates needs at least 2 points, got {len(req.coordinates)}"
            )
        if req.timestamps and len(req.timestamps) != len(req.coordinates):
            raise InvalidRequestError(
                f"justrouting: Timestamps has {len(req.timestamps)} values "
                f"for {len(req.coordinates)} coordinates"
            )
        # The engine accepts exactly one radius per coordinate; a single
        # shared value is rejected, so catch it locally.
        if req.radiuses and len(req.radiuses) != len(req.coordinates):
            raise InvalidRequestError(
                f"justrouting: Radiuses needs one value per coordinate, "
                f"got {len(req.radiuses)} for {len(req.coordinates)} coordinates"
            )
        for i, radius in enumerate(req.radiuses):
            if radius < 0:
                raise InvalidRequestError(
                    f"justrouting: Radiuses[{i}] must not be negative, got {radius}"
                )
        coords = encode_points(req.coordinates)
        return self._client.do(
            "GET",
            "/match/v1/" + profile_or_default(req.profile) + "/" + coords,
            query=req.query(),
            needs_auth=True,
            model=MapMatchingResponse,
            timeout=timeout,
        )
