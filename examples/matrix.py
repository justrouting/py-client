"""Compute travel times from a depot to several stops.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/matrix.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    depot = justrouting.Point([103.8198, 1.3521])  # Marina Bay
    stops = [
        justrouting.Point([103.8514, 1.2897]),  # Marina Barrage
        justrouting.Point([103.9915, 1.3644]),  # Changi Airport
        justrouting.Point([103.7649, 1.3329]),  # Jurong East
    ]

    # Restricting sources to the depot computes one row instead of the
    # full square matrix, which counts against a much smaller plan limit.
    m = client.matrix.get(
        justrouting.MatrixRequest(
            coordinates=[depot, *stops],
            sources=[0],
            destinations=list(range(1, len(stops) + 1)),
        ),
        timeout=30,
    )

    print("From the depot:")
    for j in range(len(stops)):
        seconds = m.duration(0, j)
        if seconds is None:
            print(f"  stop {j + 1}: unreachable")
            continue
        metres = m.distance(0, j) or 0
        print(f"  stop {j + 1}: {seconds / 60:5.1f} min  {metres / 1000:6.1f} km")


if __name__ == "__main__":
    main()
