# PlayFuel — Player Scouting & Notes (v1)

> **Status:** v1 spec · **Authority:** Product Manager · **Last updated:** 2026-04-28
> **Sources of truth verified before scribing:**
> - `db/supabase/migrations/0001–0009_*.sql` — read in full (all 9 files)
> - `apps/api/src/playfuel_api/models/api.py` — `PlanExplanationInput`, `MatchInput`, `MatchOut` shapes confirmed
> - `apps/api/src/playfuel_api/services/llm.py` — `TemplateProvider._build_summary` confirmed
> - `apps/api/src/playfuel_api/services/llm_safety.py` — `validate_explanation` confirmed
> - `.pi/multi-team/expertise/PRIVACY_V1.md` — data inventory + COPPA section confirmed
> - `.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md §C` — prohibited-phrase list confirmed
> - `.pi/multi-team/expertise/USER_STORIES.md` — US-* numbering confirmed
> - `apps/ios/PlayFuel/Sources/PlayFuel/Views/MatchCreateView.swift` — opponent field confirmed
> - `apps/ios/PlayFuel/Sources/PlayFuel/Views/ProfileMenuSheet.swift` — 2-row structure confirmed

---

## §A — Privacy & COPPA

> **Resolve before data model.** User wants to store notes about junior-tennis opponents — children. This is a new PII surface.

### §A.1 — Data minimisation principle (LOCKED)

The `players` table stores **only** court-observable information plus a display name. Schema has **no columns** for:
- Email address
- Phone number
- Home address
- Photos or avatar
- Physical descriptions beyond playing style
- Social media handles

This is enforced at the **schema level** (no columns, no free-form blobs with column names implying personal contact data) AND at the **UX level** (helper text on every note-entry form, see §E.5).

Character limit: `player_notes.body` is capped at 2,000 characters by a `CHECK (char_length(body) <= 2000)` constraint. Enough for meaningful scouting notes; not enough to paste contact details.

### §A.2 — Note text UX guardrail (LOCKED, verbatim required)

The following text **must appear verbatim** on `AddPlayerNoteSheet`, below the body `TextEditor`:

> *"Notes are private to your account. Don't include personal contact info, photos, or anything not directly observable on court."*

This is a hard-coded string. Do NOT generate or paraphrase it.

### §A.3 — LLM paraphrase-only rule (LOCKED)

When opponent notes feed into `PlanExplanationInput.opponent_notes`:
- The TemplateProvider conservative acknowledgment (§D.4) **never quotes note body text** — it only counts notes.
- The real-LLM prompt rule (§D.5, post-MVP) prohibits verbatim quoting.
- `validate_explanation` from `services/llm_safety.py` already scans all LLM output for §C prohibited phrases — **no new code** needed for that check. It applies unconditionally.
- Notes are sanitized (URLs/emails/phones stripped, 200-char truncation) before reaching the LLM input object (§D.3).

### §A.4 — Retention & cascade delete (LOCKED)

| Event | Effect |
|---|---|
| Player deleted by parent | CASCADE: all `player_notes` for that player deleted |
| Account deleted (auth.users DELETE) | CASCADE: `public.users` → cascade to `players` → cascade to `player_notes` |
| Match deleted | `player_notes.match_id` is SET NULL (note survives; FK link is cleared) |

No scheduled purge. `OQ-SCOUT-PRIV-2` flagged for legal retention-cap decision.

### §A.5 — Privacy posture (LOCKED)

**Ship with current guardrails.** Parent-authored opinion data about opponents is legally analogous to a coach's clipboard — it is the parent's own observation, not opponent-authored PII. The data minimisation schema (no contact fields), UX guardrail text, cascade-delete paths, and paraphrase-only LLM rule collectively provide a defensible MVP posture. Legal review is flagged as `OQ-SCOUT-PRIV-1` but is **not a build blocker** — consistent with the existing PRIVACY_V1.md posture where parent `player_profile.injury_notes` (health-adjacent minor data) ships under the same parent-provided model.

---

## §B — Data Model

> Migration: **`0010_players_and_notes.sql`**
>
> [VERIFIED — corrected from brief] **The orchestrator brief specified `0009_players_and_notes.sql`. This is WRONG.** `db/supabase/migrations/0009_plans_upsert_constraint.sql` already exists on disk (OIA-9 hotfix). The next available number is **0010**. Engineering must use `0010_players_and_notes.sql`.
>
> [VERIFIED — corrected from brief] **FK target must be `public.users(id)`, not `auth.users(id)`.** Every existing user-owned table (`player_profiles`, `tournaments`) references `public.users(id)`. The `public.users` table itself is the shadow row (`id uuid primary key references auth.users(id)`). Mirror this pattern.

