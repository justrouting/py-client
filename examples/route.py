"""Compute a route between two points and print its distance.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/route.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    # Marina Bay to Changi Airport. Every coordinate in a request must lie
    # within one country, so both points are in Singapore.
    try:
        route = client.routes.get(
            justrouting.RouteRequest(
                origin=[103.8198, 1.3521],
                destination=[103.9915, 1.3644],
                overview="full",
            ),
            timeout=30,
        )
    except justrouting.CrossCountryError:
        raise SystemExit("origin and destination must be in the same country")

    print(f"Distance: {route.distance / 1000:.1f} km")
    print(f"Duration: {route.duration / 60:.0f} min")
    print(f"Legs:     {len(route.legs)}")

    try:
        polyline = route.geometry.polyline()
    except ValueError:
        pass
    else:
        print(f"Geometry(Polyline): {polyline}")


if __name__ == "__main__":
    main()
