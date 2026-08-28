"""Shared test helpers: a local HTTP server playing the role of
httptest.NewServer from the Go suite, and a client factory aimed at it."""

import http.server
import threading
import urllib.parse
from contextlib import contextmanager

import justrouting

TEST_API_KEY = "0123456789abcdef0123456789abcdef"

# The same minimal success payloads the Go tests serve.
OK_ROUTE = '{"code":"Ok","routes":[{"distance":100,"duration":10}],"waypoints":[]}'
OK_HEALTH = '{"status":"ok"}'


def make_handler(handler_func):
    """Wrap a callable ``handler_func(request)`` in a BaseHTTPRequestHandler
    class. ``request`` carries .method, .path, .headers, .query (a dict of
    lists) and .read_body()."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            record = RequestRecord(self)
            try:
                status, body, headers = handler_func(record)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                # The handler broke the connection deliberately: hang up
                # without a response, like the hijacked connection in the
                # Go transport test.
                self.close_connection = True
                return
            except Exception:
                # Return the traceback so a failing test handler is visible.
                import traceback

                traceback.print_exc()
                status, body, headers = 500, b"handler error", {}
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            if "Content-Type" not in {k.lower() for k in headers}:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if isinstance(body, str):
                body = body.encode()
            self.wfile.write(body)

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def log_message(self, format, *args):
            pass

    return Handler


class RequestRecord:
    """The request as seen by a handler: method, path, headers, query."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.method = handler.command
        self.path = handler.path
        self.headers = handler.headers
        self.query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
        self._rfile = handler.rfile

    def url_path(self) -> str:
        return urllib.parse.urlsplit(self.path).path

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self._rfile.read(length)

    def abort(self):
        """Break the connection without sending a response, like a hijacked
        socket closed mid-request."""
        raise ConnectionResetError("connection broken by handler")


@contextmanager
def serve(handler_func):
    """Serve handler_func on an ephemeral local port for the duration of the
    context; yields the base URL.

    Not named test_* so pytest does not collect it as a test."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(handler_func))
    # Daemon threads so a lingering handler (e.g. one sleeping past a client
    # timeout) does not block server_close.
    srv.daemon_threads = True
    # A short poll interval so shutdown() returns promptly; serve_forever
    # defaults the parameter, so it must be passed explicitly.
    thread = threading.Thread(
        target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join()


def json_handler(status, body):
    """A handler that always replies with a fixed status and JSON body."""
    payload = body if isinstance(body, bytes) else body.encode()

    def handle(req):
        return status, payload, {}

    return handle


@contextmanager
def new_test_client(handler, **opts):
    """Start a server running handler and return a client aimed at it.
    Backoff is zeroed so retry tests run instantly."""
    opts.setdefault("backoff", lambda attempt: 0)
    with serve(handler) as base_url:
        yield justrouting.Client(TEST_API_KEY, base_url=base_url, **opts)


def simple_route():
    return justrouting.RouteRequest(
        origin=[103.8198, 1.3521],
        destination=[103.9915, 1.3644],
    )


def simple_optimization():
    return justrouting.OptimizationRequest(
        vehicles=[
            justrouting.Vehicle(
                id=1, start=[103.8198, 1.3521], end=[103.8198, 1.3521]
            )
        ],
        jobs=[justrouting.Job(id=1, location=[103.8514, 1.2897])],
    )


def three_points():
    return [
        justrouting.Point([103.8198, 1.3521]),
        justrouting.Point([103.83, 1.3048]),
        justrouting.Point([103.9915, 1.3644]),
    ]