### §B.1 — Migration DDL

```sql
-- =============================================================================
-- PlayFuel Migration 0010: Players and Player Notes (Scouting)
-- =============================================================================
-- Prerequisites: 0001–0009 must be applied first.
-- Idempotent: all statements use IF NOT EXISTS / IF NOT EXIST guards.
--
-- Creates:
--   public.players         — parent's roster of tracked opponents
--   public.player_notes    — append-only per-parent observation log
--   player_note_source     — enum for note provenance
-- Alters:
--   public.matches         — adds opponent_player_id FK (nullable)
-- RLS:
--   8 new policies (4 per new table) + ALTER TABLE enable RLS for both
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enum: player_note_source
-- Values verified not to collide with enums in 0001_extensions_and_enums.sql:
--   scenario_kind, gap_status, schedule_confidence, food_bucket,
--   pickup_bucket, weather_condition — none clash.
-- ---------------------------------------------------------------------------
do $$ begin
  create type player_note_source as enum ('secondhand', 'observed', 'post_match');
exception when duplicate_object then null;
end $$;


-- ===========================================================================
-- TABLE: players
-- ===========================================================================
-- Parent's roster of opponent players they have tracked or will track.
-- Data minimisation: NO email, phone, photo, home address, or physical
-- description columns — see PLAYER_SCOUTING_V1.md §A.1.
-- updated_at bumped by set_updated_at() trigger (same function as 0002).
-- FK: public.users(id) — mirrors player_profiles, tournaments pattern.
-- ---------------------------------------------------------------------------
create table if not exists public.players (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (id)
                    on delete cascade,  -- cascade: removing user removes all their scouted players
  display_name    text not null,
  club            text,        -- optional, e.g. "Dallas Tennis Academy"
  city            text,        -- optional regional context, e.g. "Plano, TX"
  notes_summary   text,        -- optional parent-curated 1-line headline; see OQ-SCOUT-DATA-1
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on column public.players.notes_summary is
  'Parent-curated 1-line headline for this player. '
  'Persisted (not derived) in v1. See OQ-SCOUT-DATA-1.';

create index if not exists players_user_id_idx on public.players (user_id);

create trigger set_players_updated_at
  before update on public.players
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: player_notes
-- ===========================================================================
-- Append-only log of observations about an opponent player.
-- source enum: 'secondhand' (heard from others), 'observed' (during a match),
--              'post_match' (reflection after playing them).
-- body is the free-form note text; capped at 2000 chars.
-- match_id is nullable FK — links the note to a specific match when known;
--   ON DELETE SET NULL so the note survives match deletion.
-- user_id is denormalised here (not just via player_id) for direct RLS checks
--   and to support simple index queries without a join.
-- ---------------------------------------------------------------------------
create table if not exists public.player_notes (
  id          uuid primary key default gen_random_uuid(),
  player_id   uuid not null references public.players (id)
                on delete cascade,  -- cascade: deleting a player removes all their notes
  user_id     uuid not null references public.users (id)
                on delete cascade,  -- cascade: deleting account removes orphaned note rows
  source      player_note_source not null,
  body        text not null check (char_length(body) <= 2000),
  match_id    uuid references public.matches (id)
                on delete set null, -- set null: note survives if the match is deleted
  created_at  timestamptz not null default now()
  -- No updated_at: notes are immutable after creation (OQ-SCOUT-API-2 note-edit window)
);

comment on column public.player_notes.source is
  'Provenance of this note. secondhand = heard from others; '
  'observed = watched during a match; post_match = after playing them.';

create index if not exists player_notes_player_id_idx on public.player_notes (player_id);
create index if not exists player_notes_user_id_idx   on public.player_notes (user_id);


-- ===========================================================================
-- TABLE: matches (additive ALTER)
-- ===========================================================================
-- Adds opponent_player_id FK referencing the new players table.
-- Nullable; backward-compat. Existing opponent_label text column stays.
-- ON DELETE SET NULL: if the scouted player is deleted, the match record
--   retains its opponent_label text but loses the player FK link.
-- ---------------------------------------------------------------------------
alter table public.matches
  add column if not exists opponent_player_id uuid
    references public.players (id) on delete set null;

comment on column public.matches.opponent_player_id is
  'Optional FK to players.id — links this match to a scouted opponent. '
  'SET NULL on player delete. Complements opponent_label (text) which stays '
  'for display fallback. See PLAYER_SCOUTING_V1.md §B.';


-- ===========================================================================
-- RLS: players
-- Ownership predicate: (select auth.uid()) = user_id
-- Mirrors player_profiles policies from 0003_rls.sql exactly.
-- ===========================================================================
alter table public.players enable row level security;

create policy "players_select_own"
  on public.players
  for select
  using ((select auth.uid()) = user_id);

create policy "players_insert_own"
  on public.players
  for insert
  with check ((select auth.uid()) = user_id);

create policy "players_update_own"
  on public.players
  for update
  using  ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "players_delete_own"
  on public.players
  for delete
  using ((select auth.uid()) = user_id);


-- ===========================================================================
-- RLS: player_notes
-- Ownership predicate: EXISTS through players table (player_notes has user_id
-- but we chain through players to prevent cross-ownership manipulation: a note
-- must be owned by a parent who also owns the player referenced by player_id).
-- Mirrors matches/weather_snapshots one-hop pattern from 0003_rls.sql.
-- ===========================================================================
alter table public.player_notes enable row level security;

create policy "player_notes_select_own"
  on public.player_notes
  for select
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_insert_own"
  on public.player_notes
  for insert
  with check (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_update_own"
  on public.player_notes
  for update
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_delete_own"
  on public.player_notes
  for delete
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );
```

