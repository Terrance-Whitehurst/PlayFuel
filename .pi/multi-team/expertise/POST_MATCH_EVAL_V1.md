# PlayFuel — Post-Match Evaluation (v1)

> **Status:** v1 spec · **Authority:** Product Manager · **Last updated:** 2026-04-28
> **Sources of truth verified before scribing:**
> - `db/supabase/migrations/` — `ls` run: 0001–0010 confirmed; **0011 is the next free number** ✅
> - `db/supabase/migrations/0002_tables.sql` — `matches.tournament_id` exists, FK `public.users(id)` pattern confirmed ✅
> - `db/supabase/migrations/0010_players_and_notes.sql` — enum DO-block syntax, trigger pattern, RLS chain-through pattern confirmed ✅
> - `apps/api/src/playfuel_api/models/api.py` — `_CAMEL`, `OpponentNoteForLLM`, `PlayerNoteCreate`, `PlanExplanationInput` shapes confirmed ✅
> - `apps/api/src/playfuel_api/models/enums.py` — `PlayerNoteSource` enum confirmed; no new `match_eval_result` enum collision ✅
> - `apps/api/src/playfuel_api/routes/__init__.py` — router mount is via `routers` list in `routes/__init__.py`, NOT directly in `main.py` ✅ **(I-6 correction — brief was wrong)**
> - `apps/api/src/playfuel_api/routes/players.py` — nested-resource route pattern (`/v1/players/{pid}/notes`) confirmed ✅
> - `apps/api/src/playfuel_api/services/scouting.py` — `fetch_opponent_notes_for_match`, sanitization pipeline confirmed ✅
> - `apps/ios/PlayFuel/Sources/PlayFuel/Views/ScheduleStripView.swift` — strip taps only set `selectedMatchId`; no existing drill-in path ✅
> - `apps/ios/PlayFuel/Sources/PlayFuel/Views/MatchCreateView.swift` — player-scouting state already present from prior delegate ✅
> - `.pi/multi-team/expertise/PLAYER_SCOUTING_V1.md` — auto-note loop, idempotency context ✅
> - `.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md §C` — prohibited-phrase list confirmed ✅
> - `.pi/multi-team/expertise/PRIVACY_V1.md §13` — "Notes about other minors" section covers `opponent_observations` ✅
> - `.pi/multi-team/expertise/USER_STORIES.md` — US-PLAYER-* last entry is US-PLAYER-5 ✅

---

## §I — PM Verification Findings (Pre-Scribe Disk Read)

> Structural catches from reading every source-of-truth file before scribing.
> Each would have failed at build time if uncorrected.

| # | Finding | Severity | Resolution |
|---|---|---|---|
| **I-1** ✅ | Migration number 0011 is free — `ls` confirms 0001–0010 present, 0011 unallocated | n/a | Use `0011_match_evaluations.sql` throughout |
| **I-2** ✅ | `matches.tournament_id` exists in 0002_tables.sql (confirmed: `tournament_id uuid not null references public.tournaments(id)`) | n/a | Two-hop RLS chain `eval → match → tournament → user_id` is valid |
| **I-3** ✅ | FK target `public.users(id)` confirmed from 0002 + 0010 patterns (NOT `auth.users(id)`) | n/a | All DDL in spec uses `public.users(id)` |
| **I-4** ✅ | Idempotent enum syntax from 0010 line 17: `do $$ begin create type ... exception when duplicate_object then null; end $$;` | n/a | `match_eval_result` enum creation mirrors this exactly |
| **I-5** ✅ | `_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True)` at `models/api.py:38` | n/a | All new Create/Update/Response models get `model_config = _CAMEL` |
| **I-6** 🔴 | **Brief said "mount in `main.py`" — WRONG.** `routes/__init__.py` exposes a `routers = [...]` list; `main.py` iterates it. Adding to `main.py` directly would bypass this pattern. | Corrected | Engineering must add new router to **`routes/__init__.py`** `routers` list |
| **I-7** ✅ | `opponent_label` text column preserved — confirmed in 0005 + 0010 DDL comments | n/a | Does not need touching; eval schema is orthogonal |
| **I-8** ✅ | `ScheduleStripView` chips only call `selectedMatchId` on tap — no existing drill-in path | n/a | `MatchDetailView` access point must be added in `TournamentDashboardView`, not in `ScheduleStripView` |
| **I-9** ✅ | `MatchCreateView.swift` already has `opponentPlayerId`, `showPlayerSearch`, `availablePlayers`, `playerSearchText` from prior delegate. No opponent picker rework needed. | n/a | iOS task list updated to reflect this (spec §G iOS item 17 dropped) |
| **I-10** ⚠️ | `Plan` response model does NOT carry `roundLabel`/`opponentLabel`. Strip uses `"Match N"` fallback. `MatchDetailView` needs a design decision for match metadata. | Design call | Spec §E.2 explicitly addresses: `MatchDetailView` receives `plan: Plan` + optional `matchId: UUID`; round/opponent display falls back to `"Match N"` for MVP. Full match-label passthrough flagged as `OQ-EVAL-UX-2`. |

