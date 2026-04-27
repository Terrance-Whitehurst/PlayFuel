"""Constants smoke tests — RULES_CONSTANTS_V1.md §J.2.

Asserts that the frozen constants are byte-for-byte correct.
Any value drift here signals an uncommitted version bump (§J.3).
"""
from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION, SCENARIO_DURATIONS_MIN


def test_rules_constants_version():
    """§J.1 — version must be exactly '1.0.0'."""
    assert RULES_CONSTANTS_VERSION == "1.0.0"


def test_scenario_durations_min_dict():
    """§A.1 — all three durations must match source-of-truth values."""
    assert SCENARIO_DURATIONS_MIN == {
        "short": 75,
        "normal": 120,
        "long": 180,
    }
