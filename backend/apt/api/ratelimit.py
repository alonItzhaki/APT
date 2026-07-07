import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PATHS = {"/healthz"}
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 120):
        super().__init__(app)
        self._max_requests = max_requests
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[client_ip]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        hits.append(now)
        return await call_next(request)
