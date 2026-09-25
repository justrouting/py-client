"""Find the fastest order to visit a set of points.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/trip.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    # Three points around Singapore, all in one country. The engine returns
    # the fastest order to visit them, ending where the trip began.
    resp = client.trip.get_all(
        justrouting.TripRequest(
            coordinates=[
                [103.8198, 1.3521],  # Marina Bay
                [103.8514, 1.2897],  # Sentosa
                [103.9915, 1.3644],  # Changi
            ]
        ),
        timeout=30,
    )

    trip = resp.trips[0]
    print(f"Distance: {trip.distance / 1000:.1f} km")
    print(f"Duration: {trip.duration / 60:.0f} min")
    print(f"Legs:     {len(trip.legs)}")

    # Waypoints are returned in the order the trip visits them.
    print("Order:    " + " -> ".join(wp.name for wp in resp.waypoints))


if __name__ == "__main__":
    main()
