# PlayFuel

> Tournament-day operating system for junior tennis parents. iPhone-first.

**Phase 1 complete · Phase 2 complete · Phase 3 complete · Phases 4–6 in progress**

---

## What is PlayFuel?

Junior tennis tournaments are chaotic. Parents make critical decisions about food, hydration,
warm-up timing, and logistics — often with no coach present, in unfamiliar venues, under
extreme heat. They don't lack information. They lack a plan.

PlayFuel is an iPhone app that generates a complete, weather-aware, scenario-based
tournament-day plan from a few inputs: match time, estimated next match time, venue location,
and current weather. The plan tells a parent exactly what to do and when — from wake-up to
recovery — across three match-duration scenarios (short, normal, long).

The engine is fully deterministic. A parent entering a 9:00 AM match at an 88°F Dallas venue
gets the same plan every time: `light_meal` window for the short scenario (165-minute gap),
`quick_pickup` for normal (120-minute gap), portable food pre-staged for the long scenario
(60-minute gap) — plus heat-illness emergency guidance and weather-adjusted hydration notes.
No language model invents the plan. A future explanation layer (Phase 6) translates the
structured output into parent-friendly prose, but the plan logic is pure, version-controlled
Python.

**Canonical demo scenario:**

> Tournament: Dallas Junior Open, XYZ Tennis Center, Dallas TX  
> Match 1: 9:00 AM · Est. Match 2: 1:00 PM  
> Weather: 88°F / 72% humidity → `hot` + `humid` → `extreme_heat_risk = true`  
> Output: EmergencyBanner · 3 scenario cards · weather-adjusted hydration · food pickup windows · pre-match timeline

---

## Demo / Screenshots

_(Screenshots TBD when iOS build is recordable)_

---

## Monorepo Layout

| Directory | Description |
|---|---|
| `apps/api/` | FastAPI backend — JWT auth, deterministic rules engine, Supabase integration |
| `apps/ios/PlayFuel/` | SwiftUI iOS app — Phase 1 static prototype; Phase 3 wires to live API |
| `db/supabase/` | Supabase schema migrations, RLS policies, Sign in with Apple wiring, seed data |
| `specs/` | Build plan (`PLAN.md`) |
| `.pi/multi-team/expertise/` | Canonical specs: PRD, user stories, rules constants, privacy, safety disclaimers |
| `.pi/multi-team/sessions/` | Multi-agent session logs (build artifact — most readers can ignore) |
| `docs/` | Documentation index |

