"""Match scenario generation — RULES_CONSTANTS_V1.md §A / §B / §D / §G.

generate_match_scenarios() is the central rules engine entry point for v1.0.0.
It is pure: no I/O, no LLM calls, no side effects.

Gap arithmetic (§B.1):
    gap_minutes = next_match.scheduled_start − (match.scheduled_start + duration_min)

gap_status classification (§G.1):
    overrun      gap_minutes < 0
    tight        0 <= gap_minutes < TIGHT_GAP_THRESHOLD_MIN (30)  [DRAFT — OQ-E]
    ok           gap_minutes >= TIGHT_GAP_THRESHOLD_MIN
    no_next_match  next_match is None

Overrun clamps (§G.3 / OQ-14):
    food    → bag_only
    pickup  → bring_portable
    rewarm_up → None
    Plan still returns HTTP 200 with OVERRUN_MESSAGE warning.

Rewarm-up (§D.2):
    Non-null only when gap_minutes >= REWARM_UP_MIN_GAP (60).
    start_offset_min = REWARM_UP_OFFSET_MIN (−30); duration_min = REWARM_UP_DURATION_MIN (20).

No-next-match (§G.5):
    food_strategy → None; pickup_strategy.bucket → None; no rewarm_up.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from playfuel_api.models.api import (
    FoodStrategy,
    OverrunWarning,
    PickupStrategy,
    RewarmUp,
    ScenarioPlan,
)
from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind
from playfuel_api.rules.buckets import food_bucket_for, pickup_bucket_for
from playfuel_api.rules.constants import (
    REWARM_UP_DURATION_MIN,
    REWARM_UP_MIN_GAP,
    REWARM_UP_OFFSET_MIN,
    SCENARIO_DURATIONS_MIN,
    TIGHT_GAP_THRESHOLD_MIN,
)
from playfuel_api.rules.hard_coded_strings import (
    FOOD_BUCKET_TEXT,
    OVERRUN_MESSAGE,
    PICKUP_BUCKET_TEXT,
)

# §G.5 verbatim — USER_STORIES.md US-04.
_NO_NEXT_MATCH_PICKUP_TEXT = (
    "No next match provided. Parent can wait until match ends."
)


def _fmt_time(dt) -> str:
    """Format a datetime as 'H:MM AM/PM' with no leading zero on the hour."""
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{h}:{dt.minute:02d} {ampm}"


def _make_scenario(
    kind: ScenarioKind,
    match: MatchRow,
    next_match: Optional[MatchRow],
    duration_min: int,
) -> ScenarioPlan:
    """Build a single ScenarioPlan for one duration scenario (internal helper)."""
    estimated_end_dt = match.scheduled_start + timedelta(minutes=duration_min)
    estimated_end_str = _fmt_time(estimated_end_dt)

    # ── §G.5: no_next_match ──────────────────────────────────────────────────
    if next_match is None:
        return ScenarioPlan(
            scenario=kind,
            duration_min=duration_min,
            estimated_end=estimated_end_str,
            gap_minutes=None,
            gap_status=GapStatus.no_next_match,
            food_strategy=None,
            pickup_strategy=PickupStrategy(
                bucket=None,
                text=_NO_NEXT_MATCH_PICKUP_TEXT,
            ),
            rewarm_up=None,
            overrun_warning=None,
            warnings=[],
        )

    # ── §B.1: gap arithmetic ─────────────────────────────────────────────────
    gap_td = next_match.scheduled_start - estimated_end_dt
    gap_minutes = int(gap_td.total_seconds() / 60)

    # ── §G.3: overrun clamps ─────────────────────────────────────────────────
    if gap_minutes < 0:
        overrun_w = OverrunWarning(
            code="MATCH_OVERRUN",
            severity="high",
            minutes_over=abs(gap_minutes),
            message=OVERRUN_MESSAGE,
        )
        return ScenarioPlan(
            scenario=kind,
            duration_min=duration_min,
            estimated_end=estimated_end_str,
            gap_minutes=gap_minutes,
            gap_status=GapStatus.overrun,
            food_strategy=FoodStrategy(
                bucket=FoodBucket.bag_only,
                text=FOOD_BUCKET_TEXT["bag_only"],
            ),
            pickup_strategy=PickupStrategy(
                bucket=PickupBucket.bring_portable,
                text=PICKUP_BUCKET_TEXT["bring_portable"],
            ),
            rewarm_up=None,
            overrun_warning=overrun_w,
            warnings=["MATCH_OVERRUN"],
        )

    # ── §G.1: gap_status for non-overrun gaps ────────────────────────────────
    # TIGHT_GAP_THRESHOLD_MIN = 30 [DRAFT — OQ-E]
    gap_status = (
        GapStatus.tight if gap_minutes < TIGHT_GAP_THRESHOLD_MIN else GapStatus.ok
    )

    # ── §B.2 / §B.3: food + pickup buckets ──────────────────────────────────
    fb: FoodBucket = food_bucket_for(gap_minutes)
    pb: PickupBucket = pickup_bucket_for(gap_minutes)

    # ── §D.2: rewarm-up (non-null only when gap >= 60 min) ──────────────────
    rewarm_up: Optional[RewarmUp] = None
    if gap_minutes >= REWARM_UP_MIN_GAP:
        rewarm_up = RewarmUp(
            start_offset_min=REWARM_UP_OFFSET_MIN,
            duration_min=REWARM_UP_DURATION_MIN,
        )

    return ScenarioPlan(
        scenario=kind,
        duration_min=duration_min,
        estimated_end=estimated_end_str,
        gap_minutes=gap_minutes,
        gap_status=gap_status,
        food_strategy=FoodStrategy(bucket=fb, text=FOOD_BUCKET_TEXT[fb.value]),
        pickup_strategy=PickupStrategy(bucket=pb, text=PICKUP_BUCKET_TEXT[pb.value]),
        rewarm_up=rewarm_up,
        overrun_warning=None,
        warnings=[],
    )


def generate_match_scenarios(
    match: MatchRow,
    next_match: Optional[MatchRow],
    *,
    duration_overrides: Optional[dict[str, int]] = None,
) -> list[ScenarioPlan]:
    """Generate short / normal / long ScenarioPlan objects for a match pair.

    §A.2 — duration_overrides is reserved for v1.1; in v1.0.0 it is unused and
    SCENARIO_DURATIONS_MIN defaults are always used regardless of the kwarg value.

    Args:
        match:             Match whose scheduled_start anchors all durations.
        next_match:        Following match, or None (triggers §G.5 no_next_match).
        duration_overrides: Reserved; unused in v1.0.0.

    Returns:
        list[ScenarioPlan] — [short, normal, long] in ScenarioKind definition order.
    """
    # duration_overrides is reserved (§A.2 v1.1 hook); ignored in this version.
    _ = duration_overrides

    return [
        _make_scenario(kind, match, next_match, SCENARIO_DURATIONS_MIN[kind.value])
        for kind in ScenarioKind
    ]
