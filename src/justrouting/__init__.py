"""JustRouting Python client.

Official Python client for the JustRouting API — routing, distance
matrices, and vehicle routing optimization across Southeast Asia.

    client = justrouting.Client("YOUR_API_KEY")

    route = client.routes.get(justrouting.RouteRequest(
        origin=[103.8198, 1.3521],
        destination=[103.9915, 1.3644],
    ))
    print(f"Distance: {route.distance / 1000:.1f} km")

Coordinates are always [longitude, latitude], the order used by GeoJSON,
OSRM and VROOM. Failed calls raise a subclass of [justrouting.Error] —
see [justrouting.NoRouteError] and friends.

The package has no dependencies outside the standard library.
"""

from .client import Client
from .consts import DEFAULT_BASE_URL, DEFAULT_PROFILE, VERSION
from .error import (
    CrossCountryError,
    DecodeError,
    Error,
    InvalidCoordinatesError,
    InvalidRequestError,
    JustRoutingError,
    NoRouteError,
    PlanLimitExceededError,
    QuotaExceededError,
    RateLimitedError,
    TransportError,
    UnauthorizedError,
    UpstreamUnavailableError,
)
from .geo import Geometry, LineString, Point, Waypoint
from .health import Health, HealthService
from .matrix import MatrixRequest, MatrixResponse, MatrixService
from .optimization import (
    Job,
    OptimizationOptions,
    OptimizationRequest,
    OptimizationService,
    RouteStep,
    Shipment,
    ShipmentStep,
    Solution,
    Summary,
    TimeWindow,
    Unassigned,
    Vehicle,
    VehicleRoute,
)
from .routes import (
    Annotation,
    Intersection,
    Lane,
    Leg,
    Maneuver,
    Route,
    RouteRequest,
    RouteResponse,
    RoutesService,
    Step,
)

__version__ = VERSION

__all__ = [
    # Client
    "Client",
    "VERSION",
    "DEFAULT_BASE_URL",
    "DEFAULT_PROFILE",
    # Errors
    "JustRoutingError",
    "Error",
    "UnauthorizedError",
    "RateLimitedError",
    "QuotaExceededError",
    "PlanLimitExceededError",
    "CrossCountryError",
    "InvalidCoordinatesError",
    "NoRouteError",
    "UpstreamUnavailableError",
    "InvalidRequestError",
    "TransportError",
    "DecodeError",
    # Geo
    "Point",
    "Geometry",
    "LineString",
    "Waypoint",
    # Services
    "RoutesService",
    "MatrixService",
    "OptimizationService",
    "HealthService",
    # Routes
    "RouteRequest",
    "RouteResponse",
    "Route",
    "Leg",
    "Step",
    "Maneuver",
    "Intersection",
    "Lane",
    "Annotation",
    # Matrix
    "MatrixRequest",
    "MatrixResponse",
    # Optimization
    "OptimizationRequest",
    "OptimizationOptions",
    "TimeWindow",
    "Vehicle",
    "Job",
    "ShipmentStep",
    "Shipment",
    "Solution",
    "Summary",
    "VehicleRoute",
    "RouteStep",
    "Unassigned",
    # Health
    "Health",
]
