"""Geographic primitives shared by every service."""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence

from .error import InvalidCoordinatesError

__all__ = ["Point", "PointLike", "Geometry", "LineString", "Waypoint"]

# Anything the request builders accept as a [longitude, latitude] pair: a
# Point, or a plain list/tuple of two floats. Point subclasses list, so at
# runtime the two are interchangeable; PointLike is what the type checker
# sees on input fields.
PointLike = Sequence[float]


class Point(list):
    """A geographic coordinate expressed as ``[longitude, latitude]`` — the
    order used by GeoJSON, OSRM and VROOM, and the reverse of the "lat, lng"
    convention used by most map UIs.

    ``Point`` subclasses ``list``, so a plain list works anywhere a Point is
    expected::

        origin=[103.8198, 1.3521]   # Singapore
    """

    def lon(self) -> float:
        """The longitude, or 0 if the point is not a well-formed pair."""
        if len(self) < 2:
            return 0
        return self[0]

    def lat(self) -> float:
        """The latitude, or 0 if the point is not a well-formed pair."""
        if len(self) < 2:
            return 0
        return self[1]

    def validate(self) -> None:
        """Raise InvalidCoordinatesError if the point is not a well-formed
        [longitude, latitude] pair within the valid ranges."""
        if len(self) != 2:
            raise InvalidCoordinatesError(
                f"justrouting: expected [longitude, latitude], got {len(self)} value(s)"
            )
        lon, lat = self[0], self[1]
        if math.isnan(lon) or math.isnan(lat) or math.isinf(lon) or math.isinf(lat):
            raise InvalidCoordinatesError(
                "justrouting: longitude and latitude must be finite numbers"
            )
        if lon < -180 or lon > 180:
            raise InvalidCoordinatesError(
                f"justrouting: longitude {lon} is outside [-180, 180]"
            )
        if lat < -90 or lat > 90:
            # Catches the common mistake of passing [lat, lon].
            raise InvalidCoordinatesError(
                f"justrouting: latitude {lat} is outside [-90, 90] (coordinates are [longitude, latitude])"
            )

    def __str__(self) -> str:
        """Format as "longitude,latitude" using the shortest representation
        that round-trips exactly."""
        if len(self) != 2:
            return ""
        return _format_coord(self[0]) + "," + _format_coord(self[1])


def _format_coord(v: float) -> str:
    """The equivalent of Go's strconv.FormatFloat(v, 'f', -1, 64): fixed
    notation (never scientific) with the fewest digits that round-trip."""
    r = repr(v)
    if "e" not in r and "E" not in r:
        if "." in r:
            r = r.rstrip("0").rstrip(".")
        return r
    # Scientific notation: convert to fixed point with enough digits to
    # round-trip exactly.
    mantissa, sep, exp_part = r.partition("e")
    if not sep:
        mantissa, sep, exp_part = r.partition("E")
    if not sep:
        return r  # inf / nan; rejected by validation before this runs
    exponent = int(exp_part)
    digits = len(mantissa.replace(".", "").lstrip("+-"))
    precision = max(0, digits - 1 - exponent)
    return format(v, f".{precision}f").rstrip("0").rstrip(".")


def encode_points(points: List[PointLike]) -> str:
    """Render points as the "lon,lat;lon,lat" path segment that the OSRM
    services expect, validating each point along the way."""
    if not points:
        raise InvalidCoordinatesError("justrouting: at least one coordinate is required")
    parts = []
    for i, p in enumerate(points):
        point = p if isinstance(p, Point) else Point(p)
        try:
            point.validate()
        except InvalidCoordinatesError as e:
            raise InvalidCoordinatesError(f"coordinate {i}: {e}") from e
        parts.append(str(point))
    return ";".join(parts)


class Geometry:
    """A route geometry. OSRM encodes it either as an encoded polyline
    string (geometries=polyline, the default, or polyline6) or as a GeoJSON
    LineString object (geometries=geojson). Geometry preserves whichever
    form the server sent; read it with :meth:`polyline` or :meth:`geojson`.
    """

    def __init__(self, raw: Any = None) -> None:
        # raw is the decoded JSON value: a str for polylines, a dict for
        # GeoJSON, or None when the server omitted the geometry.
        self.raw = raw

    def is_zero(self) -> bool:
        """Whether the server omitted the geometry, which happens when a
        request sets overview=false."""
        return self.raw is None

    def polyline(self) -> str:
        """Return the geometry as an encoded polyline string.

        Raises ValueError if the request asked for GeoJSON instead.
        """
        if self.is_zero():
            raise ValueError("justrouting: geometry is empty")
        if not isinstance(self.raw, str):
            raise ValueError(
                'justrouting: geometry is not an encoded polyline; set Geometries to "polyline" or "polyline6"'
            )
        return self.raw

    def geojson(self) -> "LineString":
        """Return the geometry as a GeoJSON LineString.

        Raises ValueError if the request used the default polyline encoding.
        """
        if self.is_zero():
            raise ValueError("justrouting: geometry is empty")
        if not isinstance(self.raw, dict):
            raise ValueError(
                'justrouting: geometry is not GeoJSON; set Geometries to "geojson"'
            )
        return LineString.from_dict(self.raw)

    def __repr__(self) -> str:
        return f"Geometry({self.raw!r})"


class LineString:
    """A GeoJSON LineString geometry."""

    def __init__(self, type: str = "", coordinates: Optional[List[Point]] = None) -> None:
        self.type = type
        self.coordinates = coordinates or []

    @classmethod
    def from_dict(cls, d: dict) -> "LineString":
        return cls(
            type=d.get("type", ""),
            coordinates=[Point(c) for c in d.get("coordinates") or []],
        )

    def __repr__(self) -> str:
        return f"LineString(type={self.type!r}, coordinates={self.coordinates!r})"


class Waypoint:
    """An input coordinate snapped to the road network.

    Attributes:
        name: The street the coordinate snapped to, if known.
        location: The snapped position.
        distance: The metres between the input coordinate and ``location``.
        hint: An opaque token that can speed up subsequent requests.
    """

    def __init__(
        self,
        name: str = "",
        location: Optional[Point] = None,
        distance: float = 0.0,
        hint: str = "",
    ) -> None:
        self.name = name
        self.location = Point(location) if location is not None else Point()
        self.distance = distance
        self.hint = hint

    @classmethod
    def from_dict(cls, d: dict) -> "Waypoint":
        return cls(
            name=d.get("name", ""),
            location=Point(d["location"]) if d.get("location") else Point(),
            distance=d.get("distance", 0.0),
            hint=d.get("hint", ""),
        )

    def __repr__(self) -> str:
        return (
            f"Waypoint(name={self.name!r}, location={self.location!r}, "
            f"distance={self.distance!r})"
        )
