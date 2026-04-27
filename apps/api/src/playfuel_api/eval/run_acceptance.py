"""PlayFuel scenario acceptance eval harness.

Run from apps/api/:
    python3.12 -m playfuel_api.eval.run_acceptance

Checks all 5 SCENARIO_ACCEPTANCE.md cases against the live rules engine.
Scenario 5 (rain delay) is marked xfail per OQ-F — it is expected to fail
and does not contribute to the exit code.

Exit 0  → no unexpected failures.
Exit 1  → at least one unexpected failure (a scenario failed that was not xfail).

Output format:
    === SCENARIO ACCEPTANCE EVAL ===
    [PASS]  Scenario 1 — Cool 9/1 baseline
    [PASS]  Scenario 2 — Hot/humid Dallas demo
    [PASS]  Scenario 3 — Long gap
    [PASS]  Scenario 4 — Back-to-back
    [XFAIL] Scenario 5 — Rain delay (OQ-F deferred to Phase 4)
    ====================================
    4 passed, 1 expected fail, 0 failed
"""
from __future__ import annotations

import sys
import traceback
from uuid import uuid4

from playfuel_api.eval.fixtures.scenario_acceptance import FIXTURES
from playfuel_api.rules.plan import build_plan_envelope
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.rules.weather import classify_weather


# ── Value resolver ────────────────────────────────────────────────────────────

def _resolve(obj, path: str):
    """Resolve a dotted path like 'scenarios[1].gap_status' against a result dict.

    Result dict has keys: 'scenarios' (list[ScenarioPlan]), 'plan' (Plan),
    'weather' (dict[str, bool] | None).

    Supports:
        scenarios[N].attr.subattr
        plan.attr
        weather.attr
        plan.heat_emergency_text_is_set  (special: checks is not None)
    """
    parts = path.split(".")
    current = obj

    # Handle special sentinel key
    if path == "plan.heat_emergency_text_is_set":
        return current["plan"].heat_emergency_text is not None

    for part in parts:
        if "[" in part:
            # e.g. scenarios[1]
            name, rest = part.split("[")
            idx = int(rest.rstrip("]"))
            current = getattr(current, name, None) if not isinstance(current, dict) else current[name]
            current = current[idx]
        elif isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, part)

    return current


# ── Runner ────────────────────────────────────────────────────────────────────

def run_scenario(fixture: dict) -> tuple[bool, str]:
    """Run one scenario fixture. Returns (passed, failure_detail).

    For xfail scenarios: always returns (True, "") — they are always expected to "pass"
    the runner's exit-code check. The caller prints [XFAIL].
    """
    if fixture["xfail"]:
        # Don't run assertions — document the contract only.
        return True, ""

    try:
        match = fixture["match"]
        next_match = fixture["next_match"]
        weather_kwargs = fixture.get("weather")

        # Generate scenarios
        scenarios = generate_match_scenarios(match, next_match)

        # Classify weather if provided
        weather_flags = classify_weather(**weather_kwargs) if weather_kwargs else None

        # Build plan envelope
        plan = build_plan_envelope(
            uuid4(),
            scenarios,
            weather_flags=weather_flags,
        )

        # Bundle result for resolver
        result = {
            "scenarios": scenarios,
            "plan": plan,
            "weather": weather_flags,
        }

        # Check all expected assertions
        failures = []
        for path, expected_value in fixture["expected"].items():
            actual = _resolve(result, path)
            if actual != expected_value:
                failures.append(
                    f"  {path}: expected {expected_value!r}, got {actual!r}"
                )

        if failures:
            return False, "\n".join(failures)

        return True, ""

    except Exception:
        return False, traceback.format_exc()


def main() -> int:
    print("=== SCENARIO ACCEPTANCE EVAL ===")

    passed = 0
    failed = 0
    xfailed = 0
    fail_details = []

    for fixture in FIXTURES:
        name = fixture["name"]
        is_xfail = fixture["xfail"]
        ok, detail = run_scenario(fixture)

        if is_xfail:
            print(f"[XFAIL] {name}")
            xfailed += 1
        elif ok:
            print(f"[PASS]  {name}")
            passed += 1
        else:
            print(f"[FAIL]  {name}")
            fail_details.append((name, detail))
            failed += 1

    print("====================================")
    print(f"{passed} passed, {xfailed} expected fail, {failed} failed")

    if fail_details:
        print()
        print("--- FAILURES ---")
        for name, detail in fail_details:
            print(f"\n{name}:")
            print(detail)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
