"""Assign deliveries to a small fleet and print the resulting routes.

Usage:

    JUSTROUTING_API_KEY=<key> python examples/optimization.py
"""

import os

import justrouting

DEFAULT_API_KEY = "e7d5c0f6c1da7752488610d21fd80959"


def main() -> None:
    client = justrouting.Client(
        os.environ.get("JUSTROUTING_API_KEY") or DEFAULT_API_KEY
    )

    depot = justrouting.Point([103.8198, 1.3521])

    # Two vans, each able to carry three parcels, working a morning shift.
    shift = (8 * 3600, 12 * 3600)
    vehicles = [
        justrouting.Vehicle(
            id=1, start=depot, end=depot, capacity=[3], time_window=shift
        ),
        justrouting.Vehicle(
            id=2, start=depot, end=depot, capacity=[3], time_window=shift
        ),
    ]

    # Four deliveries, each taking five minutes on site.
    jobs = [
        justrouting.Job(id=1, location=[103.8514, 1.2897], delivery=[1], service=300),
        justrouting.Job(id=2, location=[103.9915, 1.3644], delivery=[1], service=300),
        justrouting.Job(id=3, location=[103.7649, 1.3329], delivery=[2], service=300),
        justrouting.Job(id=4, location=[103.8198, 1.4382], delivery=[1], service=300),
    ]

    try:
        solution = client.optimization.solve(
            justrouting.OptimizationRequest(vehicles=vehicles, jobs=jobs),
            timeout=60,
        )
    except justrouting.PlanLimitExceededError:
        raise SystemExit("the fleet or job count exceeds your plan limit")

    print(
        f"cost {solution.summary.cost}, {solution.summary.routes} route(s), "
        f"{solution.summary.unassigned} unassigned\n"
    )

    for route in solution.routes:
        print(
            f"vehicle {route.vehicle} — {route.duration / 60:.0f} min, "
            f"{route.distance / 1000:.1f} km"
        )
        for step in route.steps:
            if step.type in ("start", "end"):
                print(f"  {step.type:<8} at {step.location}")
            else:
                print(f"  {step.type:<8} job {step.job}, arrive {step.arrival / 60:.0f} min in")
        print()

    for task in solution.unassigned:
        print(f"unassigned: task {task.id} at {task.location}")


if __name__ == "__main__":
    main()
