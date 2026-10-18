"""Small in-memory rate limits for the open demo link. Each Cloud Run instance keeps its own counters, so the
real ceiling is (limit x max instances); keep max instances low."""
import threading
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, seconds: float):
        self.limit, self.seconds = limit, seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.seconds:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # drop idle clients so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


def client_ip(request) -> str:
    """Cloud Run puts the caller's address first in X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")
