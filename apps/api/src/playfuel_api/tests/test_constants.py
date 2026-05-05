"""Constants smoke tests — RULES_CONSTANTS_V1.md §J.2 + DOUBLES_SPEC_V1.md §B.1.

Asserts that the frozen constants are byte-for-byte correct.
Any value drift here signals an uncommitted version bump (§J.3).

v1.1.0 changes:
- RULES_CONSTANTS_VERSION bumped from "1.1.0" to "2.0.0" (Phase B metric recalibration)
- RULES_CONSTANTS_VERSION bumped from "2.0.0" to "2.1.0" (Phase C-infrastructure)
- RULES_CONSTANTS_VERSION bumped from "2.1.0" to "2.2.0" (ACCOMMODATIONS_V1: added ARRIVE_SNACK_MIN)
- RULES_CONSTANTS_VERSION bumped from "2.2.1" to "2.2.2" (DR-PLACES-1: places.distanceMeters removed from Google field mask)
- SCENARIO_DURATIONS_MIN changed from flat dict[str,int] to nested dict
  keyed by (match_type, doubles_format | None).
"""
from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION, SCENARIO_DURATIONS_MIN


def test_rules_constants_version():
    """§J.1 — version must be exactly '2.2.2' (DR-PLACES-1: places.distanceMeters removed from Google field mask)."""
    assert RULES_CONSTANTS_VERSION == "2.2.2"


def test_scenario_durations_min_singles():
    """§A.1 — singles row must be FROZEN at v1.0.0 values."""
    assert SCENARIO_DURATIONS_MIN[("singles", None)] == {
        "short": 75,
        "normal": 120,
        "long": 180,
    }


def test_scenario_durations_min_doubles_best_of_3():
    """DOUBLES_SPEC_V1.md §B.1 — doubles best_of_3 row [DRAFT — OQ-DBL-1]."""
    assert SCENARIO_DURATIONS_MIN[("doubles", "best_of_3")] == {
        "short": 60,
        "normal": 90,
        "long": 135,
    }


def test_scenario_durations_min_doubles_pro_set_8():
    """DOUBLES_SPEC_V1.md §B.1 — doubles pro_set_8 row [DRAFT — OQ-DBL-1]."""
    assert SCENARIO_DURATIONS_MIN[("doubles", "pro_set_8")] == {
        "short": 45,
        "normal": 70,
        "long": 100,
    }


def test_scenario_durations_min_all_keys_present():
    """All three canonical keys must be present."""
    assert ("singles", None) in SCENARIO_DURATIONS_MIN
    assert ("doubles", "best_of_3") in SCENARIO_DURATIONS_MIN
    assert ("doubles", "pro_set_8") in SCENARIO_DURATIONS_MIN