---

## §A — Research Findings: MVP Post-Match Eval Template

### §A.1 — Template research basis

Common junior-tennis coaching practice draws from three frameworks:
1. **USTA junior coaching resources** — four pillars: Mental, Physical, Tactical, Emotional self-rating
2. **Academy debrief sheets** — 1-5 Likert scales for Effort, Focus, Strategy execution, Composure
3. **Parent-facing tournament journals** — free-text: "3 things that went well", "3 to work on", "turning points", "opponent notes"

### §A.2 — Locked MVP field set (8 fields, ~2 min to complete)

| Field | DB type | Required | Limit | Notes |
|---|---|---|---|---|
| `result` | `match_eval_result` enum | **Yes** | — | won / lost / withdrew / retired |
| `score_text` | `text` | No | 80 chars | "6-4, 3-6, 10-7" |
| `effort_rating` | `smallint` | No | 1–5 CHECK | Physical effort self-rating |
| `focus_rating` | `smallint` | No | 1–5 CHECK | Mental focus self-rating |
| `went_well` | `text[]` | No | 5 items × 200 chars | "3 things that went well" format |
| `to_improve` | `text[]` | No | 5 items × 200 chars | Constructive — "to work on", NOT "failures" |
| `opponent_observations` | `text` | No | 500 chars | Feeds auto-player-note loop (§D) |
| `key_moments` | `text` | No | 500 chars | Turning points, clutch moments |

### §A.3 — Justification for field set

**Why 8 fields and not more?** A 9-year-old's parent, standing in a 100°F parking lot with a tired child, will complete at most 2 minutes of tapping. Eight fields with 6 optional gives a realistic completion rate. Adding Mental, Physical, Tactical, Composure (4 more Likert scales) would push form completion time to 4-5 minutes, reducing fill rates sharply. `OQ-EVAL-1` tracks this for refinement.

**Why `text[]` for went_well/to_improve?** Dynamic list editors (add row / remove row) on mobile feel natural for bullet-style entries. The 5-item cap prevents form abuse. Normalization to a child table adds join complexity for marginal future value at MVP scale. `OQ-EVAL-2` flags for post-MVP review.

**Why no time lock on eval edits?** Post-match evaluations are *journaling*. A parent may add observations hours later when they review video, or correct a score they misremembered. Contrast with `player_notes` (24h lock enforces scouting-record integrity — OQ-SCOUT-API-2). The eval's 1:1 relationship with a match (UNIQUE constraint) means any edit simply updates the single authoritative record. `US-EVAL-4` captures this explicitly.

**User's "what you did not do bad" phrasing** → rendered in UI as "What to Improve" — constructive, coach-voice, appropriate for a young athlete.

---

## §B — Data Model

### §B.1 — Migration: `0011_match_evaluations.sql`

> **Verified: 0011 is the next free migration slot.** `ls db/supabase/migrations/` → 0001–0010 present.

