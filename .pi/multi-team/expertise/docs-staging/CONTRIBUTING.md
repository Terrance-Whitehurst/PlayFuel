# Contributing to PlayFuel

> Audience: someone about to make their first PR.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Existing scripts and docs use Python 3.12 |
| Xcode | ≥ 15 | Required for iOS 17 simulator target |
| Supabase CLI | ≥ 1.150 | `brew install supabase/tap/supabase` |
| Docker Desktop | ≥ 4.x | Required by Supabase local stack |
| Apple Developer account | Any tier | Required for Sign in with Apple on **physical device only** — simulator works without |

---

## Local Dev Setup

### Step 1: Database

```bash
# Start the local Supabase stack (requires Docker)
supabase start
```

On success you'll see output like:

```
API URL: http://localhost:54321
DB URL:  postgresql://postgres:postgres@localhost:54322/postgres
Studio:  http://localhost:54323
Anon Key: <key>
Service Role Key: <key>
JWT Secret: <secret>
```

Copy the Anon Key, Service Role Key, and JWT Secret — you'll need them for the backend `.env`.

```bash
# Apply all migrations (idempotent)
supabase db reset
```

`supabase db reset` runs all four migration files in order:
1. `0001_extensions_and_enums.sql`
2. `0002_tables.sql`
3. `0003_rls.sql`
4. `0004_auth_trigger.sql`

To apply migrations without dropping data: `supabase db push`.
To open the local Studio UI: `open http://localhost:54323`.

Full Sign in with Apple provider setup is documented in `db/supabase/auth/sign-in-with-apple.md`.

---

### Step 2: Backend

```bash
cd apps/api

# Install all dependencies (including dev/test extras)
python3.12 -m pip install -e ".[dev]"

# Configure environment
cp .env.example .env
```

Edit `.env` with the values from `supabase start` output (or your Supabase Cloud project):

```ini
SUPABASE_URL=http://localhost:54321          # or https://your-project.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_JWT_SECRET=<jwt secret>
SUPABASE_SERVICE_ROLE_KEY=<service role key>  # server-side only; never expose to clients
API_PORT=8000
```

For Supabase Cloud: values are at **Dashboard → Project Settings → API**.

```bash
# Run the development server
uvicorn playfuel_api.main:app --reload --port 8000
```

- API auto-docs: `http://localhost:8000/docs`
- Liveness probe: `http://localhost:8000/healthz`
- `RULES_CONSTANTS_VERSION` is logged to stdout on startup

---

### Step 3: iOS

```bash
# No install step — zero external dependencies in Phase 1
```

1. `File → Open` in Xcode → select `apps/ios/PlayFuel/` (Xcode detects `Package.swift`)
2. Set run target to an **iPhone 17 simulator** (iOS 17+)
3. Build and run

Phase 1 runs entirely on `FakeData.swift` — no API keys, no Supabase, no environment setup
required. See `apps/ios/PlayFuel/README.md` for the Phase 3 swap path (one-file replacement).

> Sign in with Apple requires a real bundle ID + Apple Developer account to function on a
> physical device. The simulator tap-to-fake-auth intercept works without signing.

---

### Step 4: Seed Data

The Dallas demo seed fixture is at `db/supabase/seed/dallas_demo.sql`. Load it manually:

```bash
psql "$(supabase status --output json | jq -r '.DB_URL')" \
  -f db/supabase/seed/dallas_demo.sql
```

No seed data exists yet for fixtures outside the Dallas demo scenario.
_[TODO: verify whether auto-seed via `supabase/config.toml` is configured]_

Stable seed UUIDs (safe to hardcode in integration tests):

| Entity | UUID |
|---|---|
| Demo user | `a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Dallas Junior Open tournament | `b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Match 1 (9:00 AM) | `c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Match 2 (1:00 PM) | `d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Weather snapshot | `e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |

---

### Step 5: Getting a Test JWT for API Development

Protected endpoints require `Authorization: Bearer <supabase_access_token>`. To get one:

1. Sign in through the local Supabase Studio (`http://localhost:54323`) or the iOS app
2. Copy the access token from Supabase Auth dashboard
3. Use as `Authorization: Bearer <token>` in `curl`, Postman, or the Swagger UI at `/docs`

No automated test-JWT tooling exists yet — the `conftest.py` mocks auth in unit tests.

---

## Running Tests

### Backend

```bash
cd apps/api
python3.12 -m pytest src/playfuel_api/tests/ -v
```

Run a single file:

```bash
python3.12 -m pytest src/playfuel_api/tests/test_buckets.py -v
```

**Test matrix:**

| File | What it covers |
|---|---|
| `test_constants.py` | `RULES_CONSTANTS_VERSION == "1.0.0"`, `SCENARIO_DURATIONS_MIN` literal |
| `test_buckets.py` | 13 named boundary cases (incl. `test_gap_120_is_quick_pickup`) |
| `test_weather.py` | Parametrized: 6 weather inputs × all 7 flags |
| `test_scenarios.py` | 5 SCENARIO_ACCEPTANCE cases; Scenario 5 `xfail` |
| `test_routes_smoke.py` | `/healthz` → 200; no token → 401; mocked auth → 200 |

