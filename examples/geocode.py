"""Search for an address and print the matches.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/geocode.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    results = client.geocode.search(
        justrouting.GeocodeRequest(
            text="Marina Bay Sands, Singapore",
            limit=5,
            filters=["countrycode:sg"],
        ),
        timeout=30,
    )

    for i, r in enumerate(results.results):
        loc = r.location()
        print(f"#{i + 1} {r.formatted}")
        print(f"  Location:   {loc.lon():.6f}, {loc.lat():.6f}")
        print(f"  Type:       {r.result_type}")
        print(f"  Place ID:   {r.place_id}")


if __name__ == "__main__":
    main()
