"""
High-performance in-memory sliding-window rate limiter for FastAPI.

Usage:
    from src.core.rate_limiter import rate_limit

    @router.post("/book", dependencies=[Depends(rate_limit(max_requests=50, window_seconds=60))])
    async def book_token(...):
        ...
"""

import time
from collections import defaultdict
from collections.abc import Callable
from typing import ClassVar

from fastapi import HTTPException, Request, status

from src.core.logger import get_logger

logger = get_logger(__name__)


class SlidingWindowRateLimiter:
    """Thread-safe, high-performance in-memory sliding window rate limiter."""

    _instances: ClassVar[dict[str, list[float]]] = defaultdict(list)

    @classmethod
    def is_allowed(cls, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, float]:
        """
        Check if request is allowed under rate limits.

        Returns:
            (allowed: bool, remaining_requests: int, reset_seconds: float)
        """
        now = time.time()
        cutoff = now - window_seconds
        timestamps = cls._instances[key]

        # Clean old timestamps outside sliding window
        valid_timestamps = [t for t in timestamps if t > cutoff]
        cls._instances[key] = valid_timestamps

        if len(valid_timestamps) >= max_requests:
            oldest = valid_timestamps[0]
            reset_seconds = max(0.0, oldest + window_seconds - now)
            return False, 0, reset_seconds

        # Record current request
        valid_timestamps.append(now)
        remaining = max_requests - len(valid_timestamps)
        return True, remaining, float(window_seconds)


def rate_limit(max_requests: int = 50, window_seconds: int = 60) -> Callable:
    """
    FastAPI dependency factory for rate limiting endpoints.

    Identifies client by user ID (if authenticated) or client IP address.
    """
    async def _rate_limit_dependency(request: Request) -> None:
        # Determine client key (Auth user ID or IP)
        user_id = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate:{user_id or client_ip}:{request.url.path}"

        allowed, remaining, reset_secs = SlidingWindowRateLimiter.is_allowed(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded for %s on %s (limit: %d/%ds)",
                key, request.url.path, max_requests, window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s. Try again in {int(reset_secs)} seconds.",
                headers={"Retry-After": str(int(reset_secs))},
            )

    return _rate_limit_dependency
