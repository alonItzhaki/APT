import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PATHS = {"/healthz"}
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 120, max_tracked_ips: int = 1000):
        super().__init__(app)
        self._max_requests = max_requests
        self._max_tracked_ips = max_tracked_ips
        self._hits: dict[str, deque] = defaultdict(deque)

    def _sweep(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        stale = [ip for ip, entries in self._hits.items() if not entries or entries[-1] < cutoff]
        for ip in stale:
            del self._hits[ip]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if len(self._hits) > self._max_tracked_ips:
            self._sweep(now)
        hits = self._hits[client_ip]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        hits.append(now)
        return await call_next(request)
