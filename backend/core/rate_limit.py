"""In-process sliding-window rate limiter (single instance only)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from backend.core.exceptions import AppError


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    detail = "Trop de tentatives — réessayez plus tard"


class SlidingWindowLimiter:
    """ponytail: in-process only; shared store if multi-replica."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, limit: int, window_sec: float) -> None:
        now = time.monotonic()
        cutoff = now - window_sec
        with self._lock:
            bucket = self._hits[key]
            del bucket[: next((i for i, t in enumerate(bucket) if t >= cutoff), len(bucket))]
            if len(bucket) >= limit:
                raise RateLimited()
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Shared buckets for public intake routes.
public_intake_limiter = SlidingWindowLimiter()
