"""Tests for rules/duration_format.py — friendly_duration() pure function.

Locked format spec (HEADER_BUBBLES_V1 / Engineering brief 2026-04-28):

    0              → "0 min"
    1–59           → "X min"
    60             → "1 hr"
    61–119         → "1 hr Y min"
    120            → "2 hr"
    120+ even hr   → "X hr"
    120+ with min  → "X hr Y min"
    negative       → "-" + friendly_duration(abs(value))

14 named tests covering every boundary + all 9 canonical match durations.
"""
from __future__ import annotations

import pytest

from playfuel_api.rules.duration_format import friendly_duration


# ── Sub-60 cases ──────────────────────────────────────────────────────────────


def test_zero_minutes() -> None:
    """0 minutes → '0 min'."""
    assert friendly_duration(0) == "0 min"


def test_thirty_minutes() -> None:
    """30 minutes → '30 min' (sub-60, most common gap/offset)."""
    assert friendly_duration(30) == "30 min"


def test_forty_five_minutes() -> None:
    """45 minutes → '45 min' (doubles pro_set_8 short canonical)."""
    assert friendly_duration(45) == "45 min"


def test_fifty_nine_minutes() -> None:
    """59 minutes → '59 min' (boundary just below 1 hr)."""
    assert friendly_duration(59) == "59 min"


# ── Exact-hour cases ──────────────────────────────────────────────────────────


def test_sixty_minutes_is_one_hr() -> None:
    """60 minutes → '1 hr' (exact boundary)."""
    assert friendly_duration(60) == "1 hr"


def test_one_twenty_minutes_is_two_hr() -> None:
    """120 minutes → '2 hr' (singles normal canonical)."""
    assert friendly_duration(120) == "2 hr"


def test_one_eighty_minutes_is_three_hr() -> None:
    """180 minutes → '3 hr' (singles long canonical)."""
    assert friendly_duration(180) == "3 hr"


# ── Hr + min cases — all 9 canonical match durations covered ─────────────────


def test_seventy_five_minutes() -> None:
    """75 minutes → '1 hr 15 min' (singles short canonical)."""
    assert friendly_duration(75) == "1 hr 15 min"


def test_ninety_minutes() -> None:
    """90 minutes → '1 hr 30 min' (doubles best_of_3 normal canonical)."""
    assert friendly_duration(90) == "1 hr 30 min"


def test_one_thirty_five_minutes() -> None:
    """135 minutes → '2 hr 15 min' (doubles best_of_3 long canonical)."""
    assert friendly_duration(135) == "2 hr 15 min"


def test_seventy_minutes() -> None:
    """70 minutes → '1 hr 10 min' (doubles pro_set_8 normal canonical)."""
    assert friendly_duration(70) == "1 hr 10 min"


def test_one_hundred_minutes() -> None:
    """100 minutes → '1 hr 40 min' (doubles pro_set_8 long canonical)."""
    assert friendly_duration(100) == "1 hr 40 min"


def test_two_twenty_five_minutes() -> None:
    """225 minutes → '3 hr 45 min' (the screenshot value that triggered this feature)."""
    assert friendly_duration(225) == "3 hr 45 min"


# ── Negative (overrun) cases ──────────────────────────────────────────────────


def test_negative_forty_five_minutes() -> None:
    """−45 minutes → '-45 min' (sub-60 overrun)."""
    assert friendly_duration(-45) == "-45 min"


def test_negative_ninety_minutes() -> None:
    """−90 minutes → '-1 hr 30 min' (≥60 overrun)."""
    assert friendly_duration(-90) == "-1 hr 30 min"
