"""PlayFuel rules-engine scenario acceptance eval harness.

Run from apps/api/:
    python3.12 -m playfuel_api.eval.run_acceptance

Exit 0  → no unexpected failures (xfails don't count).
Exit 1  → at least one unexpected failure.

See eval/fixtures/scenario_acceptance.py for the 5 canonical cases.
"""
