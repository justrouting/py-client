# JustRouting Python Client

Official Python client for the [JustRouting](https://justrouting.tech) API — routing, distance matrices, and vehicle routing optimization across Southeast Asia.

No dependencies outside the standard library. Requires Python 3.9+.

## Install

```shell
# (Not yet available on PyPI)
pip install justrouting
```

> Or install from a clone of this repository:

```shell
pip install -e .
```

```python
import justrouting
```

## Quickstart

```python
import justrouting

client = justrouting.Client("YOUR_API_KEY")

route = client.routes.get(
    justrouting.RouteRequest(
        origin=[103.8198, 1.3521],
        destination=[101.6869, 3.1390],
    ),
    timeout=30,
)

print(f"Distance: {route.distance / 1000:.1f} km")
```

> The coordinates above are Singapore and Kuala Lumpur, which span two countries. See [Coordinates must share a country](#coordinates-must-share-a-country) — the runnable examples use same-country pairs.

## Services

A `Client` exposes four services.

### Routes

`Routes.get` returns the best route. `Routes.get_all` additionally returns alternatives and the snapped input waypoints.

```python
route = client.routes.get(justrouting.RouteRequest(
    origin=[103.8198, 1.3521],
    destination=[103.9915, 1.3644],
    waypoints=[[103.8514, 1.2897]],   # stops in order
    overview="full",                  # full geometry
    steps=True,                       # turn-by-turn
))

print(route.distance)  # metres
print(route.duration)  # seconds
```

`route.geometry` holds whichever encoding you asked for:

```python
polyline = route.geometry.polyline()  # default, and "polyline6"
line = route.geometry.geojson()       # when geometries="geojson"
```

### Matrix

Travel time and distance between many points at once.

```python
m = client.matrix.get(justrouting.MatrixRequest(
    coordinates=[depot, stop_a, stop_b],
    sources=[0],            # only the depot row; cheaper than N×N
    destinations=[1, 2],
))

seconds = m.duration(0, 1)
if seconds is not None:
    print(f"depot -> stopA: {seconds / 60:.0f} min")
```

The accessors return `None` for unreachable pairs. The API reports those as `null`, which is deliberately kept distinct from a genuine zero.

### Optimization

Assign tasks to a fleet and order each vehicle's stops.

```python
solution = client.optimization.solve(justrouting.OptimizationRequest(
    vehicles=[justrouting.Vehicle(
        id=1, start=depot, end=depot, capacity=[4],
    )],
    jobs=[
        justrouting.Job(id=1, location=stop_a, delivery=[1], service=300),
        justrouting.Job(id=2, location=stop_b, delivery=[2], service=300),
    ],
))

for route in solution.routes:
    print(f"vehicle {route.vehicle}: {len(route.steps)} stops")
print(len(solution.unassigned), "task(s) could not be served")
```

Use `Shipments` instead of `Jobs` for pickup-and-delivery pairs that must be served in order by the same vehicle.

### Health

The only call that works without an API key, which makes it a useful connectivity check.

```python
health = client.health.get()
print(health.ok(), health.upstreams)
```

## Error handling

Every failure raises a subclass of `justrouting.Error`. Classify it with `except` clauses rather than matching on message text:

```python
try:
    route = client.routes.get(req)
except justrouting.QuotaExceededError:
    # daily allowance used up — retrying will not help
except justrouting.RateLimitedError:
    # throttled; the client already retried
except justrouting.CrossCountryError:
    # coordinates span more than one country
except justrouting.NoRouteError:
    # no road connects these points
```

| Exception | Meaning |
| --- | --- |
| `UnauthorizedError` | API key missing, invalid, or revoked |
| `RateLimitedError` | Throttled (per-second limit or daily quota) |
| `QuotaExceededError` | Daily quota exhausted; retrying will not help (subclasses `RateLimitedError`) |
| `PlanLimitExceededError` | Too many matrix coordinates, jobs, or vehicles |
| `CrossCountryError` | Coordinates span more than one country |
| `InvalidCoordinatesError` | Coordinate malformed or out of range |
| `NoRouteError` | No route exists between the points |
| `UpstreamUnavailableError` | Routing engine unreachable; usually transient |
| `InvalidRequestError` | Rejected locally before any request was sent |

Catch `justrouting.Error` itself when you need the status code, engine code, or raw body:

```python
except justrouting.Error as e:
    print(f"HTTP {e.status_code}: {e.message}")
    print(e.body)  # raw response body, truncated
```

Failures that never produced an API response raise `TransportError` (network-level, retried like a 5xx) or `DecodeError` (unparseable success response) instead; neither is a subclass of `Error`.

## Configuration

| Argument | Default | Purpose |
| --- | --- | --- |
| `api_key` | — | Sent as `Authorization: Bearer` on every authenticated request |
| `base_url` | `https://api.justrouting.tech` | Target a local or staging server |
| `user_agent` | `justrouting-py/<version>` | Identify your application |
| `max_retries` | `2` | Retry budget on top of the initial attempt |
| `backoff` | 500ms → 8s, jittered | Callable replacing the retry delay schedule |
| `timeout` | `30` | Seconds per HTTP attempt |

Invalid options raise `ValueError` immediately. (The Go client defers them to the first request because its constructor cannot fail; Python constructors can.)

### Timeouts and retries

Rate limits (429), server errors (5xx), and transport failures are retried with exponential backoff and jitter; a `Retry-After` header takes precedence when present. Other 4xx responses are returned immediately — they would fail identically on a retry and would still consume quota.

`Client(timeout=...)` covers a single HTTP attempt, like `http.Client.Timeout` in Go. Pass the per-call `timeout` argument to bound the whole retry sequence:

```python
route = client.routes.get(req, timeout=30)  # 30s total, retries included
```

Proxy configuration follows the standard `HTTP_PROXY` / `HTTPS_PROXY` environment variables.

## Things to know

### Coordinates are `[longitude, latitude]`

This is the GeoJSON order, and the reverse of the "lat, lng" used by most map UIs. Swapped coordinates are usually caught locally — a longitude in the latitude slot fails the `[-90, 90]` check before a request is sent — but a swap that stays in range will silently route somewhere unexpected.

`Point` is a `list` subclass, so both of these work:

```python
origin=[103.8198, 1.3521]
origin=justrouting.Point([103.8198, 1.3521])
```

### Coordinates must share a country

Every coordinate in a single request must fall within one country; the API routes each request to a per-country engine. A Singapore → Kuala Lumpur request fails with `CrossCountryError`.

Supported countries: Brunei, Cambodia, Indonesia, Laos, Malaysia, Myanmar, the Philippines, Singapore, Thailand, and Vietnam.

### Plan limits

| | Free | Hobby |
| --- | --- | --- |
| Requests per day | 100 | 10,000 |
| Requests per second | 5 | 10 |
| Matrix coordinates | 100 | 500 |
| Jobs per optimization | 100 | 1,000 |
| Vehicles per optimization | 10 | 50 |

Exceeding a size limit raises `PlanLimitExceededError`; exhausting the daily allowance raises `QuotaExceededError`.

## Examples

Runnable scripts live in [`examples/`](./examples):

```shell
export JUSTROUTING_API_KEY=<your key>
python examples/route.py
python examples/matrix.py
python examples/optimization.py
```

## Development

```shell
pip install -e '.[dev]'
pytest
```

The default suite runs entirely against local `http.server` instances — no network access and no API key.

Integration tests hit a live API and are behind a marker, so they never run by accident:

```shell
pytest -m integration                          # health and auth only
JUSTROUTING_API_KEY=<key> pytest -m integration
JUSTROUTING_BASE_URL=http://localhost:8080 pytest -m integration
```

## Differences from the Go client

* Exceptions replace sentinel errors and `errors.Is`; `QuotaExceededError` subclasses `RateLimitedError`.
* Constructor options are keyword arguments; invalid ones raise `ValueError` immediately instead of being deferred to the first request.
* There is no `context.Context`; the per-call `timeout` argument plays the role of a context deadline.
* Matrix accessors return `float | None` instead of `(float, ok)`.
* There is no custom-HTTP-client option; use `base_url`, `timeout`, and the standard proxy environment variables instead.

## License

[MIT](./LICENSE)