```sql
-- =============================================================================
-- PlayFuel Migration 0011: Post-Match Evaluations
-- =============================================================================
-- Prerequisites: 0001–0010 must be applied first.
-- Idempotent: all statements use IF NOT EXISTS / DO $$ guards.
--
-- Creates:
--   public.match_evaluations — per-match structured post-match write-up
--   match_eval_result        — enum for match outcome
-- RLS:
--   4 new policies (1 per CRUD operation) + ALTER TABLE enable RLS
--
-- Privacy: opponent_observations flows under PLAYER_SCOUTING_V1.md §A /
--   PRIVACY_V1.md §13 "Notes about other minors" posture — same as player_notes.
-- FK target: public.users(id) — mirrors 0002, 0010 pattern.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enum: match_eval_result
-- Verified no collision with 0001 enums:
--   scenario_kind, gap_status, schedule_confidence, food_bucket,
--   pickup_bucket, weather_condition, player_note_source — none clash.
-- ---------------------------------------------------------------------------
do $$ begin
  create type match_eval_result as enum ('won', 'lost', 'withdrew', 'retired');
exception when duplicate_object then null;
end $$;


-- ===========================================================================
-- TABLE: match_evaluations
-- ===========================================================================
-- One row per match (UNIQUE on match_id). PATCH overwrites — no version history.
-- went_well / to_improve are text[] capped at 5 items via application layer;
--   no DB array length constraint in Postgres standard DDL — API enforces 5-item cap.
-- opponent_observations feeds the auto-player-note loop (services/post_match_sync.py).
-- user_id denormalised for direct RLS check (avoids extra join on every row read).
-- ---------------------------------------------------------------------------
create table if not exists public.match_evaluations (
  id                      uuid primary key default gen_random_uuid(),
  match_id                uuid not null unique references public.matches (id)
                            on delete cascade,
  user_id                 uuid not null references public.users (id)
                            on delete cascade,
  result                  match_eval_result not null,
  score_text              text check (char_length(score_text) <= 80),
  effort_rating           smallint check (effort_rating between 1 and 5),
  focus_rating            smallint check (focus_rating between 1 and 5),
  went_well               text[] not null default array[]::text[],
  to_improve              text[] not null default array[]::text[],
  opponent_observations   text check (char_length(opponent_observations) <= 500),
  key_moments             text check (char_length(key_moments) <= 500),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

comment on column public.match_evaluations.opponent_observations is
  'Parent observations about the opponent; ≤500 chars. '
  'Auto-synced to player_notes with source=post_match when opponent_player_id is set on match. '
  'Sanitised before LLM use via services/scouting.py. See POST_MATCH_EVAL_V1.md §D.';

comment on column public.match_evaluations.went_well is
  'Free-text bullet list of positives; up to 5 items (enforced at API layer). '
  'Individual item limit: 200 chars (enforced at API layer via Pydantic).';

comment on column public.match_evaluations.to_improve is
  'Free-text bullet list of growth areas; up to 5 items (enforced at API layer). '
  'Labelled "What to Improve" in UI — constructive framing for young athletes.';

create index if not exists match_evaluations_match_id_idx on public.match_evaluations (match_id);
create index if not exists match_evaluations_user_id_idx  on public.match_evaluations (user_id);

drop trigger if exists set_match_evaluations_updated_at on public.match_evaluations;
create trigger set_match_evaluations_updated_at
  before update on public.match_evaluations
  for each row execute function set_updated_at();


-- ===========================================================================
-- RLS: match_evaluations
-- ===========================================================================
-- Simple user_id predicate for SELECT/UPDATE/DELETE (user_id is denormalised).
-- INSERT / UPDATE also chain-check through match → tournament for cross-user
--   match_id injection prevention (a user can't evaluate a match they don't own
--   even if they know the match UUID).
-- Pattern mirrors match_scenarios from 0003_rls.sql.
-- ===========================================================================
alter table public.match_evaluations enable row level security;

create policy "match_evaluations_select_own"
  on public.match_evaluations
  for select
  using ((select auth.uid()) = user_id);

create policy "match_evaluations_insert_own"
  on public.match_evaluations
  for insert
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.matches m
      join public.tournaments t on m.tournament_id = t.id
      where m.id = match_evaluations.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_evaluations_update_own"
  on public.match_evaluations
  for update
  using  ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.matches m
      join public.tournaments t on m.tournament_id = t.id
      where m.id = match_evaluations.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_evaluations_delete_own"
  on public.match_evaluations
  for delete
  using ((select auth.uid()) = user_id);
```

### §B.2 — `text[]` vs child table rationale

`text[]` is chosen for MVP. Rationale:
- **No FK joins at read time** — a single SELECT returns the complete evaluation
- **iOS mapping is trivial** — `[String]` round-trips to Postgres `text[]` cleanly
- **5-item cap is a product constraint** — enforced at the API layer (Pydantic max-length list validator), not in DB DDL
- **Normalization deferred** — flagged as `OQ-EVAL-2` for future analytical use cases (e.g. cross-tournament "things that went well" trend)

### §B.3 — Cascade chain

```
auth.users (DELETE)
  └── public.users               [CASCADE]
        └── public.matches       [CASCADE from tournaments]
              └── public.match_evaluations  [CASCADE]   ← new
```

Separately:
```
public.match_evaluations.match_id references public.matches(id) ON DELETE CASCADE
  — deleting a match removes its evaluation.
```

The auto-created `player_notes` row (from `opponent_observations`) has its own cascade:
- `player_notes.match_id` is SET NULL on match delete (note survives; FK link cleared) — this is the existing 0010 behaviour.

---

## §C — API Surface

### §C.1 — Router file

