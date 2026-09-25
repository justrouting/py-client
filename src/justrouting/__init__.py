"""JustRouting Python client.

Official Python client for the JustRouting API — routing, distance
matrices, geocoding, map matching, trips, nearest-road lookup, and
vehicle routing optimization across Southeast Asia.

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
from .geo import Geometry, LineString, Point, PointLike, Waypoint
from .geocode import (
    BBox,
    Datasource,
    GeocodeQuery,
    GeocodeRequest,
    GeocodeResponse,
    GeocodeResult,
    GeocodeService,
    Rank,
    StructuredQuery,
    Timezone,
)
from .health import Health, HealthService
from .map_matching import (
    MapMatchingRequest,
    MapMatchingResponse,
    MapMatchingService,
    Match,
    Tracepoint,
)
from .matrix import MatrixRequest, MatrixResponse, MatrixService
from .nearest import NearestRequest, NearestResponse, NearestService
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
from .trip import TripRequest, TripResponse, TripService

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
    "PointLike",
    "Geometry",
    "LineString",
    "Waypoint",
    # Services
    "RoutesService",
    "MatrixService",
    "MapMatchingService",
    "TripService",
    "NearestService",
    "GeocodeService",
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
    # Map matching
    "MapMatchingRequest",
    "MapMatchingResponse",
    "Match",
    "Tracepoint",
    # Trip
    "TripRequest",
    "TripResponse",
    # Nearest
    "NearestRequest",
    "NearestResponse",
    # Geocode
    "GeocodeRequest",
    "StructuredQuery",
    "GeocodeResponse",
    "GeocodeQuery",
    "GeocodeResult",
    "Datasource",
    "Rank",
    "Timezone",
    "BBox",
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
