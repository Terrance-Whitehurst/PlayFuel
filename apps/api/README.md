# PlayFuel API

FastAPI backend + deterministic plan-generation engine for PlayFuel (Phase 3).

**Rules source:** `RULES_CONSTANTS_V1.md` — version 1.0.0  
**Schema source:** `db/supabase/migrations/` (Engineering3, Task #4)  
**Pairs with:** `apps/ios/PlayFuel/` (Task #3 SwiftUI prototype)

---

## Architecture Summary

```
apps/api/
├── pyproject.toml              # python 3.11+, fastapi, pydantic v2, pyjwt[crypto], supabase
├── .env.example                # copy → .env; never commit
└── src/playfuel_api/
    ├── main.py                 # FastAPI app, CORS, router mounting
    ├── auth.py                 # verify_supabase_jwt() — HS256 via pyjwt
    ├── db.py                   # per-request Supabase client (anon key + user JWT → RLS)
    ├── settings.py             # pydantic-settings reading .env
    ├── rules/
    │   ├── constants.py        # RULES_CONSTANTS_VERSION, SCENARIO_DURATIONS_MIN, thresholds
    │   ├── hard_coded_strings.py  # OVERRUN_MESSAGE, HEAT_EMERGENCY_TEXT, bucket text
    │   ├── weather.py          # classify_weather() → flag dict incl. extreme_heat_risk
    │   ├── buckets.py          # food_bucket_for(), pickup_bucket_for() — half-open intervals
    │   ├── scenarios.py        # generate_match_scenarios() — pure, no I/O
    │   └── plan.py             # build_plan_envelope(), derive_schedule_confidence()
    ├── models/
    │   ├── enums.py            # StrEnum mirrors of Postgres enum types (byte-for-byte)
    │   ├── db.py               # Pydantic mirrors of public.* tables
    │   └── api.py              # ScenarioPlan, Plan, MatchInput + request/response shapes
    ├── routes/
    │   ├── health.py           # GET /healthz (no auth)
    │   ├── player_profiles.py  # CRUD /v1/player-profiles
    │   ├── tournaments.py      # CRUD /v1/tournaments
    │   ├── matches.py          # CRUD /v1/tournaments/{tid}/matches
    │   └── plans.py            # POST /v1/tournaments/{tid}/plans/generate; GET list/detail
    └── tests/
        ├── conftest.py
        ├── test_constants.py   # RULES_CONSTANTS_VERSION assertion
        ├── test_buckets.py     # 13 half-open boundary cases
        ├── test_weather.py     # all 6 primary flags + extreme_heat_risk derivation
        ├── test_scenarios.py   # 5 SCENARIO_ACCEPTANCE cases (Scenario 5 xfail)
        └── test_routes_smoke.py  # /healthz 200; protected → 403 without bearer
```

---

## Quick Start — Local Development

### Prerequisites

- Python 3.11+
- A running Supabase project (or local `supabase start`)

### 1. Install dependencies

```bash
cd apps/api
python3.12 -m pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL, anon key, and JWT secret
```

Values are available in:
- **Supabase Cloud:** Dashboard → Project Settings → API
- **Local:** `supabase status` output after `supabase start`

### 3. Run the server

```bash
cd apps/api
uvicorn playfuel_api.main:app --reload --port 8000
```

API docs auto-generated at: http://localhost:8000/docs

### 4. Run tests

```bash
cd apps/api
python3.12 -m pytest src/playfuel_api/tests/ -v
```

Run a single test file:
```bash
python3.12 -m pytest src/playfuel_api/tests/test_buckets.py -v
```

---

## Key Design Decisions

### Auth — anon key + user JWT (not service role)

Every protected route requires `Authorization: Bearer <supabase_access_token>`.
The token is verified with HS256 using `SUPABASE_JWT_SECRET`. The extracted JWT
is then passed to the supabase-py PostgREST client as the auth header so
Postgres RLS automatically enforces row ownership.

**The service role key bypasses RLS and is NOT used for any protected route.**
It is loaded from env only for potential future admin/Phase 6 use.

### Rules engine — pure, deterministic, no LLM

`generate_match_scenarios()` is a pure Python function (no I/O, no LLM).
Phase 6 (Task #9) will add the LLM explanation layer on top of the structured
`Plan` output. The rules engine never calls an LLM.

### JSON key convention — camelCase

The API serializes responses with camelCase field names (via Pydantic
`alias_generator=to_camel`) to match iOS Swift property names directly.
Enum *values* remain snake_case (e.g. `"no_next_match"`, `"bag_only"`) as
defined in both the Postgres enums and the iOS `Codable` enums.

Phase 3 iOS wiring (Task #6) can use `JSONDecoder()` with no extra configuration
because field names already match Swift property names.

> Deviation from §G JSON shapes (which show snake_case keys): see DEVIATIONS section.

### MVP scope — first match only

`POST /v1/tournaments/{tid}/plans/generate` generates scenarios for the **first
match** (by `display_order`) and uses the **second match** (if any) as the
next-match reference. All three short/normal/long scenarios are generated.
Multi-match day iteration is a Phase 4 concern.

### schedule_confidence derivation

Derived before INSERT per `db/supabase/README.md` (resolves OQ-G):
- `low` — any scenario has `gap_status IN ('overrun', 'no_next_match')`
- `medium` — any scenario has `gap_status = 'tight'`
- `high` — otherwise

### DRAFT OQs surfaced

| OQ | Status in this task |
|---|---|
| OQ-E | `TIGHT_GAP_THRESHOLD_MIN = 30` — Engineering1 proposal, still DRAFT. Unit-tested with this value. |
| OQ-11 | `HEAT_EMERGENCY_TEXT` is DRAFT pending legal review. Flagged in `hard_coded_strings.py`. |
| OQ-C | Pre-match/warm-up offsets are DRAFT (not implemented in Phase 3 engine). |
| OQ-A | Hydration quantities are DRAFT (not implemented in Phase 3 engine). |

---

## Deviations

| # | Deviation | Reason |
|---|---|---|
| 1 | API returns **camelCase** field names, not snake_case (§G JSON shapes show snake_case) | iOS Swift properties are camelCase; no-config Phase 3 wiring. Documented here + delivery report. |
| 2 | `schedule_confidence = 'low'` when `gap_status = 'no_next_match'` | Per `db/supabase/README.md` OQ-G resolution — implemented as specified. |
| 3 | MVP generates scenarios for first match only | Per brief: "first match in display_order + estimated next match" canonical use case. |

---

## Endpoint Inventory

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | no | Liveness probe |
| GET | `/v1/me` | yes | Echo user_id from JWT |
| GET | `/v1/player-profiles` | yes | List caller's player profiles |
| POST | `/v1/player-profiles` | yes | Create player profile |
| PATCH | `/v1/player-profiles/{id}` | yes | Update player profile |
| DELETE | `/v1/player-profiles/{id}` | yes | Delete player profile |
| GET | `/v1/tournaments` | yes | List caller's tournaments |
| POST | `/v1/tournaments` | yes | Create tournament |
| GET | `/v1/tournaments/{id}` | yes | Get tournament |
| PATCH | `/v1/tournaments/{id}` | yes | Update tournament |
| DELETE | `/v1/tournaments/{id}` | yes | Delete tournament (cascades) |
| GET | `/v1/tournaments/{tid}/matches` | yes | List matches for tournament |
| POST | `/v1/tournaments/{tid}/matches` | yes | Create match |
| PATCH | `/v1/tournaments/{tid}/matches/{mid}` | yes | Update match |
| DELETE | `/v1/tournaments/{tid}/matches/{mid}` | yes | Delete match |
| GET | `/v1/tournaments/{tid}/plans` | yes | List plans for tournament |
| POST | `/v1/tournaments/{tid}/plans/generate` | yes | Run rules engine, persist plan, return Plan |
| GET | `/v1/plans/{id}` | yes | Fetch one plan |