**NEW `routes/match_evaluations.py`** — nested under `/v1/matches/{mid}/evaluation`:

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/v1/matches/{mid}/evaluation` | 200 / 404 | Fetch the evaluation; 404 if not yet created |
| POST | `/v1/matches/{mid}/evaluation` | 201 / 200 | Upsert — 201 on create, 200 on update (UNIQUE constraint) |
| PATCH | `/v1/matches/{mid}/evaluation` | 200 | Partial update of any field |
| DELETE | `/v1/matches/{mid}/evaluation` | 204 | Delete the evaluation |

Mount: **add to `routes/__init__.py` `routers = [...]` list** (I-6 correction). Pattern example: add `from playfuel_api.routes.match_evaluations import router as match_evaluations_router` and include it in the list. Do NOT edit `main.py` directly — it iterates `routes.routers`.

### §C.2 — Pydantic models (all in `models/api.py`)

**ALL new models MUST have `model_config = _CAMEL`** (BD lesson from player-scouting delegate — BD caught that 4 request models were missing this; iOS sends `displayName`, `effortRating` etc. in camelCase — without `_CAMEL` every POST/PATCH returns 422).

```python
class MatchEvalResult(StrEnum):
    """Mirror of match_eval_result Postgres enum. In models/enums.py."""
    won = "won"
    lost = "lost"
    withdrew = "withdrew"
    retired = "retired"

class MatchEvalCreate(BaseModel):
    """POST /v1/matches/{mid}/evaluation request body."""
    model_config = _CAMEL
    result: MatchEvalResult
    score_text: Optional[str] = Field(default=None, max_length=80)
    effort_rating: Optional[int] = Field(default=None, ge=1, le=5)
    focus_rating: Optional[int] = Field(default=None, ge=1, le=5)
    went_well: list[str] = Field(default_factory=list,
        description="Up to 5 items, 200 chars each")
    to_improve: list[str] = Field(default_factory=list,
        description="Up to 5 items, 200 chars each")
    opponent_observations: Optional[str] = Field(default=None, max_length=500)
    key_moments: Optional[str] = Field(default=None, max_length=500)

class MatchEvalUpdate(BaseModel):
    """PATCH /v1/matches/{mid}/evaluation request body. All fields optional."""
    model_config = _CAMEL
    result: Optional[MatchEvalResult] = None
    score_text: Optional[str] = Field(default=None, max_length=80)
    effort_rating: Optional[int] = Field(default=None, ge=1, le=5)
    focus_rating: Optional[int] = Field(default=None, ge=1, le=5)
    went_well: Optional[list[str]] = None
    to_improve: Optional[list[str]] = None
    opponent_observations: Optional[str] = Field(default=None, max_length=500)
    key_moments: Optional[str] = Field(default=None, max_length=500)

class MatchEvaluation(BaseModel):
    """API response model — GET / POST / PATCH."""
    model_config = _CAMEL
    id: UUID
    match_id: UUID
    user_id: UUID
    result: MatchEvalResult
    score_text: Optional[str] = None
    effort_rating: Optional[int] = None
    focus_rating: Optional[int] = None
    went_well: list[str] = []
    to_improve: list[str] = []
    opponent_observations: Optional[str] = None
    key_moments: Optional[str] = None
    created_at: datetime
    updated_at: datetime
```

Also add to `models/db.py`:
```python
class MatchEvaluationRow(BaseModel):
    id: UUID
    match_id: UUID
    user_id: UUID
    result: str
    score_text: Optional[str] = None
    effort_rating: Optional[int] = None
    focus_rating: Optional[int] = None
    went_well: list[str] = []
    to_improve: list[str] = []
    opponent_observations: Optional[str] = None
    key_moments: Optional[str] = None
    created_at: datetime
    updated_at: datetime
```

### §C.3 — Upsert strategy on POST

POST `/v1/matches/{mid}/evaluation` acts as an upsert:
- Attempt `INSERT INTO match_evaluations (...) VALUES (...) ON CONFLICT (match_id) DO UPDATE SET ...`
- Alternatively: `SELECT` existing → if row exists, `UPDATE`; if not, `INSERT`
- Return 201 on creation, 200 on update (consistent with the player scouting pattern)

The UNIQUE constraint on `match_id` is the DB-level idempotency guarantee.

### §C.4 — Validation: item-level constraints on went_well / to_improve

The Pydantic `MatchEvalCreate` and `MatchEvalUpdate` models must validate each item in the list:
```python
@field_validator("went_well", "to_improve", mode="before")
@classmethod
def _validate_items(cls, v):
    if v is None:
        return []
    if len(v) > 5:
        raise ValueError("Maximum 5 items allowed")
    for item in v:
        if len(item) > 200:
            raise ValueError(f"Item exceeds 200-character limit: {item[:20]}...")
    return v
