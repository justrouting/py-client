"""Find the road segment closest to a coordinate.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/nearest.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    wp = client.nearest.get(
        justrouting.NearestRequest(coordinate=[103.8198, 1.3521]),
        timeout=30,
    )

    print(f"Street:   {wp.name}")
    print(f"Location: {wp.location.lon():.6f}, {wp.location.lat():.6f}")
    print(f"Distance: {wp.distance:.0f} m")
    if wp.nodes:
        print(f"Nodes:    {wp.nodes}")


if __name__ == "__main__":
    main()
