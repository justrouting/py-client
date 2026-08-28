"""Port of geo_test.go."""

import math

import pytest

import justrouting
from justrouting.geo import encode_points


def test_point_accessors():
    # The quickstart assigns a plain list literal to Point fields; guard the
    # same tolerance here.
    req = justrouting.RouteRequest(
        origin=[103.8198, 1.3521],
        destination=[103.9915, 1.3644],
        waypoints=[justrouting.Point([103.85, 1.29])],
    )
    assert req.origin.lon() == 103.8198
    assert req.origin.lat() == 1.3521


def test_point_accessors_on_malformed_values():
    for p in [None, [], [1.0]]:
        point = justrouting.Point(p) if p is not None else justrouting.Point()
        assert point.lon() == 0
        assert point.lat() == 0


@pytest.mark.parametrize(
    "point,valid",
    [
        ([103.8198, 1.3521], True),  # singapore
        ([0, 0], True),  # null island
        ([-180, -90], True),  # extremes
        ([180, 90], True),  # opposite extremes
        (None, False),  # nil
        ([], False),  # empty
        ([1], False),  # one value
        ([1, 2, 3], False),  # three values
        ([180.1, 0], False),  # longitude too large
        ([-180.1, 0], False),  # longitude too small
        ([0, 90.1], False),  # latitude too large
        ([0, -90.1], False),  # latitude too small
        ([math.nan, 0], False),  # NaN
        ([math.inf, 0], False),  # infinity
    ],
)
def test_point_validate(point, valid):
    p = justrouting.Point(point) if point is not None else justrouting.Point()
    if valid:
        p.validate()  # must not raise
    else:
        with pytest.raises(justrouting.InvalidCoordinatesError):
            p.validate()


# Coordinates must not lose precision or gain exponent notation on the way
# into a URL path.
@pytest.mark.parametrize(
    "point,want",
    [
        ([103.8198, 1.3521], "103.8198,1.3521"),
        ([-0.1276474, 51.5073219], "-0.1276474,51.5073219"),
        ([0, 0], "0,0"),
        ([103.819836000001, 1.352100000009], "103.819836000001,1.352100000009"),
        ([0.0000001, 0.0000001], "0.0000001,0.0000001"),
        ([1], ""),
        ([], ""),
    ],
)
def test_point_string(point, want):
    assert str(justrouting.Point(point)) == want


def test_encode_points():
    # joins with semicolons
    got = encode_points(
        [justrouting.Point([103.8, 1.35]), justrouting.Point([103.9, 1.36]), justrouting.Point([104.0, 1.37])]
    )
    assert got == "103.8,1.35;103.9,1.36;104,1.37"

    # rejects an empty list
    with pytest.raises(justrouting.InvalidCoordinatesError):
        encode_points([])

    # reports which coordinate is bad
    with pytest.raises(justrouting.InvalidCoordinatesError) as excinfo:
        encode_points([justrouting.Point([103.8, 1.35]), justrouting.Point([0, 91])])
    assert "coordinate 1" in str(excinfo.value)


def test_geometry_polyline():
    g = justrouting.Geometry("ka|ceeEnAqB")

    assert g.polyline() == "ka|ceeEnAqB"

    # Asking for the wrong encoding should explain the mismatch, not crash.
    with pytest.raises(ValueError):
        g.geojson()
    assert g.is_zero() is False


def test_geometry_geojson():
    raw = {"type": "LineString", "coordinates": [[103.8198, 1.3521], [103.9915, 1.3644]]}
    g = justrouting.Geometry(raw)

    ls = g.geojson()
    assert ls.type == "LineString"
    assert len(ls.coordinates) == 2
    assert ls.coordinates[0].lon() == 103.8198

    with pytest.raises(ValueError):
        g.polyline()


def test_geometry_absent():
    g = justrouting.Geometry()
    assert g.is_zero() is True
    assert justrouting.Geometry(None).is_zero() is True

    with pytest.raises(ValueError):
        g.polyline()
    with pytest.raises(ValueError):
        g.geojson()
