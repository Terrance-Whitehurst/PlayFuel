# PlayFuel — Supabase Database Layer

> Phase 2 deliverable. Provides schema migrations, RLS policies, Sign in with Apple
> wiring, and a canonical seed fixture for local development.

---

## Directory Structure

```
db/supabase/
├── README.md                         ← you are here
├── .env.example                      ← copy to .env and fill in real values
├── migrations/
│   ├── 0001_extensions_and_enums.sql ← pgcrypto + all Postgres enums
│   ├── 0002_tables.sql               ← all tables, indexes, updated_at triggers
│   ├── 0003_rls.sql                  ← RLS enable + all policies (4 per table)
│   └── 0004_auth_trigger.sql         ← handle_new_user() + on_auth_user_created
├── seed/
│   └── dallas_demo.sql               ← canonical Dallas tournament fixture
├── policies/
│   └── README.md                     ← plain-English RLS policy reference
└── auth/
    └── sign-in-with-apple.md         ← Apple Developer + Supabase provider setup
```

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Supabase CLI | ≥ 1.150 | `brew install supabase/tap/supabase` |
| Docker Desktop | ≥ 4.x | Required by Supabase local stack |

---

## Quick Start — Local Development

### 1. Start the local Supabase stack

```bash
cd /path/to/PlayFuel
supabase start
```

This pulls the Supabase Docker images and starts Postgres, Auth, Storage, and the
Studio UI. First run takes a few minutes.

On success you'll see output like:
```
API URL: http://localhost:54321
DB URL:  postgresql://postgres:postgres@localhost:54322/postgres
Studio:  http://localhost:54323
Anon Key: <key>
Service Role Key: <key>
JWT Secret: <secret>
```

Copy the Anon Key and Service Role Key into `db/supabase/.env`.

### 2. Apply migrations

```bash
supabase db reset
```

`db reset` drops the local database, re-creates it, runs every migration in
`migrations/` in filename order, then runs any seed files. It is fully idempotent.

To apply migrations without dropping (incremental apply):
```bash
supabase db push
```

### 3. Verify the schema

```bash
supabase db diff
```

Should show no diff after a clean `db reset`.

### 4. Apply seed data (Dallas demo)

`supabase db reset` now auto-applies the Dallas demo seed via `supabase/config.toml`
at the repo root. Manual `psql` application is no longer required.

### 5. Open Supabase Studio

```bash
open http://localhost:54323
```

---

## Migration Order

Migrations **must** be applied in filename order:

| File | What it does |
|---|---|
| `0001_extensions_and_enums.sql` | Enables pgcrypto; creates all Postgres enum types |
| `0002_tables.sql` | Creates all tables, FK indexes, `set_updated_at()` trigger function, per-table triggers |
| `0003_rls.sql` | Enables RLS; creates all 4 policies per table |
| `0004_auth_trigger.sql` | Creates `handle_new_user()` (SECURITY DEFINER) + `on_auth_user_created` trigger on `auth.users` |
| `0005_match_labels.sql` | Adds nullable `round_label`, `opponent_label`, `court_label` text columns to `public.matches` (resolves OQ-API-1a) |
| `0006_plan_llm_summary.sql` | Adds nullable `llm_summary` jsonb column to `public.plans` for Phase 6 LLM explanation layer (Phase 6) |
| `0007_doubles_support.sql` | Adds nullable `doubles_format` text column to `public.matches` and nullable `match_type` text column to `public.plans` for doubles-spec extension (DOUBLES_SPEC_V1.md) |
| `0008_per_match_plans.sql` | Adds nullable `match_id` uuid FK column to `public.plans` (ON DELETE CASCADE to `matches`) and a partial unique index `plans_match_id_match_type_uq` — enforces one plan per (match, match_type). Partial index excludes null match_ids (legacy rows). See NUTRITION_FIRST_IA_V1.md §E. |
| `0009_plans_upsert_constraint.sql` | Ensures the partial unique index on `(match_id, match_type)` exists for idempotent plan upserts (resolves OQ-IA-9). |
| `0010_players_and_notes.sql` | Creates `public.players` and `public.player_notes` tables, `player_note_source` enum, adds nullable `opponent_player_id` FK to `public.matches`. Includes RLS (8 new policies). See PLAYER_SCOUTING_V1.md §B. |
| `0011_match_evaluations.sql` | Creates `public.match_evaluations` table, `match_eval_result` enum (`won`/`lost`/`withdrew`/`retired`), 4 RLS policies. One row per match (UNIQUE on `match_id`). Auto-syncs `opponent_observations` to `player_notes` via `services/post_match_sync.py`. See POST_MATCH_EVAL_V1.md §B. |
| `0012_tournament_location.sql` | Adds nullable `venue_place_id` TEXT column to `public.tournaments`; adds coords-pair CHECK constraint; creates `public.tournament_places_cache` table (keyed by `(tournament_id, place_type)`, JSONB payload, 24h TTL enforced at API layer) + 4 RLS policies. See TOURNAMENT_LOCATION_V1.md §C. |

---

## Fixed UUIDs (Dallas Demo Seed)

These UUIDs are stable across seed runs — use them in integration tests.

| Entity | UUID |
|---|---|
| Demo user | `a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Dallas Junior Open tournament | `b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Match 1 (9:00 AM) | `c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Match 2 (1:00 PM) | `d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |
| Weather snapshot | `e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11` |

---

## Environment Variables

| Variable | Where used | Notes |
|---|---|---|
| `SUPABASE_URL` | FastAPI backend, iOS app | Public project URL |
| `SUPABASE_ANON_KEY` | iOS app only | Client-facing; RLS enforced |
| `SUPABASE_SERVICE_ROLE_KEY` | FastAPI backend only | Bypasses RLS; never expose to client |
| `APPLE_SERVICE_ID` | Supabase Dashboard (Apple provider config) | |
| `APPLE_TEAM_ID` | Supabase Dashboard | |
| `APPLE_KEY_ID` | Supabase Dashboard | |
| `APPLE_PRIVATE_KEY_PATH` | Supabase Dashboard / local .p8 file | |
| `APPLE_REDIRECT_URL` | Supabase Dashboard, Apple Developer portal | Must match exactly |

See `auth/sign-in-with-apple.md` for full Apple provider setup steps.

---

## Key Design Decisions

### RLS Pattern
All user-owned tables use `(select auth.uid())` (parenthesised) for query planner caching.
Child tables use `EXISTS (select 1 from parent ... where user_id = (select auth.uid()))`.
No bare `auth.uid()` calls. See `policies/README.md` for full policy reference.

### schedule_confidence (resolves OQ-G)
Stored on `plans` as an enum `{high, medium, low}`. The FastAPI backend derives it
before INSERT using the following rule:
- `'low'`    — any scenario has `gap_status IN ('overrun', 'no_next_match')`
- `'medium'` — any scenario has `gap_status = 'tight'`
- `'high'`   — otherwise (default)

### Cascade Deletes
All FK relationships cascade on DELETE. Deleting a `users` row deletes all their data
in one operation — required by PRD §11 account deletion flow.

### updated_at Trigger
One shared `set_updated_at()` function; one `BEFORE UPDATE` trigger per table.
Function body is not duplicated.

---

## Stopping the Local Stack

```bash
supabase stop
```

Data is persisted in a Docker volume between `stop`/`start` cycles.
To wipe all local data: `supabase stop --backup=false && supabase db reset`.