Expected: 5 passed, 1 xfailed (Scenario 5 rain delay — deferred to Phase 4).

### iOS

No automated tests in Phase 1. Manual smoke via Xcode simulator:

1. Open `apps/ios/PlayFuel/` in Xcode
2. Run on iPhone 17 simulator
3. Tap "Dallas Spring Open" → verify red `EmergencyBanner` appears (88°F + 72% humidity → `extremeHeatRisk = true`)
4. Swipe through scenario cards — verify Short/Normal/Long show correct gaps and bucket labels
5. Tap "Full Day Timeline" — verify 12 chronological events from 6:00 AM

### Database

```bash
# Verify no schema drift after db reset
supabase db diff   # should show no diff
```

RLS policy documentation: `db/supabase/policies/README.md`.

---

## Code Conventions

### API (Python)

- **Internals:** `snake_case` everywhere (Python standard)
- **JSON output:** `camelCase` via `alias_generator=to_camel` in `models/api.py`
- Every route returning `Plan` or `ScenarioPlan` must use:
  - `response_model_by_alias=True` on the route decorator **or**
  - `model.model_dump(by_alias=True, mode="json")` when persisting to JSONB
- `supabase-py` client **must** be created per-request: `client.postgrest.auth(jwt)` —
  never use the service role key on protected routes
- **No `WHERE user_id = ?` or `eq("user_id", ...)` in route handlers** — Postgres RLS owns
  all ownership checks

### iOS (Swift)

- Standard Swift naming (camelCase properties, PascalCase types)
- iOS models mirror the API's `ScenarioPlan` / `Plan` shapes exactly — don't add fields
  that don't exist in the API response
- Disclaimer text and heat-emergency text **must** come from `HardCodedStrings.swift` —
  never re-type them in View files

### Database

- `snake_case` column names
- Half-open `[a, b)` ranges where applicable (gap-bucket boundary values)
- RLS policies use `(select auth.uid())` (parenthesised form) for query planner caching —
  see `db/supabase/policies/README.md` for rationale
- No bare `auth.uid()` calls in policies

### Tests

- **Name boundary-regression tests explicitly:** `test_gap_120_is_quick_pickup`, not
  `test_gap_boundary_3`
- Parametrize weather tests over the full 6-case matrix — don't add ad-hoc weather tests
- Deferred scenario tests (Scenario 5 rain delay) use
  `@pytest.mark.xfail(reason="OQ-F deferred to Phase 4")` — document the contract in the
  test body, don't implement it

---

## The OQ System

Open questions are how the team handles uncertainty without shipping guesses.

**Anatomy of an OQ:**
- Tagged inline in code as `# [DRAFT — OQ-X]` or `# OQ-X: ...`
- Listed in the canonical spec that owns the relevant decision
  (e.g., `RULES_CONSTANTS_V1.md §I`, `PRIVACY_V1.md §11`)
- Identified as `OQ-<TOPIC>-<N>` (e.g., `OQ-E`, `OQ-QA-1`, `OQ-PRIV-3`)

**Rules:**
- **Don't silently resolve an OQ.** If your PR changes something an OQ is about, surface
  it in the PR description and update the owning spec.
- **New OQ?** Add it to the owning spec's open-questions section and add a `[DRAFT]` comment
  at the relevant code location.
- **Legal blockers (`OQ-06`, `OQ-11`)** require a lawyer, not an engineer.

---

## Making Changes to Canonical Specs

Files in `.pi/multi-team/expertise/*.md` are **versioned narrative** — each file represents
a frozen snapshot at a point in time.

- **Do not edit a V1 spec in place** — create `RULES_CONSTANTS_V2.md` (for example) and
  archive the V1 file
- **Engineering does not edit specs unilaterally** — specs are co-authored between Planning
  and Engineering; see `RULES_CONSTANTS_V1.md §J.3` for the change-control matrix
- **Version bump rules:**
  - Typo/formatting only → patch: `1.0.0 → 1.0.1`
  - Boundary value or threshold change → minor: `1.0.x → 1.1.0`
  - New section or OQ resolution → minor or major

---

## PR Conventions

- Branch off `main`
- **PR title format:** `[area] short description`
  - Examples: `[api] fix gap-120 bucket boundary`, `[ios] wire FakeData to live API`,
    `[db] add match index`, `[docs] expand quickstart`
- Green tests required before merge
- Link any OQ your PR resolves in the PR description
- Changes to `rules/constants.py` require Planning + Engineering sign-off per
  `RULES_CONSTANTS_V1.md §J.3`

---

## Code of Conduct & Licensing

_(TBD pre-launch; will be added alongside the public license)_