> `.pi/multi-team/` is the multi-agent collaboration artifact directory used to build this
> project. Most users can ignore it. The canonical product specs live in
> `.pi/multi-team/expertise/` — see the [Documentation Map](#documentation-map) below.

---

## Stack

| Layer | Technology | Version |
|---|---|---|
| iOS | SwiftUI + Sign in with Apple | iOS 17+ |
| Backend | Python + FastAPI + Pydantic | Python ≥ 3.11 · FastAPI ≥ 0.115 · Pydantic ≥ 2.7 |
| Auth | Supabase Auth + Sign in with Apple → HS256 JWT | supabase-py ≥ 2.5 · PyJWT ≥ 2.8 |
| Database | Supabase Postgres + Row-Level Security | — |
| Settings | pydantic-settings | ≥ 2.3 |
| Weather | WeatherKit _or_ OpenWeather | TBD — Phase 4 (OQ-D) |
| Places | Google Places _or_ Yelp Fusion | TBD — Phase 5 |
| LLM | TBD (explanation layer only — never plan logic) | Phase 6 |

---

## Quickstart

### Database

**Prerequisites:** [Supabase CLI](https://supabase.com/docs/guides/cli) ≥ 1.150 · Docker Desktop ≥ 4.x

```bash
# Start the local Supabase stack
supabase start

# Apply all migrations (idempotent reset)
supabase db reset
```

`supabase db reset` runs all migrations in order and **auto-applies the Dallas demo
seed** (`db/supabase/seed/dallas_demo.sql`) via `supabase/config.toml` — no manual
`psql` step required.

Full setup (Sign in with Apple provider config, env vars): see `db/supabase/README.md`.

---

### Backend

**Prerequisites:** Python 3.11+

```bash
cd apps/api

# Install dependencies (including dev/test extras)
python3.12 -m pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env — fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
# (from Supabase Dashboard → Project Settings → API, or from `supabase status` for local dev)

# Run the server
uvicorn playfuel_api.main:app --reload --port 8000
```

- API auto-docs: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/healthz`

**Run tests:**

```bash
cd apps/api
python3.12 -m pytest src/playfuel_api/tests/ -v
```

---

### iOS

**Prerequisites:** Xcode 15+

1. `File → Open` → select `apps/ios/PlayFuel/` (Xcode detects `Package.swift`)
2. Set run target to an iPhone 17 simulator (iOS 17+)
3. Build and run — **no API keys needed for Phase 1** (all data is static)

> **Phase 3 wiring:** Replace `FakeData.swift` with a real API client. No View files change.
> See `apps/ios/PlayFuel/README.md`.

> Sign in with Apple requires a real bundle ID + Apple Developer account on a physical device.
> Simulator tap-to-fake-auth works without signing.

---

## Documentation Map

| Document | Path | Purpose |
|---|---|---|
| Architecture | `/ARCHITECTURE.md` | System design, components, data flow, auth model, rules engine invariants |
| Contributing | `/CONTRIBUTING.md` | Dev setup, test commands, code conventions, OQ system, PR guide |
| Docs Index | `/docs/INDEX.md` | Full index of every document in the repo |
| API README | `apps/api/README.md` | Endpoint inventory, design decisions, deviations |
| iOS README | `apps/ios/PlayFuel/README.md` | Xcode setup, Phase 3 swap path, screen tour |
| DB README | `db/supabase/README.md` | Migration order, RLS pattern, seed UUIDs, env vars |
| Build Plan | `specs/PLAN.md` | Phased roadmap, task IDs, parallelization, open questions |
| On-Device Testing | `docs/ON_DEVICE_TESTING.md` | Sequenced checklist: local dev loop → distribution path → Fly.io deploy → iOS signing → SIWA → smoke-test |
| PRD | `.pi/multi-team/expertise/PRD.md` | Product requirements, demo scenario, build phases |
| Rules Engine Spec | `.pi/multi-team/expertise/RULES_CONSTANTS_V1.md` | All constants, bucket boundaries, gap contract (v1.0.0) |
| Safety Disclaimers | `.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md` | Verbatim disclaimer text, prohibited phrases, heat-emergency guidance |
| Privacy | `.pi/multi-team/expertise/PRIVACY_V1.md` | COPPA posture, data inventory, App Store disclosures, deletion flow |

---

## Project Status & Roadmap

| Phase | Status | Deliverable |
|---|---|---|
| 0 — PRD + rules | ✅ Complete | PRD, user stories, safety docs, scenario acceptance, rules constants v1 |
| 1 — iOS prototype | ✅ Complete | SwiftUI shell with fake data (22 files, Dallas demo, EmergencyBanner) |
| 2 — Auth + DB | ✅ Complete | Supabase schema (9 tables, 6 enums, RLS), Sign in with Apple |
| 3 — FastAPI + engine | ✅ Complete | JWT auth, 18 endpoints, deterministic rules engine, 5 scenario acceptance tests |
| 4 — Weather | 🔲 Pending | Weather API client (WeatherKit/OpenWeather), flag classifier, plan adjustments |
| 5 — Food / Places | 🔲 Pending | Nearby food search, restaurant templates, recommended orders |
| 6 — LLM layer | 🔲 Pending | Structured plan JSON → parent-friendly explanation (deliberately deferred) |
| 7 — Feedback | 🔲 Pending | Post-tournament rating screen, what-worked / what-didn't |
| 8 — Beta | 🔲 Pending | TestFlight build, 5–10 junior tennis families |
| Privacy | 🟡 In progress | COPPA review, App Store disclosures (PRIVACY_V1 drafted; legal review pending) |
| Eval | 🔲 Pending | 5 canonical scenario tests (automated harness) |

The **LLM explanation layer (Phase 6) is deliberately deferred** to keep v1 fully deterministic.
The rules engine — not a language model — owns all plan logic. The LLM will explain the plan
in parent-friendly prose; it will never change or invent any value in it.

**Explicitly out of scope for MVP:** fine-tuning · on-device LLM · menu scraping · coach
dashboard · recruiting · social network · player rankings · wearable integrations · push
notifications · USTA schedule scraping.

---

## Safety & Privacy

PlayFuel provides general tournament preparation guidance. It is **not** medical advice,
nutrition therapy, or a substitute for a coach, physician, athletic trainer, or registered
dietitian. See [`.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md`](.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md)
for the full verbatim disclaimer, prohibited phrases, and heat-emergency guidance.

All data is parent-owned. No child-owned accounts in MVP. No data selling, no advertising,
no third-party tracking SDKs. See [`.pi/multi-team/expertise/PRIVACY_V1.md`](.pi/multi-team/expertise/PRIVACY_V1.md)
for COPPA posture, the full data inventory (9 tables × 67 columns), App Store privacy
disclosures, and account deletion flow.

---

## License

_(TBD pre-launch)_