### §B.2 — Table summary

| Table | Columns | New PII? | ASTC bucket |
|---|---|---|---|
| `players` | id, user_id, display_name, club, city, notes_summary, created_at, updated_at | Yes — display_name is child-adjacent name | OUC / CI |
| `player_notes` | id, player_id, user_id, source, body, match_id, created_at | Yes — free-text observations | OUC |
| `matches.opponent_player_id` | uuid FK (additive column) | No — FK only | ID |

### §B.3 — Cross-table ownership at API layer

DB RLS scopes both `players` and `player_notes` to the caller. API layer adds a redundant explicit check on `opponent_player_id` writes: before writing `matches.opponent_player_id = X`, verify that `players.where(id=X, user_id=caller_id)` exists. Returns 404 if the player is not found or doesn't belong to the caller. DB RLS would catch it anyway — this is belt-and-suspenders. See `OQ-SCOUT-API-1`.

---

## §C — API Surface

### §C.1 — Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/players` | List caller's players, ordered `updated_at DESC` |
| POST | `/v1/players` | Create player |
| GET | `/v1/players/{id}` | Get one player (metadata only; notes via separate route) |
| PATCH | `/v1/players/{id}` | Update player metadata (display_name, club, city, notes_summary) |
| DELETE | `/v1/players/{id}` | Delete player + cascade all notes |
| GET | `/v1/players/{id}/notes` | List notes for player, newest-first |
| POST | `/v1/players/{id}/notes` | Add note |
| PATCH | `/v1/players/{id}/notes/{nid}` | Edit note — allowed within 24h of `created_at`; see `OQ-SCOUT-API-2` |
| DELETE | `/v1/players/{id}/notes/{nid}` | Delete note |

Follow existing `routes/tournaments.py` + `routes/matches.py` naming conventions. New file: `routes/players.py`.

### §C.2 — Pydantic models (new + widened)

**New models in `models/api.py`:**

```python
class PlayerCreate(BaseModel):
    display_name: str
    club: Optional[str] = None
    city: Optional[str] = None
    notes_summary: Optional[str] = None

class PlayerUpdate(BaseModel):
    display_name: Optional[str] = None
    club: Optional[str] = None
    city: Optional[str] = None
    notes_summary: Optional[str] = None

class Player(BaseModel):
    """Response model."""
    model_config = _CAMEL
    id: UUID
    user_id: UUID
    display_name: str
    club: Optional[str] = None
    city: Optional[str] = None
    notes_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class PlayerNoteCreate(BaseModel):
    source: Literal["secondhand", "observed", "post_match"]
    body: str         # ≤ 2000 chars; validated server-side + DB CHECK
    match_id: Optional[UUID] = None

class PlayerNote(BaseModel):
    """Response model."""
    model_config = _CAMEL
    id: UUID
    player_id: UUID
    user_id: UUID
    source: str
    body: str
    match_id: Optional[UUID] = None
    created_at: datetime

class OpponentNoteForLLM(BaseModel):
    """Sanitized note fragment passed to PlanExplanationInput. Never raw."""
    source: Literal["secondhand", "observed", "post_match"]
    age_days: int           # days since note created_at; newer = more relevant
    body_paraphrasable: str  # ≤ 200 chars, sanitized (see §D.3)
```

