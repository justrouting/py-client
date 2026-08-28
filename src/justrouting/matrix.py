"""The Matrix service: travel duration and distance between many
coordinates at once."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .consts import profile_or_default
from .error import InvalidRequestError, osrm_status_error
from .geo import Point, Waypoint, encode_points

__all__ = ["MatrixService", "MatrixRequest", "MatrixResponse"]


def _point(p) -> Point:
    return p if isinstance(p, Point) else (Point(p) if p is not None else Point())


@dataclass
class MatrixRequest:
    """A matrix query. ``coordinates`` is required and must hold at least
    two points.

    By default every coordinate is used as both a source and a destination,
    producing an NxN matrix. Set ``sources`` and/or ``destinations`` to
    compute a rectangular subset instead, which is considerably cheaper.

    The number of coordinates is capped by the account plan; exceeding it
    raises [PlanLimitExceededError].

    Attributes:
        coordinates: The points to measure between.
        sources: Which coordinates act as row origins, by index into
            ``coordinates``. Empty means all of them.
        destinations: Which coordinates act as column targets, by index
            into ``coordinates``. Empty means all of them.
        annotations: Which matrices to compute: "duration", "distance", or
            both. Defaults to both.
        profile: The routing profile. Defaults to "driving".
    """

    coordinates: List[Point] = field(default_factory=list)
    sources: List[int] = field(default_factory=list)
    destinations: List[int] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    profile: str = ""

    def __post_init__(self) -> None:
        self.coordinates = [_point(p) for p in self.coordinates]

    def query(self) -> dict:
        q = {}

        annotations = self.annotations or ["duration", "distance"]
        q["annotations"] = ",".join(annotations)

        sources = encode_indices("Sources", self.sources, len(self.coordinates))
        if sources:
            q["sources"] = sources

        destinations = encode_indices(
            "Destinations", self.destinations, len(self.coordinates)
        )
        if destinations:
            q["destinations"] = destinations

        return q


@dataclass
class MatrixResponse:
    """The computed matrices.

    Entries may be ``None`` because the engine reports an unreachable pair
    as null, which must stay distinguishable from a genuine zero. Prefer the
    [MatrixResponse.duration] and [MatrixResponse.distance] accessors.

    Attributes:
        code: The engine status, "Ok" on success.
        message: Explains a non-Ok ``code``.
        durations: Travel times in seconds, indexed [source][destination].
        distances: Travel distances in metres, indexed
            [source][destination].
        sources: The source coordinates snapped to the road network.
        destinations: The destination coordinates snapped to the road
            network.
    """

    code: str = ""
    message: str = ""
    durations: Optional[List[List[Optional[float]]]] = None
    distances: Optional[List[List[Optional[float]]]] = None
    sources: List[Waypoint] = field(default_factory=list)
    destinations: List[Waypoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "MatrixResponse":
        return cls(
            code=d.get("code", ""),
            message=d.get("message", ""),
            durations=d.get("durations"),
            distances=d.get("distances"),
            sources=[Waypoint.from_dict(w) for w in d.get("sources") or []],
            destinations=[
                Waypoint.from_dict(w) for w in d.get("destinations") or []
            ],
        )

    def api_error(self):
        """An in-body engine failure, or None when the response is Ok."""
        return osrm_status_error(self.code, self.message)

    def duration(self, i: int, j: int) -> Optional[float]:
        """The travel time in seconds from source ``i`` to destination
        ``j``, or ``None`` when the indices are out of range or the pair is
        unreachable."""
        return matrix_at(self.durations, i, j)

    def distance(self, i: int, j: int) -> Optional[float]:
        """The travel distance in metres from source ``i`` to destination
        ``j``, or ``None`` when the indices are out of range or the pair is
        unreachable."""
        return matrix_at(self.distances, i, j)


def matrix_at(m, i: int, j: int) -> Optional[float]:
    if m is None or not 0 <= i < len(m):
        return None
    row = m[i]
    if not 0 <= j < len(row):
        return None
    return row[j]


class MatrixService:
    """Computes travel duration and distance between many coordinates at
    once."""

    def __init__(self, transport) -> None:
        self._client = transport

    def get(self, req: MatrixRequest, *, timeout: Optional[float] = None) -> MatrixResponse:
        """Compute the duration and distance matrices for ``req``.

            m = client.matrix.get(justrouting.MatrixRequest(
                coordinates=[depot, stop_a, stop_b],
                sources=[0],            # only the depot row; cheaper than NxN
                destinations=[1, 2],
            ))
            seconds = m.duration(0, 1)
            if seconds is not None:
                print(f"depot -> stopA: {seconds / 60:.0f} min")
        """
        if req is None:
            raise InvalidRequestError("justrouting: request must not be None")
        if len(req.coordinates) < 2:
            raise InvalidRequestError(
                f"justrouting: Coordinates needs at least 2 points, got {len(req.coordinates)}"
            )
        coords = encode_points(req.coordinates)

        return self._client.do(
            "GET",
            "/osrm/table/v1/" + profile_or_default(req.profile) + "/" + coords,
            query=req.query(),
            needs_auth=True,
            model=MatrixResponse,
            timeout=timeout,
        )


def encode_indices(field: str, indices: List[int], total: int) -> str:
    """Render coordinate indices as a semicolon-separated list, rejecting
    anything outside the coordinate slice before a request is spent."""
    if not indices:
        return ""
    parts = []
    for i, idx in enumerate(indices):
        if not 0 <= idx < total:
            raise InvalidRequestError(
                f"justrouting: {field}[{i}] = {idx} is out of range for {total} coordinates"
            )
        parts.append(str(idx))
    return ";".join(parts)
