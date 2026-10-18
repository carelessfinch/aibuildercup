"""Judge-link guards. This is deliberately simple and in-process for M1."""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from .settings import WebSettings


class GuardDenied(Exception):
    def __init__(self, status_code: int, detail: str, retry_after_s: int | None = None):
        self.status_code = status_code
        self.detail = detail
        self.retry_after_s = retry_after_s


class RunGuards:
    """In-memory run admission checks (M1 stub; Project A can externalise this in M2)."""

    def __init__(self, settings: WebSettings, clock: Callable[[], datetime] | None = None):
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._per_ip: dict[str, deque[datetime]] = defaultdict(deque)
        self._daily_count = 0
        self._daily_date: date | None = None

    def reserve(self, client_ip: str, active_runs: int) -> None:
        now = self.clock()
        digest = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:24]
        with self._lock:
            if self.settings.spend_killswitch:
                raise GuardDenied(503, "New runs are paused by the spending kill-switch.")

            if self._daily_date != now.date():
                self._daily_date = now.date()
                self._daily_count = 0
            if self._daily_count >= self.settings.daily_run_cap:
                raise GuardDenied(
                    429, "Today's public judge-run allowance is used.", retry_after_s=3600
                )

            cutoff = now - timedelta(hours=1)
            attempts = self._per_ip[digest]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.settings.rate_limit_per_ip_per_hour:
                retry_after = max(1, int((attempts[0] + timedelta(hours=1) - now).total_seconds()))
                raise GuardDenied(
                    429,
                    "Too many runs from this address. Try again later.",
                    retry_after_s=retry_after,
                )

            if active_runs >= self.settings.max_concurrent_runs:
                raise GuardDenied(
                    409,
                    "The simulator is already running the maximum number of jobs.",
                )

            attempts.append(now)
            self._daily_count += 1

    @property
    def daily_run_count(self) -> int:
        with self._lock:
            return self._daily_count