**Widened in `models/api.py`:**

```python
# MatchInput: add (additive, backward-compat)
opponent_player_id: Optional[UUID] = None

# MatchOut (if it exists as a separate response model): same addition
opponent_player_id: Optional[UUID] = None

# PlanExplanationInput: add at the end (default empty list — additive, decode-safe)
opponent_notes: list[OpponentNoteForLLM] = []
```

**New DB rows in `models/db.py`:**

```python
@dataclass
class PlayerRow:
    id: UUID
    user_id: UUID
    display_name: str
    club: Optional[str]
    city: Optional[str]
    notes_summary: Optional[str]
    created_at: datetime
    updated_at: datetime

@dataclass
class PlayerNoteRow:
    id: UUID
    player_id: UUID
    user_id: UUID
    source: str              # player_note_source enum value
    body: str
    match_id: Optional[UUID]
    created_at: datetime

# MatchRow: add field
opponent_player_id: Optional[UUID] = None
```

### §C.3 — Error handling conventions

| Condition | HTTP status | Detail |
|---|---|---|
| Player not found / wrong owner | 404 | `"Player not found"` |
| Note not found | 404 | `"Note not found"` |
| `opponent_player_id` not owned by caller | 404 | `"Player not found"` (don't leak existence) |
| Note edit after 24h window | 422 | `"Note cannot be edited after 24 hours"` |
| Body > 2000 chars | 422 | `"Note body exceeds 2000 characters"` |

---

## §D — LLM Input Widening

### §D.1 — `PlanExplanationInput` addition

```python
# Added at end of PlanExplanationInput — backward-compat (default empty list)
opponent_notes: list[OpponentNoteForLLM] = []
```

Confirmed additive: current model ends with `match_type: str = "singles"`. This new field appends cleanly; no existing field is moved or renamed.

### §D.2 — Where opponent notes are fetched

New function in new module `services/scouting.py`:

```python
async def fetch_opponent_notes_for_match(
    match_id: UUID,
    user_id: UUID,
    db: AsyncClient,  # Supabase async client, same pattern as routes/plans.py
) -> list[OpponentNoteForLLM]:
    """Fetch and sanitize opponent notes for a given match.

    1. Look up matches.opponent_player_id where matches.id = match_id.
    2. If None, return [].
    3. Fetch player_notes WHERE player_id = opponent_player_id
       AND user_id = user_id ORDER BY created_at DESC LIMIT 10.
    4. Sanitize + build OpponentNoteForLLM for each note.
    5. Return list (may be empty if player has no notes).
    """
```

Called in `routes/plans.py` `generate_plan` after `build_plan_envelope()`, before `build_explanation_input()`. Attach the resulting list to `PlanExplanationInput.opponent_notes`.

### §D.3 — Sanitization pipeline (in `services/scouting.py`)

Applied to each note's `body` before building `body_paraphrasable`:

```python
import re

def _sanitize_note_body(body: str) -> str:
    # 1. Strip URLs
    text = re.sub(r'https?://\S+', '', body)
    # 2. Strip email-like patterns
    text = re.sub(r'\S+@\S+\.\S+', '', text)
    # 3. Strip phone-like patterns
    text = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '', text)
    # 4. Truncate to 200 chars
    text = text[:200].strip()
    return text

def _is_prohibited(text: str) -> bool:
    """Return True if any §C prohibited phrase appears in text (case-insensitive)."""
    from playfuel_api.services.llm_safety import PROHIBITED_PHRASES
    lower = text.lower()
    return any(p.lower() in lower for p in PROHIBITED_PHRASES)

def build_opponent_note_for_llm(
    note: PlayerNoteRow,
    now: datetime,
) -> OpponentNoteForLLM:
    sanitized = _sanitize_note_body(note.body)
    age_days = max(0, (now - note.created_at.replace(tzinfo=timezone.utc)).days)
    if _is_prohibited(sanitized):
        sanitized = "[note redacted]"
    return OpponentNoteForLLM(
        source=note.source,
        age_days=age_days,
        body_paraphrasable=sanitized,
    )
```

Notes where `body_paraphrasable == "[note redacted]"` are **dropped** from the list passed to the LLM (do not pass redacted notes — they carry zero signal and may confuse the template).

### §D.4 — TemplateProvider conservative acknowledgment (ship now)

Edit `services/llm.py` `TemplateProvider._build_summary` to append the acknowledgment when `opponent_notes` is non-empty:

```python
@staticmethod
def _build_summary(inp: "PlanExplanationInput") -> str:
    # ... existing code unchanged ...
    summary = (
        f"{subject} at {venue} {match_desc} "
        f"scheduled to start at {time_part}. "
        f"We've prepared three scenarios—short, normal, and long—to cover "
        f"different match durations. "
        f"The normal scenario (~{friendly_duration(normal_min)}) is used as "
        f"the primary planning reference."
        f"{heat_note}"
    )
    # NEW: conservative opponent-notes acknowledgment
    notes = getattr(inp, "opponent_notes", [])
    if notes:
        n = len(notes)
        s = "s" if n != 1 else ""
        summary += (
            f" Your notes mention {n} prior observation{s} "
            f"— review the player profile for tactics."
        )
    return summary
```

**Constraint:** the appended sentence never quotes note body text. It never reveals source. It only counts notes. Real tactical paraphrase waits for a real LLM provider — see `OQ-SCOUT-LLM-1`.

### §D.5 — Real-LLM prompt rule (post-MVP, doc only — `OQ-SCOUT-LLM-1`)

When `AnthropicProvider` or `OpenAIProvider` are implemented, add to `SYSTEM_PROMPT`:

```
OPPONENT NOTES RULE (when opponent_notes is present in the plan input):
- You MAY paraphrase 1–2 actionable tactical hints in the summary section.
- NEVER quote a note verbatim.
- NEVER reveal the source ("someone said", "observed") — frame as "based on your notes".
- NEVER include any prohibited phrase from the safety guardrails.
- If the notes contain only non-tactical or personal content, ignore them entirely.
```

### §D.6 — `validate_explanation` coverage

Confirmed (read `services/llm_safety.py`): `validate_explanation` iterates over ALL text fields of `PlanExplanation` via `_all_text_fields()` — summary, safety_note, weather_note, food_note, all scenario_explanations values. **No new validation code is needed.** The §C prohibited-phrase check already applies to any opponent-note-derived content in the summary.

---

## §E — UX Placement

### §E.1 — Where "Players" lives in the IA (LOCKED)

**3rd row in `ProfileMenuSheet`** (after Settings, Dashboard). Justification: the Profile menu pattern is established and discoverable from any screen within one tap (toolbar button on both TournamentListView and TournamentDashboardView). Adding a 3rd row costs zero navigation depth and requires no app-shell rewrite. The alternative — a tab bar entry — would require restructuring the root navigation, which is out of scope.

Icon: `person.2.fill`. Foreground: `.green` (distinct from Settings blue and Dashboard indigo).

### §E.2 — PlayerListView structure

```
NavigationStack {
    List {
        // Player rows ordered by updated_at DESC
        // Each row: display_name (primary), club + city subtitle,
        //           last-note source pill (Heard/Observed/Post), last-note date
    }
    .navigationTitle("Players")
    .toolbar {
        ToolbarItem(.topBarTrailing) { Button("+") { showAddPlayer = true } }
    }
    .overlay { if players.isEmpty { EmptyStateView("Add a player to start tracking opponents") } }
}
```

### §E.3 — PlayerDetailView structure

```
ScrollView {
    // Header: display_name large title, club/city subtitle, "X notes" pill,
    //         edit/delete context menu
    Section("Notes") {
        // Reverse-chronological note list
        // Each note: source pill (Heard/Observed/Post), date, body
    }
    Button("+ Add Note") { showAddNote = true }
    // §E.7: Linked matches section — post-MVP placeholder, OQ-SCOUT-UX-1
}
```

### §E.4 — MatchCreateView opponent picker upgrade

Replace:
```swift
TextField("Opponent (e.g. Smith)", text: $opponentLabelText)
```

With: a `NavigationLink`-style search row that opens `PlayerSearchView` inline:
- Search-as-type filter over the user's `players` list
- Each result row shows `display_name` + club/city subtitle
- Bottom of the list: `"+ Add \"\(typedName)\" as new player"` inline option
- On select: populates BOTH `opponentPlayerId: UUID?` (new state var) AND `opponentLabelText` (existing state var, set to `player.display_name` for display continuity)
- On "+ Add new": opens `AddPlayerSheet` modally (just `display_name` required), on save returns the new player's ID and name, populates both fields

The `save()` function in `MatchCreateView` sends `opponentPlayerId` as the new `opponent_player_id` field and `opponentLabelText` as the existing `opponent_label` field. Both are optional; if the parent skips the picker, `opponent_player_id` is nil and `opponent_label` is nil or typed text — same behavior as today.

### §E.5 — AddPlayerNoteSheet

```
Form {
    Section(header: Text("Source"),
            footer: Text("Where did this observation come from?")) {
        Picker("Source", selection: $source) {
            Text("Heard from others").tag("secondhand")
            Text("I observed this").tag("observed")
            Text("After we played").tag("post_match")
        }
        .pickerStyle(.segmented)
    }
    Section(header: Text("Note"),
            footer: Text("\(body.count)/2000")) {
        TextEditor(text: $body)
            .frame(minHeight: 120)
    }
    Section {
        Text("Notes are private to your account. Don't include personal contact info, photos, or anything not directly observable on court.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }
}
.navigationTitle("Add Note")
```

The verbatim privacy guardrail text from §A.2 is displayed as a static `Text` in its own Section — not in a footer, not behind a disclosure — so it is always visible.

### §E.6 — AddPlayerSheet

```
Form {
    Section(footer: Text("Required")) {
        TextField("Player's name", text: $displayName)
    }
    Section(footer: Text("Optional")) {
        TextField("Club (e.g. Dallas Tennis Academy)", text: $club)
        TextField("City (e.g. Plano, TX)", text: $city)
    }
}
.navigationTitle("Add Player")
```

### §E.7 — "Linked matches" on PlayerDetailView (deferred)

A "Matches" section showing all matches where `opponent_player_id == this player` is useful context but requires a new API query (`GET /v1/players/{id}/matches`). Deferred to post-MVP. Flagged as `OQ-SCOUT-UX-1`. Reserve the section space with a "Coming soon" placeholder or simply omit for v1.

---

## §F — User Stories

> See `USER_STORIES.md` for the full Given/When/Then format. Summarised here for cross-reference.

| Story | One-liner |
|---|---|
| **US-PLAYER-1** | Parent maintains a running log of opponents with notes from before/during/after matches |
| **US-PLAYER-2** | Parent searches for an existing player when creating a match, or adds a new one inline |
| **US-PLAYER-3** | Day-of plan summary acknowledges tactical context recorded about the opponent (no verbatim quoting) |
| **US-PLAYER-4** | Notes about other children are private, never shared, no contact-info columns by design |
| **US-PLAYER-5** | Deleting a player cascades all their notes |

---

## §G — Engineering Hand-Off

> Copy-paste ready. Numbered list. Sequence matters — do not reorder §G.1–§G.3 relative to each other.

**Backend:**

1. Migration `0010_players_and_notes.sql` — `players` table + `player_notes` table + `player_note_source` enum + `matches.opponent_player_id` column. RLS policies in same file. Trigger from existing `set_updated_at()`. FK target: `public.users(id)`. See §B.1 DDL verbatim.

2. New `models/db.py` rows: `PlayerRow`, `PlayerNoteRow`. Update `MatchRow` to add `opponent_player_id: Optional[UUID] = None`.

3. New `models/api.py`: `Player`, `PlayerCreate`, `PlayerUpdate`, `PlayerNote`, `PlayerNoteCreate`, `OpponentNoteForLLM`. Widen `MatchInput` + `PlanExplanationInput` per §C.2 field additions.

4. New `routes/players.py` with 9 endpoints from §C.1. Cross-table ownership check per §B.3 + §C.3.

5. New `services/scouting.py` with `fetch_opponent_notes_for_match()` + `_sanitize_note_body()` + `build_opponent_note_for_llm()` per §D.2–§D.3.

6. EDIT `routes/plans.py` `generate_plan`: per-match call to `fetch_opponent_notes_for_match()`, attach result to `PlanExplanationInput.opponent_notes`.

7. EDIT `services/llm.py` `TemplateProvider._build_summary`: add the conservative acknowledgment block per §D.4.

8. New tests: `test_players_routes.py`, `test_player_notes_routes.py`, `test_scouting_sanitization.py`, `test_opponent_notes_in_plan.py`. Minimum 20 named tests covering: CRUD happy paths, RLS (other user can't see/edit), note body > 2000 chars returns 422, sanitization strips URL/email/phone, prohibited-phrase → `[note redacted]`, acknowledgment appends when notes > 0, acknowledgment absent when notes == 0, opponent_player_id cross-table ownership check.

**iOS:**

9. NEW `Models/Player.swift` — `Player`, `PlayerCreate`, `PlayerUpdate` (Codable, Identifiable, camelCase).

10. NEW `Models/PlayerNote.swift` — `PlayerNote`, `PlayerNoteCreate`. `PlayerNoteSource` as `String`-raw-value enum: `secondhand`, `observed`, `postMatch` (camelCase raw for display).

11. EDIT `Networking/Repository.swift` — add `listPlayers()`, `createPlayer()`, `getPlayer()`, `updatePlayer()`, `deletePlayer()`, `listPlayerNotes()`, `addPlayerNote()`, `editPlayerNote()`, `deletePlayerNote()`.

12. NEW `Views/PlayerListView.swift`.

13. NEW `Views/PlayerDetailView.swift`.

14. NEW `Views/Sheets/AddPlayerNoteSheet.swift` — per §E.5.

15. NEW `Views/Sheets/AddPlayerSheet.swift` — per §E.6.

16. EDIT `Views/MatchCreateView.swift` — opponent picker upgrade per §E.4. New `@State private var opponentPlayerId: UUID? = nil`. Existing `opponentLabelText` stays.

17. EDIT `Views/ProfileMenuSheet.swift` — add 3rd row "Players" with `person.2.fill` icon (`.green`), same Button/sheet pattern as Settings and Dashboard rows.

18. EDIT `Data/FakeData.swift` — add 3–4 dummy `Player` instances + 5–8 dummy `PlayerNote` instances for Canvas previews.

**Mandatory after all files written:**

19. `cd apps/ios/PlayFuel && xcodegen generate`

20. Re-apply `Assets.xcassets` manual UUID patch (`OQ-XCG-1` treadmill — 5-site pattern, UUIDs `AA0000AA0000AA0000AA0001`–`AA0000AA0000AA0000AA0004`).

21. `xcodebuild -project apps/ios/PlayFuel/PlayFuel.xcodeproj -scheme PlayFuel -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=latest' build`

**Acceptance:**

- Backend: all prior tests pass (291 + ~20 new) at eval harness exit 0
- Migration 0010 idempotent
- iOS: ProfileMenuSheet 3rd row "Players" opens PlayerListView; MatchCreateView opponent picker shows existing players + "Add new" option; pbxproj has all new files; BUILD SUCCEEDED
- LLM: TemplateProvider acknowledgment fires when opponent notes ≥ 1; zero when notes == 0; never quotes note body
- Privacy: PRIVACY_V1.md updated with new section + data inventory rows (see §A.5 + PRIVACY_V1 §2 update)

---

## §H — DRAFT-Flagged Open Questions

| ID | Severity | Owner | Description | Resolution path |
|---|---|---|---|---|
| **OQ-SCOUT-PRIV-1** | 🟡 | Legal | Parent-authored opinion data about other minors — is this a regulated category? Posture: it's the parent's own court observations (coach's clipboard), not the opponent's own data. No VPC obligation expected. | Legal confirmation before App Store submission |
| **OQ-SCOUT-PRIV-2** | 🟡 | Legal | Retention policy for opponent notes. Current stance: no cap (running log is the feature). Should notes auto-expire after X years? After tournament date + Y days? | Legal + PM before privacy policy is published |
| **OQ-SCOUT-API-1** | ⚪ | Engineering | Cross-table ownership check for `opponent_player_id` — API-layer assertion vs. DB trigger. Current decision: API layer (cheaper, defensible via RLS). | Engineering implementation choice |
| **OQ-SCOUT-API-2** | ⚪ | Engineering | Note edit window — PATCH allowed within 24h of `created_at`, then locked (422). Or always-editable? Or never-editable (append-only)? Current spec: 24h window. | Engineering + UX input; can ship as always-editable v1 and tighten later |
| **OQ-SCOUT-UX-1** | ⚪ | Engineering | "Linked matches" section on PlayerDetailView — post-MVP. Requires `GET /v1/players/{id}/matches` endpoint. | Phase 9+ |
| **OQ-SCOUT-LLM-1** | 🟡 | Engineering + Legal | Real Anthropic/OpenAI provider prompt rule for tactical paraphrase. Post-MVP; TemplateProvider conservative acknowledgment ships now. Legal should review the paraphrase rule before the real provider ships. | Phase 9+ when real LLM providers are wired |
| **OQ-SCOUT-DATA-1** | ⚪ | Engineering | `players.notes_summary` — persisted text vs. derived last-note body. Current decision: persisted (explicit parent-curated headline). If derived, remove column and compute in API response. | Engineering preference |

---

## §I — PM Verification Findings

Disk read performed against all source files before scribing. Corrections vs. orchestrator brief:

| # | Finding | Correction applied |
|---|---|---|
| **I-1** | Migration number conflict: `0009_plans_upsert_constraint.sql` already exists on disk. Orchestrator brief said `0009_players_and_notes.sql`. | **Corrected to `0010_players_and_notes.sql`** throughout this spec. Engineering MUST use 0010. |
| **I-2** | FK target: Orchestrator brief said `REFERENCES auth.users(id)`. Existing tables (`player_profiles`, `tournaments`) reference `public.users(id)`. The `public.users` table is the shadow row that itself FKs to `auth.users`. | **Corrected to `public.users(id)`** in §B.1 DDL and throughout. |
| **I-3** | `matches.opponent_label` — orchestrator brief said "existing column, keep it." Confirmed by reading `0005_match_labels.sql`: `ALTER TABLE public.matches ADD COLUMN IF NOT EXISTS opponent_label text`. Confirmed present. | No correction needed — brief was correct. |
| **I-4** | `player_note_source` enum name — checked against all enums in `0001_extensions_and_enums.sql` (scenario_kind, gap_status, schedule_confidence, food_bucket, pickup_bucket, weather_condition). No collision. | Confirmed safe — no correction. |
| **I-5** | `PlanExplanationInput` current fields — confirmed by reading `models/api.py`. Last field is `match_type: str = "singles"`. New `opponent_notes: list[OpponentNoteForLLM] = []` appends cleanly. | No correction needed — additive is safe. |
| **I-6** | `TemplateProvider._build_summary` target — confirmed the method name and its return type (`str`). The conservative acknowledgment must be appended inside this function. | Spec §D.4 gives the exact edit location. |
| **I-7** | `MatchCreateView` opponent field — confirmed as `@State private var opponentLabelText: String = ""` bound to `TextField`. New field `opponentPlayerId: UUID? = nil` is additive. | Spec §E.4 specifies the upgrade correctly. |
| **I-8** | `ProfileMenuSheet` — confirmed 2 rows: Settings (`gearshape.fill`, blue) + Dashboard (`square.grid.2x2.fill`, indigo). Players is the 3rd row. | Spec §E.1 + §G.17 correct. |

---

## §J — Decisions Table

| ID | Decision | Tag | Rationale |
|---|---|---|---|
| **D-SCOUT-1** | UX placement: 3rd row in ProfileMenuSheet | Derived | Consistent with established pattern; single-tap from any screen |
| **D-SCOUT-2** | FK target: `public.users(id)` not `auth.users(id)` | Derived (verified on disk) | Mirrors all existing tables; `public.users` is the shadow row |
| **D-SCOUT-3** | Migration number: 0010 | Derived (verified on disk) | 0009 already exists |
| **D-SCOUT-4** | Source enum values: `secondhand`, `observed`, `post_match` | Invented | Covers pre-match intelligence, in-match observation, post-match reflection — the 3 natural moments |
| **D-SCOUT-5** | Sanitization pipeline: strip URL + email + phone, truncate 200 chars, §C scan → redact | Derived (from §A.1 minimisation + §A.3 paraphrase rule) | Prevents contact data from reaching LLM even if parent types it |
| **D-SCOUT-6** | TemplateProvider: conservative count-only acknowledgment now; tactical paraphrase post-MVP | Worth a look | Delivers value signal immediately without legal risk of paraphrasing minor's observed behaviors |
| **D-SCOUT-7** | Note edit window: 24h then locked | Invented | Prevents retroactive rewriting of scouting records while allowing typo fixes; flag OQ-SCOUT-API-2 if UX pushes back |
| **D-SCOUT-8** | Privacy posture: ship with current guardrails | Derived (consistent with PRIVACY_V1 parent-provided model) | Parent's own observations; not opponent-authored data |

---

*End of PLAYER_SCOUTING_V1.md*