```

---

## §D — Auto-Create Player Note Loop (Closure with PLAYER_SCOUTING_V1)

### §D.1 — When to fire

After a `match_evaluation` is **created or updated** AND:
1. `opponent_observations` is non-empty (after `.strip()`)
2. The match has `opponent_player_id IS NOT NULL`

Otherwise: skip silently. No error raised if conditions aren't met.

### §D.2 — Idempotency rule (LOCKED)

An existing `player_note` with the **same `match_id` AND `source = 'post_match'`** is **updated** (not duplicated). Re-saving the eval does not grow the player_notes table.

Implementation: `services/post_match_sync.py::sync_player_note_from_eval(eval_row, match_row, client)`:

```python
# Pseudocode
existing = client.table("player_notes")
    .select("id")
    .eq("player_id", str(match_row.opponent_player_id))
    .eq("match_id", str(eval_row.match_id))
    .eq("source", "post_match")
    .limit(1)
    .execute()

if existing.data:
    # UPDATE existing note
    client.table("player_notes")
        .update({"body": eval_row.opponent_observations})
        .eq("id", existing.data[0]["id"])
        .execute()
else:
    # INSERT new note
    client.table("player_notes").insert({
        "player_id": str(match_row.opponent_player_id),
        "user_id": str(eval_row.user_id),
        "source": "post_match",
        "body": eval_row.opponent_observations,
        "match_id": str(eval_row.match_id),
    }).execute()
```

`sync_player_note_from_eval` is called from the POST and PATCH endpoints in `routes/match_evaluations.py` **after** the eval row is persisted.

### §D.3 — Sanitization design (LOCKED)

**Do NOT sanitize `opponent_observations` before persisting to `match_evaluations` or `player_notes`.** The persisted note is the parent's authentic words — sanitization is for LLM input, not for storage.

Sanitization fires **at plan-generation time** via the existing pipeline:
```
routes/plans.py → fetch_opponent_notes_for_match() → scouting.sanitize_note_for_llm()
```

The auto-created `player_note` with `source='post_match'` flows through the same pipeline as all other notes. No new code needed.

### §D.4 — Edge cases

| Condition | Behaviour |
|---|---|
| `match.opponent_player_id` is NULL | Skip: no player to link to |
| `opponent_observations` is empty/whitespace | Skip: nothing to persist |
| Player is deleted before eval is edited | `player_notes.match_id` was SET NULL on match delete — but if the player is deleted directly, the note cascades with it. The eval persists (keyed on `match_id`, not `player_id`). No player_note exists to update; a new one will be created on the next edit if the parent re-links an opponent. |
| `sync_player_note_from_eval` raises an exception | Route logs the error but returns 200/201 for the eval itself — the sync failure is not surfaced to the parent. The eval write is the primary operation. Flag as `OQ-EVAL-3`. |

---

## §E — UX Placement & Screen Specs

### §E.1 — Match detail access path (LOCKED: Option b)

**The schedule strip stays a quick switcher.** Tapping a chip continues to focus the dashboard (current behaviour). A "Match details" button/link appears **below the strip** in `TournamentDashboardView`, anchored to the currently-selected match.

**Justification:** Option (b) is the least disruptive — no navigation stack changes, no new back-button affordance needed on the dashboard. The strip remains the fast, horizontal switcher it was designed to be. The "Match details" row surfaces below it when meaningful (i.e., when a match is selected), giving deliberate rather than accidental navigation. The user's phrasing was "you go back and look at it" — this implies intent, not accidental tap. A link rather than auto-drill is the right affordance.

**Placement in `TournamentDashboardView`:**
```
[Header Bubbles]
[Schedule Strip — chips]
[↓ "View Match Details" button for selectedMatch]  ← NEW
[EnvelopeContent (scenario cards, scenarios, etc.)]
```

The "View Match Details" button/row should be a `NavigationLink` or `.sheet` push to `MatchDetailView`. Use `.sheet` for MVP simplicity (consistent with ProfileMenuSheet / SettingsView / DashboardView pattern). `.medium` + `.large` detents, drag indicator.

> ⚠️ **Engineering note:** `ScheduleStripView.swift` itself does NOT need to change — `onAddMatch` stays as-is. The new link goes in the parent view (`TournamentDashboardView.swift`), not in `ScheduleStripView.swift`.

### §E.2 — MatchDetailView structure

```
NavigationStack (or plain View in sheet)
├── Header (VStack)
│   ├── "Match N" or roundLabel if available (title)
│   ├── Scheduled time (subtitle)
│   ├── Opponent label (if available, else "—")
│   └── Court label (if available, else "—")
├── "Post-Match Write-Up" section (VStack)
│   ├── [if eval exists] PostMatchEvaluationView (read-only cards)
│   │   └── Edit button → PostMatchEvaluationForm (pre-filled)
│   └── [if eval not yet created] CTA card
│       ├── "No write-up yet"
│       └── Button "Add Post-Match Write-Up" → PostMatchEvaluationForm
└── Done toolbar button (dismisses sheet)
```

**Match metadata in MVP:** `MatchDetailView` receives a `plan: Plan` object (which has `matchId`, `scheduledStart`, `matchType`, `scenarioPlans`). `roundLabel` and `opponentLabel` are NOT on `Plan` today (see I-10). For MVP, display "Match N" (same as the strip) and leave `opponentLabel` as "—" unless a future change threads it through. Flag as `OQ-EVAL-UX-2` — the clean solution is to include `roundLabel`/`opponentLabel` in the `Plan` response.

### §E.3 — PostMatchEvaluationForm

Form fields in order:

| Field | Control | Helper text |
|---|---|---|
| Result | Segmented Picker: Won / Lost / Withdrew / Retired | (required) |
| Score | TextField, placeholder "e.g. 6-4, 3-6, 10-7" | (optional) |
| Effort | HStack of 5 tappable stars or 1-5 segmented picker | 1 = low, 5 = max |
| Focus | Same as Effort | 1 = distracted, 5 = locked in |
| What Went Well | Dynamic bullet editor (add row / remove row, max 5) | placeholder "e.g. First-serve percentage" |
| What to Improve | Dynamic bullet editor (add row / remove row, max 5) | placeholder "e.g. Net approach timing" |
| Opponent Observations | TextEditor, char count ≤500 | **VERBATIM:** *"These notes will be added to your scouting log for this opponent."* |
| Key Moments | TextEditor, char count ≤500 | placeholder "e.g. Saved a break point at 5-4" |

**Save button:** disabled until `result` is selected (only required field). Saves via `Repository.saveMatchEvaluation(...)`. On success: dismiss form → MatchDetailView refreshes to show the read-only card.

**Cancel button:** dismisses form, no save, no confirmation alert needed (no destructive action if unsaved).

### §E.4 — PostMatchEvaluationView (read-only)

Structured always-expanded cards (no accordion/expander for MVP — "bunch of information you can click into" is satisfied by the button on the match itself):

```
Card: Result + Score
   "WON — 6-4, 3-6, 10-7"

