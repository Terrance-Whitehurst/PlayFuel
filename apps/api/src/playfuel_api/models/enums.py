"""
Postgres enum mirrors for PlayFuel.

IMPORTANT: Every string value here must match the corresponding Postgres enum
value in db/supabase/migrations/0001_extensions_and_enums.sql byte-for-byte.
Any change here requires a Postgres migration AND a RULES_CONSTANTS_VERSION bump.
"""
from enum import StrEnum


class ScenarioKind(StrEnum):
    """match_scenarios.scenario_kind — RULES_CONSTANTS_V1.md §A."""
    short = "short"
    normal = "normal"
    long = "long"


class GapStatus(StrEnum):
    """match_scenarios.gap_status — RULES_CONSTANTS_V1.md §G.1."""
    ok = "ok"
    tight = "tight"
    overrun = "overrun"
    no_next_match = "no_next_match"


class ScheduleConfidence(StrEnum):
    """plans.schedule_confidence — derived by FastAPI before INSERT (resolves OQ-G)."""
    high = "high"
    medium = "medium"
    low = "low"


class FoodBucket(StrEnum):
    """match_scenarios.food_bucket — RULES_CONSTANTS_V1.md §B.2."""
    bag_only = "bag_only"
    portable = "portable"
    quick_pickup = "quick_pickup"
    light_meal = "light_meal"


class PickupBucket(StrEnum):
    """match_scenarios.pickup_bucket — RULES_CONSTANTS_V1.md §B.3."""
    bring_portable = "bring_portable"
    pickup_during_match = "pickup_during_match"
    wait_until_end = "wait_until_end"


class WeatherCondition(StrEnum):
    """weather_snapshots.condition — Engineering3 proposal; OQ-H tracks extensions."""
    clear = "clear"
    cloudy = "cloudy"
    rain = "rain"
    storm = "storm"
    snow = "snow"


class MatchType(StrEnum):
    """Doubles-spec extension — stored in matches.format (pre-existing, 0002) and
    plans.match_type (new, 0007). See DOUBLES_SPEC_V1.md §A.1."""
    singles = "singles"
    doubles = "doubles"


class DoublesFormat(StrEnum):
    """Doubles match format — stored in matches.doubles_format (new, 0007).
    Null / absent means singles or format not specified. See DOUBLES_SPEC_V1.md §A.1."""
    best_of_3 = "best_of_3"
    pro_set_8 = "pro_set_8"


class PlayerNoteSource(StrEnum):
    """player_notes.source — PLAYER_SCOUTING_V1.md §B.

    Byte-identical to the Postgres player_note_source enum values.
    """
    secondhand = "secondhand"   # heard from others before the match
    observed = "observed"       # watched during a match
    post_match = "post_match"   # reflection after playing them


class MatchEvalResult(StrEnum):
    """match_evaluations.result — POST_MATCH_EVAL_V1.md §B.

    Byte-identical to the Postgres match_eval_result enum values.
    """
    won = "won"
    lost = "lost"
    withdrew = "withdrew"
    retired = "retired"


class TimelineEventKind(StrEnum):
    """Plan timeline event categories — mirrors iOS TimelineEvent.swift.

    OQ-TRIAGE-1 resolution: extended with gap, foodWindow, pickup, matchEnd
    so the rules-engine timeline can categorise inter-match events. iOS enum
    must be extended in lockstep (same string values, same camelCase casing).

    partnerCoordination added in doubles-spec extension (DOUBLES_SPEC_V1.md §C.1).
    Fires at T-60m relative to match scheduled_start when match is doubles.

    NOT a Postgres enum — this is an API contract enum only.
    """
    wakeUp = "wakeUp"
    meal = "meal"
    arrive = "arrive"
    warmUp = "warmUp"
    match = "match"
    recovery = "recovery"
    hydration = "hydration"
    # New cases — OQ-TRIAGE-1
    gap = "gap"
    foodWindow = "foodWindow"
    pickup = "pickup"
    matchEnd = "matchEnd"
    # Doubles-spec extension — DOUBLES_SPEC_V1.md §C.1
    partnerCoordination = "partnerCoordination"
    # Accommodations extension — ACCOMMODATIONS_V1.md §E.2
    # Emitted when accommodation_lat/lng set; anchor = match_start - ARRIVE_SNACK_MIN - drive_minutes.
    departure = "departure"
