"""Snap a noisy GPS trace onto the road network.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/map_matching.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    # A GPS trace along the East Coast Parkway, from Marina Bay towards
    # Changi — points a few kilometres apart, with a little GPS noise.
    match = client.map_matching.get(
        justrouting.MapMatchingRequest(
            coordinates=[
                [103.823679, 1.355111],
                [103.831810, 1.355074],
                [103.839222, 1.346059],
                [103.856595, 1.343471],
                [103.864702, 1.329605],
                [103.887874, 1.322419],
                [103.928786, 1.335564],
                [103.962769, 1.350345],
                [103.983033, 1.344782],
                [103.990312, 1.361474],
            ]
        ),
        timeout=30,
    )

    print(f"Confidence: {match.confidence * 100:.0f}%")
    print(f"Distance:   {match.distance / 1000:.1f} km")
    print(f"Duration:   {match.duration / 60:.0f} min")
    print(f"Legs:       {len(match.legs)}")


if __name__ == "__main__":
    main()