Card: Ratings
   Effort ★★★★☆
   Focus  ★★★☆☆

Card: What Went Well
   • First serve consistency
   • Stayed calm in tiebreak

Card: What to Improve
   • Net approach positioning

Card: Opponent Observations
   "Aggressive cross-court backhand..."

Card: Key Moments
   "Saved 3 break points at 4-4..."
```

Top-right "Edit" button → re-opens `PostMatchEvaluationForm` pre-filled with existing data.

Cards with no content (all items empty / rating nil) are **omitted** — no empty "Opponent Observations" card if that field is blank.

---

## §F — User Stories

See appended entries in `USER_STORIES.md` (US-EVAL-1..4).

---

## §G — Engineering Hand-Off (numbered, copy-paste ready)

### Backend

1. **NEW `db/supabase/migrations/0011_match_evaluations.sql`** — `match_eval_result` enum (idempotent DO block), `match_evaluations` table, 4 RLS policies (SELECT/INSERT/UPDATE/DELETE), trigger. Idempotent throughout. FK to `public.users(id)`.

2. **EDIT `db/supabase/migrations/README.md`** — add migration 0011 row to the table.

3. **EDIT `apps/api/src/playfuel_api/models/db.py`** — add `MatchEvaluationRow`.

4. **EDIT `apps/api/src/playfuel_api/models/enums.py`** — add `MatchEvalResult(StrEnum)` mirroring the Postgres enum byte-identically: `won`, `lost`, `withdrew`, `retired`.

5. **EDIT `apps/api/src/playfuel_api/models/api.py`** — add `MatchEvalCreate`, `MatchEvalUpdate`, `MatchEvaluation`, `MatchEvalResult` (re-exported). ALL with `model_config = _CAMEL`. Add `@field_validator` for `went_well` and `to_improve` (max 5 items × 200 chars each).

6. **NEW `apps/api/src/playfuel_api/routes/match_evaluations.py`** — 4 endpoints (GET/POST/PATCH/DELETE at `/v1/matches/{mid}/evaluation`). POST acts as upsert (201 on create, 200 on update). RLS chain-check on INSERT ownership in `with check` clause (DB side, confirmed above).

7. **EDIT `apps/api/src/playfuel_api/routes/__init__.py`** — add `from playfuel_api.routes.match_evaluations import router as match_evaluations_router` to the import block and add it to the `routers = [...]` list. **Do NOT edit `main.py`** — it iterates `routes.routers`.

8. **NEW `apps/api/src/playfuel_api/services/post_match_sync.py`** — `sync_player_note_from_eval(eval_row, match_row, client)`: idempotent upsert keyed on `(player_id, match_id, source='post_match')`. Called from POST + PATCH evaluation endpoints.

9. **EDIT `apps/api/src/playfuel_api/routes/match_evaluations.py`** — POST + PATCH call `sync_player_note_from_eval` after persisting the eval. The match row (`matches.opponent_player_id`) must be fetched within the endpoint to supply `match_row` to the sync function.

10. **NEW `apps/api/src/playfuel_api/tests/test_match_evaluations_routes.py`** — ≥15 named tests:
    - create with all fields → 201, returned model matches input
    - create with result-only (minimal) → 201
    - update via PATCH → 200, fields updated
    - re-POST same match → 200 (upsert, not 409)
    - GET after create → 200, body matches
    - GET before create → 404
    - DELETE → 204; subsequent GET → 404
    - effort_rating out of 1-5 range → 422
    - score_text > 80 chars → 422
    - went_well > 5 items → 422
    - opponent_observations > 500 chars → 422
    - RLS isolation: User A creates eval on User A's match → 201; User B GET/PATCH/DELETE → 404
    - Cross-match injection: User B attempts POST with User A's match_id → 201 blocked by INSERT RLS (chain check)

11. **NEW `apps/api/src/playfuel_api/tests/test_post_match_sync.py`** — ≥8 named tests:
    - eval with opponent_observations + opponent_player_id → player_note created (source=post_match)
    - re-save same eval → note UPDATED (not duplicated)
    - eval with no opponent_player_id → no player_note created
    - eval with empty opponent_observations → no player_note created
    - eval with whitespace-only opponent_observations → no player_note created
    - player_note body reflects updated observations when eval is PATCHed
    - player deleted mid-eval → eval persists, player_note creation skipped
    - note body length ≤ 500 chars (source data is ≤500; no truncation needed before storage)

### iOS

12. **NEW `apps/ios/PlayFuel/Sources/PlayFuel/Models/MatchEvaluation.swift`** — struct with all 8 fields (matching `MatchEvaluation` API response). `Codable`, `Identifiable`, `Hashable`. Include `MatchEvalResult` enum in same file or separate `MatchEvalResult.swift`.

13. **EDIT `apps/ios/PlayFuel/Sources/PlayFuel/Networking/DTOs.swift`** — add `MatchEvaluationDTO` (Codable, snake_case keys for API decode), `MatchEvaluationCreateRequest` (Encodable). Mapper `MatchEvaluationDTO.toModel() -> MatchEvaluation`.

14. **EDIT `apps/ios/PlayFuel/Sources/PlayFuel/Networking/Repository.swift`** — add:
    ```swift
    func getMatchEvaluation(matchId: UUID) async throws -> MatchEvaluation?
    // Returns nil if 404 (not-yet-written), throws on other errors.
    
    func saveMatchEvaluation(matchId: UUID, request: MatchEvaluationCreateRequest) async throws -> MatchEvaluation
    // POSTs; returns the created/updated eval.
    
    func deleteMatchEvaluation(matchId: UUID) async throws
    // DELETEs; no return value.
    ```

15. **NEW `apps/ios/PlayFuel/Sources/PlayFuel/Views/MatchDetailView.swift`** — receives `plan: Plan`. Loads eval on `.task`. Shows header (Match N / scheduled time / opponent / court) + PostMatchEvaluationView or CTA. `Done` toolbar dismiss button. `.presentationDetents([.medium, .large])` + drag indicator.

16. **NEW `apps/ios/PlayFuel/Sources/PlayFuel/Views/Sheets/PostMatchEvaluationForm.swift`** — the input form. Receives optional `existingEval: MatchEvaluation?` (nil on create, non-nil on edit). Binds save to `Repository.saveMatchEvaluation(...)`. Includes verbatim helper text near opponent observations.

17. **NEW `apps/ios/PlayFuel/Sources/PlayFuel/Views/PostMatchEvaluationView.swift`** — read-only card display. Conditionally renders each section (skip empty). Top-right Edit button.

18. **EDIT `apps/ios/PlayFuel/Sources/PlayFuel/Views/TournamentDashboardView.swift`** — add "View Match Details" button/NavigationLink below the `ScheduleStripView`. On tap: present `MatchDetailView(plan: selectedPlan)` as a sheet. The button should be visible whenever `currentPlanEnvelope` has a selected match. *(Note: ScheduleStripView does NOT change — this goes in the parent view.)*

19. **EDIT `apps/ios/PlayFuel/Sources/PlayFuel/Data/FakeData.swift`** — add 1-2 dummy `MatchEvaluation` entries for previews. Use hex-only UUIDs (no `HIST*` or `EVAL*` prefixes — I-9 class of bug). Safety check: no §C prohibited phrases in `went_well`, `to_improve`, `opponent_observations`, or `key_moments` dummy text.

### MANDATORY

20. `cd apps/ios/PlayFuel && xcodegen generate`
21. Re-apply manual `Assets.xcassets` UUID patch (OQ-XCG-1 treadmill — 5-site `AA0000AA0000AA0000AA0001` through `AA0000AA0000AA0000AA0004`)
22. xcodebuild verification — confirm BUILD SUCCEEDED

---

## §H — Privacy & Safety

### §H.1 — Posture

**Ship with current guardrails.** The `opponent_observations` field is parent-authored content about a junior-tennis opponent (a minor) — the same posture as `player_notes.body` (PLAYER_SCOUTING_V1.md §A / PRIVACY_V1.md §13). No new ASTC category is introduced:

- `opponent_observations` → **OUC (Other User Content)** — already declared in PRIVACY_V1.md §13
- No contact-info columns in `match_evaluations` (schema minimisation enforced)
- Content flows through the same sanitization pipeline as `player_notes` when feeding the LLM
- Cascade-delete chain is complete: `public.users` → `public.matches` → `public.match_evaluations` [CASCADE]

### §H.2 — Verbatim form guardrail

The following text **must appear verbatim** in `PostMatchEvaluationForm.swift`, placed directly below the `opponent_observations` TextEditor:

> *"These notes will be added to your scouting log for this opponent."*

This is a hard-coded string. Do NOT generate or paraphrase it.

### §H.3 — PRIVACY_V1.md update

Add a one-liner to PRIVACY_V1.md §13.2 ("Scope of this section") noting that `match_evaluations.opponent_observations` flows under the same "Notes about other minors" posture already documented there. No new data inventory table row needed — it derives into the existing `player_notes` table.

---

## §I — DRAFT-flagged OQs

| ID | Question | Owner | Blocking? |
|---|---|---|---|
| **OQ-EVAL-1** | Which additional ratings to add in a future version: Mental, Physical, Tactical, Composure? USTA junior coaching frameworks use all four; MVP ships Effort + Focus only to stay under the 2-min parking-lot test. | PM / coaches | No — post-MVP |
| **OQ-EVAL-2** | `text[]` vs child `evaluation_items` table for `went_well`/`to_improve`. text[] chosen for MVP simplicity; migrate if cross-tournament analytics or search over items is needed. | Engineering | No — post-MVP |
| **OQ-EVAL-3** | `sync_player_note_from_eval` exceptions silently logged. Should the API surface a 207 partial-success or retry queue? For MVP, eval write always wins; sync failure is background. | Engineering | No |
| **OQ-EVAL-4** | Surface evals in the History Dashboard (DashboardView). Currently the calendar shows tournament entries from `FakeHistoryData`; real DB query post-tournament could aggregate eval data (win/loss/effort trends). | PM / FE | No — post-MVP |
| **OQ-EVAL-LLM-1** | Should past-match evals feed the next-match plan's LLM input directly? Currently no — only via the player_notes loop. Future: weight `post_match` source notes higher in `fetch_opponent_notes_for_match`. | AI Agent | No — OQ-SCOUT-LLM-1 milestone |
| **OQ-EVAL-UX-1** | Push notification / in-app reminder to fill eval after match completes. Defer — push notifications are explicitly out of MVP scope. | PM | No |
| **OQ-EVAL-UX-2** | `Plan` response doesn't carry `roundLabel`/`opponentLabel`. MatchDetailView falls back to `"Match N"` today. Fix: add these fields to the `Plan` response (API + iOS DTOs). Clean, small change. | Engineering | No — but worth doing before demo recording |

---

## §J — Decisions Table

| # | Decision | Value | Rationale |
|---|---|---|---|
| D-1 | Migration number | `0011` | `ls migrations/` verified; 0010 is last |
| D-2 | FK target | `public.users(id)` | Mirrors 0002, 0010 pattern |
| D-3 | Field count | 8 | 2-min parking-lot test; 6 optional |
| D-4 | Array fields | `text[]` | MVP simplicity; normalize post-MVP |
| D-5 | Edit window | None (any time) | Journaling vs. scouting record |
| D-6 | UX access path | Option (b) — link below strip | Least disruptive; deliberate navigation |
| D-7 | Auto-note idempotency key | `(player_id, match_id, source='post_match')` | Prevents duplicate notes on re-save |
| D-8 | Sanitization in storage | No | Sanitize at LLM input time only |
| D-9 | Privacy posture | Ship with guardrails | Same posture as PRIVACY_V1.md §13 |
| D-10 | Router mount | `routes/__init__.py` routers list | Matches existing project pattern (I-6 catch) |
