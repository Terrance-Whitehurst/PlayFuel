"""Doubles-spec constants tests — DOUBLES_SPEC_V1.md §B.1.

Verifies:
    - RULES_CONSTANTS_VERSION == "1.1.0"
    - All 3 canonical keys present in SCENARIO_DURATIONS_MIN
    - Exact §B.1 values for each key (singles frozen; doubles DRAFT OQ-DBL-1)
    - MatchType and DoublesFormat enums have the correct string values
    - TimelineEventKind.partnerCoordination is present
"""
from playfuel_api.models.enums import DoublesFormat, MatchType, TimelineEventKind
from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION, SCENARIO_DURATIONS_MIN


# ── Version ───────────────────────────────────────────────────────────────────


def test_version_is_2_0_0():
    """Version must be '2.1.0' after Phase C-infrastructure additions."""
    assert RULES_CONSTANTS_VERSION == "2.1.0"


# ── Duration table — all three keys ───────────────────────────────────────────


def test_singles_durations_frozen():
    """§A.1 v1.0.0 FROZEN — singles row must not change."""
    row = SCENARIO_DURATIONS_MIN[("singles", None)]
    assert row["short"] == 75
    assert row["normal"] == 120
    assert row["long"] == 180


def test_doubles_best_of_3_durations():
    """DOUBLES_SPEC_V1.md §B.1 best_of_3 row [DRAFT — OQ-DBL-1]."""
    row = SCENARIO_DURATIONS_MIN[("doubles", "best_of_3")]
    assert row["short"] == 60
    assert row["normal"] == 90
    assert row["long"] == 135


def test_doubles_pro_set_8_durations():
    """DOUBLES_SPEC_V1.md §B.1 pro_set_8 row [DRAFT — OQ-DBL-1]."""
    row = SCENARIO_DURATIONS_MIN[("doubles", "pro_set_8")]
    assert row["short"] == 45
    assert row["normal"] == 70
    assert row["long"] == 100


def test_all_three_keys_present():
    """Three canonical keys must exist — no more, no fewer."""
    assert ("singles", None) in SCENARIO_DURATIONS_MIN
    assert ("doubles", "best_of_3") in SCENARIO_DURATIONS_MIN
    assert ("doubles", "pro_set_8") in SCENARIO_DURATIONS_MIN
    # Make sure no undocumented keys snuck in
    assert len(SCENARIO_DURATIONS_MIN) == 3


def test_each_row_has_three_keys():
    """Every duration row must have short, normal, long."""
    for key, row in SCENARIO_DURATIONS_MIN.items():
        assert set(row.keys()) == {"short", "normal", "long"}, (
            f"Row {key!r} is missing a duration key. Got: {set(row.keys())}"
        )


# ── MatchType enum ────────────────────────────────────────────────────────────


def test_match_type_singles_value():
    assert MatchType.singles == "singles"


def test_match_type_doubles_value():
    assert MatchType.doubles == "doubles"


# ── DoublesFormat enum ───────────────────────────────────────────────────────


def test_doubles_format_best_of_3_value():
    assert DoublesFormat.best_of_3 == "best_of_3"


def test_doubles_format_pro_set_8_value():
    assert DoublesFormat.pro_set_8 == "pro_set_8"


# ── TimelineEventKind.partnerCoordination ────────────────────────────────────


def test_partner_coordination_kind_exists():
    """TimelineEventKind must include partnerCoordination (DOUBLES_SPEC_V1.md §C.1)."""
    assert hasattr(TimelineEventKind, "partnerCoordination")
    assert TimelineEventKind.partnerCoordination == "partnerCoordination"
