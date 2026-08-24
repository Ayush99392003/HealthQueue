"""
Unit tests for the sliding-window rate limiter module.
"""

import time
import pytest
from src.core.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_allows_under_limit():
    """Verify requests within quota are allowed."""
    key = "test_user_under_limit"
    for i in range(5):
        allowed, remaining, _ = SlidingWindowRateLimiter.is_allowed(
            key=key,
            max_requests=10,
            window_seconds=60,
        )
        assert allowed is True
        assert remaining == 10 - (i + 1)


def test_rate_limiter_blocks_over_limit():
    """Verify requests exceeding quota are blocked."""
    key = "test_user_over_limit"
    # Exhaust 3 requests
    for _ in range(3):
        allowed, _, _ = SlidingWindowRateLimiter.is_allowed(
            key=key,
            max_requests=3,
            window_seconds=10,
        )
        assert allowed is True

    # 4th request must be blocked
    allowed, remaining, reset_secs = SlidingWindowRateLimiter.is_allowed(
        key=key,
        max_requests=3,
        window_seconds=10,
    )
    assert allowed is False
    assert remaining == 0
    assert reset_secs > 0


def test_rate_limiter_window_slide():
    """Verify that requests expire after the window passes."""
    key = "test_user_window_slide"
    # Use a small 1-second window
    allowed, _, _ = SlidingWindowRateLimiter.is_allowed(key=key, max_requests=1, window_seconds=1)
    assert allowed is True

    # Immediate second request blocked
    allowed, _, _ = SlidingWindowRateLimiter.is_allowed(key=key, max_requests=1, window_seconds=1)
    assert allowed is False

    # Sleep past window
    time.sleep(1.1)

    # Next request should now be allowed
    allowed, _, _ = SlidingWindowRateLimiter.is_allowed(key=key, max_requests=1, window_seconds=1)
    assert allowed is True
