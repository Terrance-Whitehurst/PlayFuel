"""Tests for SP-2 — per-user rate limiting on POST /v1/tournaments/{tid}/plans/generate.

See: places PR validation report (SP-2 finding) and chore/cleanup-phases-5-7 branch.

Rate-limit implementation: in-memory sliding-window in routes/plans.py.
  - 10 calls per rolling hour  (_RATE_LIMIT_HOURLY)
  - 30 calls per rolling 24 h  (_RATE_LIMIT_DAILY)
  - Keyed on JWT sub (str(user_id))
  - 429 + Retry-After header when either window is exhausted

Approach:
  - Unit tests call _check_rate_limit() directly with pre-filled module deques.
  - HTTP test pre-fills deques then POSTs to the route; SP-2 fires before DB,
    so no DB fixture is required for the 429 case.
  - autouse fixture clears module-level deques before/after every test to
    prevent cross-test state pollution.

Coverage (8 tests):
    1. test_first_call_is_allowed
    2. test_hourly_cap_blocks_on_11th_call
    3. test_daily_cap_blocks_independently
    4. test_per_user_isolation
    5. test_old_hourly_timestamps_evicted_slots_reopen
    6. test_retry_after_is_positive_on_429
    7. test_http_429_with_retry_after_header
    8. test_http_429_response_body_has_detail
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from playfuel_api.routes.plans import (
    _RATE_LIMIT_DAILY,
    _RATE_LIMIT_HOURLY,
    _check_rate_limit,
    _daily_calls,
    _hourly_calls,
)

# The demo user UUID injected by the conftest auth override.
_TEST_USER_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
_USER_A = str(_TEST_USER_ID)
_USER_B = "bb000000-0000-0000-0000-000000000002"

_TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_PLAN_PATH = f"/v1/tournaments/{_TID}/plans/generate"


@pytest.fixture(autouse=True)
def _clear_rate_limit_state():
    """Reset module-level rate-limit deques before AND after every test.

    _hourly_calls and _daily_calls are process-wide singletons. Without this
    fixture, a test that records calls would pollute tests that run later in
    the same pytest session.
    """
    _hourly_calls.clear()
    _daily_calls.clear()
    yield
    _hourly_calls.clear()
    _daily_calls.clear()


# ── Unit tests for _check_rate_limit() ────────────────────────────────────────

class TestCheckRateLimitUnit:
    """Direct unit tests for the _check_rate_limit() function.

    These tests import module-level deques and pre-fill them to set up
    specific state without making HTTP calls.
    """

    def test_first_call_is_allowed(self):
        """A single call with empty deques returns (True, 0) and records itself."""
        allowed, retry = _check_rate_limit(_USER_A)

        assert allowed is True
        assert retry == 0
        # Call was recorded in both windows.
        assert len(_hourly_calls[_USER_A]) == 1
        assert len(_daily_calls[_USER_A]) == 1

    def test_hourly_cap_blocks_on_11th_call(self):
        """After _RATE_LIMIT_HOURLY (10) calls in the rolling hour, the next is blocked."""
        now = datetime.now(tz=timezone.utc)
        # Simulate 10 calls that happened seconds ago — still within the 1-hour window.
        _hourly_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)
        _daily_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)

        allowed, retry_after = _check_rate_limit(_USER_A)

        assert allowed is False
        assert retry_after >= 1  # at least 1 second until the oldest slot expires

    def test_daily_cap_blocks_independently(self):
        """Daily cap (30) fires even when the hourly window has cleared.

        Setup: 30 timestamps at 2 h ago.
          - Hourly check: 2-h-old entries are OUTSIDE the 1-h window → evicted → passes.
          - Daily check: 2-h-old entries are INSIDE the 24-h window → remain → 30 >= 30 → blocked.
        """
        now = datetime.now(tz=timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

        # 30 entries in daily queue, all 2 h old (within 24 h window).
        _daily_calls[_USER_A].extend([two_hours_ago] * _RATE_LIMIT_DAILY)
        # 10 entries in hourly queue, all 2 h old (OUTSIDE 1 h window — will be evicted).
        _hourly_calls[_USER_A].extend([two_hours_ago] * _RATE_LIMIT_HOURLY)

        allowed, retry_after = _check_rate_limit(_USER_A)

        assert allowed is False, "Daily cap should block even though hourly window is clear"
        assert retry_after >= 1

    def test_per_user_isolation(self):
        """User A at the hourly limit does not affect User B."""
        now = datetime.now(tz=timezone.utc)
        # Max out USER_A's hourly quota.
        _hourly_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)
        _daily_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)

        allowed_b, retry_b = _check_rate_limit(_USER_B)
        assert allowed_b is True, "User B should be unaffected by User A's quota"
        assert retry_b == 0

        # USER_A is still blocked.
        allowed_a, _ = _check_rate_limit(_USER_A)
        assert allowed_a is False

    def test_old_hourly_timestamps_evicted_slots_reopen(self):
        """Timestamps older than 1 hour are evicted; the user gets fresh slots.

        Pre-fill hourly deque with 10 entries from 2 h ago.  When the function
        runs, those entries are outside the 1-h window and get evicted.
        Daily deque has the same 10 entries (all within 24 h, count < 30),
        so the daily check also passes.  Result: (True, 0).
        """
        now = datetime.now(tz=timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

        _hourly_calls[_USER_A].extend([two_hours_ago] * _RATE_LIMIT_HOURLY)  # 10 stale entries
        _daily_calls[_USER_A].extend([two_hours_ago] * _RATE_LIMIT_HOURLY)   # 10 entries, < 30

        allowed, retry = _check_rate_limit(_USER_A)

        assert allowed is True, "Stale hourly entries should be evicted, freeing the slot"
        assert retry == 0

    def test_retry_after_is_positive_on_429(self):
        """retry_after returned when blocked is always >= 1 second (never 0)."""
        now = datetime.now(tz=timezone.utc)
        _hourly_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)
        _daily_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)

        allowed, retry_after = _check_rate_limit(_USER_A)

        assert allowed is False
        assert retry_after >= 1, "Retry-After must be at least 1 s per spec"


# ── HTTP integration tests ─────────────────────────────────────────────────────

class TestRateLimitHTTP:
    """HTTP-layer tests that hit the generate_plan endpoint via TestClient.

    SP-2 fires as the very first line of generate_plan (before any DB call),
    so we can pre-fill the module deques and assert on the 429 response without
    needing a full DB fixture.
    """

    def test_http_429_with_retry_after_header(self, client_with_auth):
        """11th call within the rolling hour → 429 with a Retry-After header.

        Pre-fills _hourly_calls[USER_A] with 10 recent timestamps so the next
        POST trips the hourly limit.  USER_A == str(TEST_USER_ID) which is the
        UUID injected by conftest.client_with_auth's auth override.
        """
        now = datetime.now(tz=timezone.utc)
        _hourly_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)
        _daily_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)

        resp = client_with_auth.post(_PLAN_PATH)

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert retry_after >= 1

    def test_http_429_response_body_has_detail(self, client_with_auth):
        """429 body includes a human-readable 'detail' string mentioning rate limit."""
        now = datetime.now(tz=timezone.utc)
        _hourly_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)
        _daily_calls[_USER_A].extend([now] * _RATE_LIMIT_HOURLY)

        resp = client_with_auth.post(_PLAN_PATH)

        assert resp.status_code == 429
        body = resp.json()
        assert "detail" in body
        assert "rate limit" in body["detail"].lower()
