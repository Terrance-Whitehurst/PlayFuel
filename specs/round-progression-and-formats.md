# Round Progression + Score Format — Feature Spec

> **Version:** 1.0.0
> **Status:** READY — Engineering can execute
> **Author:** Planning (Product Manager delegate)
> **Date:** 2026-05-04
> **Authority:** Planning Lead (scoping) → Engineering Lead (implementation) → Validation Lead (sign-off)
>
> Sources read before scribing:
> `db/supabase/migrations/` (0001–0017), `apps/api/src/playfuel_api/routes/matches.py`,
> `apps/api/src/playfuel_api/rules/constants.py`, `apps/ios/PlayFuel/Sources/PlayFuel/Models/Match.swift`,
> `apps/ios/PlayFuel/Sources/PlayFuel/Models/RoundVocab.swift`,
> `apps/ios/PlayFuel/Sources/PlayFuel/Views/MatchCreateView.swift`,
> `apps/ios/PlayFuel/Sources/PlayFuel/Views/TournamentCreateView.swift`,
> `apps/api/src/playfuel_api/tests/test_draw_size_and_round.py`,
> `.pi/multi-team/expertise/DOUBLES_SPEC_V1.md §B`

---

## §A — User Request

Verbatim from the user:

> "I also want the app to be smart about the rounds. Let's say you pick a tournament that's
> around a 64, and for the first round match, the first match you can pick can only be your
> first round. If you have a match for that round, for round 64, for the first round, you can
> only pick that for the match.
>
> For the second round, it is 32, so for the next match you put it in, the only option you can
> pick is 32, because in the next match you can play. You can't skip from that to the quarters,
> right? From the first rounds of the quarters, and also now that I think about it, do the same
> for doubles. Allow doubles to be able to pick two out of three sets or the eight-game pro set,
> and then restrict things based on those rounds for whichever matches and stuff, yeah, scores
> and rounds and tournaments."

**PM read of intent:** Two distinct features:
1. **Round progression** — constrain the round picker so each new match is exactly one
   round deeper than the previous in the same stream (singles/doubles independently).
2. **Score format** — unified per-match format field covering both singles and doubles
   (so singles can also pick pro-set). User confirmed doubles already has two-out-of-three
   and 8-game pro set as the options.

"Scores and rounds and tournaments" at the end is interpreted as **score format options**
(which format the match is played), NOT as game-by-game score capture. Score capture is
deferred — see §H.

---

## §I — PM Verification Findings (12 confirmed, all consequential)

These were caught by disk-reading before scribing. The orchestrator brief pre-baked decisions
based on an assumed state of the codebase that differs materially from reality. Every finding
below updates the spec to match actual disk state.

| # | Finding | Impact on Brief |
|---|---------|-----------------|
| **V-1** | `draw_size` column ALREADY EXISTS on `tournaments` (migration 0016, `NOT NULL DEFAULT 32 CHECK (32,64,128,256)`). | Drop "new draw_size on tournament" from §J Engineering scope. No migration needed for this field. |
| **V-2** | `matches.round` ALREADY EXISTS (migration 0016, numeric players-alive model, `NOT NULL DEFAULT 32 CHECK VALID_ROUNDS`). | Drop "new round column" from §J. |
| **V-3** | `matches.format` IS the match-type field (0002_tables.sql). DOUBLES_SPEC_V1 §A.2 explicitly resolved "do NOT add a redundant match_type column." Drop `match_type` from brief. The API validates `format ∈ {singles, doubles}`. | Drop "new match_type column on matches" from §J. |
| **V-4** | `matches.doubles_format` ALREADY EXISTS (migration 0007, `{best_of_3, pro_set_8}`). API validates consistency with `format`. iOS MatchCreateView shows the doubles format picker when doubles is selected. | Drop "add doubles format" from §J. |
| **V-5** | `RoundVocab.swift` ALREADY EXISTS with full `roundOptions(for:)`, `label(for:)`, `abbreviation(for:)`. The brief said "new `RoundDisplay.string(for: Int) -> String`" — already there under a different name. | Drop this iOS helper from §J. |
| **V-6** | Backend already validates: `round IN VALID_ROUNDS` (Pydantic `field_validator`), `round <= draw_size` (cross-table check in `create_match`). | Drop "add round validation" from §J. |
| **V-7** | `VALID_ROUNDS`, `ROUND_LABELS`, `rounds_for_draw()` ALREADY EXISTS in `rules/constants.py`. | Drop from §J. |
| **V-8** | `SCENARIO_DURATIONS_MIN` is ALREADY a nested dict keyed by `(match_type, doubles_format)`. `RULES_CONSTANTS_VERSION = "1.1.0"` already bumped from doubles-spec work. | New entries for singles score formats use the same key pattern. Version bumps to "1.2.0" for this spec. |
| **V-9** | `draw_size` is already REQUIRED at tournament create — AC-2 test (`missing draw_size → 422`) proves it. `TournamentCreateView` already has the draw_size picker (`RoundVocab.drawSizes = [32, 64, 128, 256]`). | Drop TournamentCreateView from iOS §J scope. Already done. |
| **V-10** | `MatchCreateView` already has: `drawSize: Int` param, round picker via `RoundVocab.roundOptions(for: drawSize)`, singles/doubles type picker, doubles format picker (shown conditionally). | Only NEW additions to MatchCreateView are: (a) score_format picker for singles, (b) round progression constraint (locked display when only one option). |
| **V-11** | No `score_format` / `scoreFormat` anywhere in the codebase (iOS or backend). Confirmed: `grep -rn "score_format\|scoreFormat"` → zero results. | `score_format` is the only genuinely NEW column needed on matches. |
| **V-12** | No `RoundProgression` helper anywhere on iOS. Round picker uses `RoundVocab.roundOptions(for: drawSize)` (all valid rounds for that draw) but does NOT enforce stream-based progression (first-match must be R{draw_size}, each next match must be prev/2). | Round progression is the core missing feature — the actual user request. Spec it in full. |

---

## §B — Data Model (only new things)

### B.1 Migration 0018 — `score_format` on matches

**Next free migration: 0018** (0017 is `match_done_state.sql`, confirmed on disk).

File: `db/supabase/migrations/0018_score_format.sql`

```sql
-- 0018_score_format.sql
-- Adds score_format column to matches.
-- Covers both singles and doubles format choice in one field.
-- 'best_of_3'       → standard two-out-of-three sets (default)
-- 'pro_set_8'       → first to 8 games wins (8-game pro set)
-- 'best_of_3_super_tb' → best of 3 with match tiebreak in lieu of 3rd set (10-point)
--
-- Doubles parents already use doubles_format for format selection.
-- score_format adds the same choice for singles and provides a unified wire field.
-- The rules engine key becomes (format_str, score_format_str) for all match types.
--
-- Prerequisites: 0017_match_done_state.sql
-- Idempotent: IF NOT EXISTS guard.

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS score_format text NOT NULL DEFAULT 'best_of_3'
    CONSTRAINT chk_score_format CHECK (
      score_format IN ('best_of_3', 'pro_set_8', 'best_of_3_super_tb')
    );

COMMENT ON COLUMN public.matches.score_format IS
  'Match format: best_of_3 | pro_set_8 | best_of_3_super_tb. '
  'Covers both singles and doubles. '
  'For doubles, score_format mirrors doubles_format semantics (kept separate for back-compat). '
  'Enforced at API layer.';
```

### B.2 Relationship between `score_format` and `doubles_format`

**Why two fields?** `doubles_format` was added in migration 0007 specifically for doubles.
`score_format` is the new unified field covering singles AND doubles format. For doubles,
both fields will hold equivalent values (`best_of_3` → `doubles_format = 'best_of_3'` AND
`score_format = 'best_of_3'`). Engineering should propagate `score_format` from the same
picker that previously drove `doubles_format` for doubles matches.

**Rules-engine key change** (§D): the rules engine will use
`(match.format, match.score_format)` as the duration lookup key, replacing the prior
`(match_type, doubles_format)` pattern. Existing `doubles_format` column stays in DB for
back-compat; `score_format` is the authoritative field going forward.

### B.3 Round progression — no new columns needed

Round progression is enforced at the **API layer only** (same as the existing
`round <= draw_size` validation). No new DB columns. The progression rule is:

```
first_round(draw_size) = draw_size
next_round(prev) = prev / 2
terminal when round == 2 (Final)
```

For a new match in stream `S` (where S = `format` value, "singles" or "doubles"):
- If no matches exist in stream S → allowed round = `tournament.draw_size`
- If matches exist in stream S → allowed round = `min_round_in_S / 2`
  (where min_round = deepest existing round in that stream)
- Duplicate round in same stream → rejected with 422

**Streams are independent.** Singles progression does not constrain doubles, and vice versa.

**Backfill exception:** The parent can explicitly request a round earlier than the deepest
existing round (to back-fill history). Backfill is allowed at the iOS level via an explicit
control — not the default picker state. The API should accept any `round` that:
- `round <= draw_size` (existing validation)
- `round ∈ VALID_ROUNDS` (existing validation)
- `round NOT IN existing_rounds_for_stream` (new: no duplicates)

The "one step only" constraint is enforced by the **iOS picker** (showing only the next
valid round by default). The API enforces only the no-duplicate rule — it does NOT enforce
that the parent must follow linear progression. This gives the parent flexibility to correct
mistakes while keeping the common path smooth. See §E for UX details.

---

## §C — Rules Engine Changes

### C.1 New duration entries — `SCENARIO_DURATIONS_MIN`

Current entries:
```python
("singles", None):          {"short": 75,  "normal": 120, "long": 180}  # FROZEN v1.0.0
("doubles", "best_of_3"):   {"short": 60,  "normal": 90,  "long": 135}  # DRAFT OQ-DBL-1
("doubles", "pro_set_8"):   {"short": 45,  "normal": 70,  "long": 100}  # DRAFT OQ-DBL-1
```

New entries to add (keyed by `(match.format, match.score_format)`):
```python
# Existing key stays for back-compat (legacy matches with no score_format):
("singles", None):                  {"short": 75,  "normal": 120, "long": 180}  # FROZEN

# New score_format-aware keys:
("singles", "best_of_3"):           {"short": 75,  "normal": 120, "long": 180}  # same as None
("singles", "pro_set_8"):           {"short": 30,  "normal": 45,  "long": 65}   # [DRAFT OQ-ROUND-1]
("singles", "best_of_3_super_tb"):  {"short": 50,  "normal": 75,  "long": 115}  # [DRAFT OQ-ROUND-1]
("doubles", "best_of_3"):           {"short": 60,  "normal": 90,  "long": 135}  # DRAFT OQ-DBL-1
("doubles", "pro_set_8"):           {"short": 45,  "normal": 70,  "long": 100}  # DRAFT OQ-DBL-1
("doubles", "best_of_3_super_tb"):  {"short": 50,  "normal": 75,  "long": 110}  # [DRAFT OQ-ROUND-1]
```

**All singles + doubles super_tb values are DRAFT** — see OQ-ROUND-1. Values follow the
same derivation rationale as DOUBLES_SPEC_V1 §B.3. Validate with a USTA junior coach
before Phase 7 cutover.

**RULES_CONSTANTS_VERSION bump:** `1.1.0 → 1.2.0` (minor bump for new `SCENARIO_DURATIONS_MIN`
entries without breaking existing keys).

### C.2 Rules-engine lookup change

The lookup call site in `rules/scenarios.py` currently uses `(match_type, doubles_format)`.
Change to `(match.format, match.score_format)` with a fallback chain:
```python
key = (match.format or "singles", match.score_format)
duration = SCENARIO_DURATIONS_MIN.get(key) or SCENARIO_DURATIONS_MIN[("singles", None)]
```
This ensures legacy matches (null `score_format`) continue to work via the None fallback.

---

## §D — API Changes

### D.1 `MatchCreate` Pydantic model — add `score_format`

In `routes/matches.py`:
```python
score_format: Optional[str] = "best_of_3"  # 'best_of_3' | 'pro_set_8' | 'best_of_3_super_tb'
```
Add a `field_validator` that enforces the value is one of the three valid options when
provided.

### D.2 `MatchUpdate` Pydantic model — add `score_format`

```python
score_format: Optional[str] = None  # optional for partial update; same validator as create
```

### D.3 `MatchRow` — add `score_format`

```python
score_format: str = "best_of_3"
```

### D.4 Round progression validation in `create_match`

Add a new helper `_validate_round_progression()` called inside `create_match` after the
existing `round <= draw_size` check:

```python
def _validate_round_progression(
    tid: str,
    stream: str,         # 'singles' or 'doubles'
    new_round: int,
    client: Client,
) -> None:
    """
    Enforce:
    - No duplicate round in the same stream.
    - (Soft) The new round is the expected next round.
    Note: The API enforces only the no-duplicate rule. The iOS picker enforces
    the one-step-at-a-time constraint in the UX. The API is intentionally permissive
    on progression so parents can back-fill missing rounds.
    """
    existing = (
        client.table("matches")
        .select("round")
        .eq("tournament_id", tid)
        .eq("format", stream)
        .execute()
    )
    existing_rounds = {row["round"] for row in (existing.data or [])}
    if new_round in existing_rounds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"A {stream} match for round {new_round} already exists in this tournament. "
                f"Cannot add a duplicate round."
            ),
        )
```

Call site in `create_match`, after the date-range validation:
```python
stream = body.format or "singles"
_validate_round_progression(str(tid), stream, body.round, client)
```

**No progression-order enforcement at API:** The API only rejects duplicate rounds.
The "you must advance one step at a time" constraint is a UX concern enforced by iOS.
This gives parents the flexibility to back-fill history without a server reject.

### D.5 `update_match` — add `score_format` propagation

When `score_format` is in the patch payload, store it. Same `field_validator` as create.
No progression re-validation on updates (parent is fixing data, not creating new).

### D.6 Plan envelope — `score_format` forwarded to `build_plan_envelope`

In `routes/plans.py`, the match-generation loop must pass `score_format=match.score_format`
to `build_plan_envelope(...)` so the rules engine uses the correct duration key.

---

## §E — iOS Changes (only delta from current state)

**What's already there (do not re-implement):**
- `TournamentCreateView` drawSize picker ✅
- `MatchCreateView` round picker via `RoundVocab.roundOptions(for: drawSize)` ✅
- `MatchCreateView` singles/doubles type picker ✅
- `MatchCreateView` doubles format picker (conditionally visible) ✅
- `RoundVocab.swift` ✅

### E.1 New iOS model fields

**`Match.swift`** — add:
```swift
/// Score format. Covers both singles and doubles.
/// 'best_of_3' | 'pro_set_8' | 'best_of_3_super_tb'. Default: 'best_of_3'.
let scoreFormat: String?  // nil → treat as 'best_of_3' (legacy back-compat)
```

**`DTOs.swift`** — `MatchDTO` gets:
```swift
let scoreFormat: String?
```
`toModel()` passes `scoreFormat: scoreFormat ?? "best_of_3"` (or keep nil if model stays optional).

### E.2 `MatchCreateView` — score format picker for singles

Add a `@State private var scoreFormat: ScoreFormat = .bestOf3` (or use a String state).

**New enum `Models/ScoreFormat.swift`:**
```swift
/// Unified match score format — covers singles and doubles.
/// Raw values match DB `matches.score_format` column values exactly.
enum ScoreFormat: String, Codable, CaseIterable {
    case bestOf3          = "best_of_3"
    case proSet8          = "pro_set_8"
    case bestOf3SuperTb   = "best_of_3_super_tb"

    var displayName: String {
        switch self {
        case .bestOf3:        return "Best of 3"
        case .proSet8:        return "8-Game Pro Set"
        case .bestOf3SuperTb: return "Match Tiebreak"
        }
    }
}
```

**Score format picker** — visible for BOTH singles and doubles (replacing the
doubles-only `doublesFormat` picker for the doubles case):
```swift
Picker("Score format", selection: $scoreFormat) {
    ForEach(ScoreFormat.allCases, id: \.self) { fmt in
        Text(fmt.displayName).tag(fmt)
    }
}
.pickerStyle(.segmented)
```

**Wire to API:** Pass `scoreFormat: scoreFormat.rawValue` in `createMatch(...)` call.

For doubles: also pass `doublesFormat` for back-compat with existing code (derive it from
`scoreFormat`: `proSet8 → "pro_set_8"`, `bestOf3/bestOf3SuperTb → "best_of_3"`). The
doubles_format field stays in the DB for back-compat.

### E.3 `MatchCreateView` — round picker constrained to next progression

Replace the current picker (all `roundOptions(for: drawSize)`) with **progression-aware logic**:

The `MatchCreateView` receives `existingMatchesForStream: [Match]` (or just
`existingRoundsInStream: [Int]`) as a new parameter passed from `TournamentDashboardView`.

```swift
/// Compute the next valid round for the stream.
/// Returns nil when the current match is the Final (round == 2) — no next match possible.
private var nextAllowedRound: Int? {
    if existingRoundsInStream.isEmpty {
        return drawSize          // first match → first round of the draw
    }
    let deepest = existingRoundsInStream.min() ?? drawSize  // min = deepest (smallest number)
    return deepest > 2 ? deepest / 2 : nil                  // nil at terminal (Final)
}
```

**Default picker state:** If `nextAllowedRound` is non-nil and the user hasn't overridden,
show only the next allowed round as a **read-only badge** with a subtle "Next in your
singles stream" / "Next in your doubles stream" caption. The parent cannot pick a different
value without explicitly entering backfill mode.

**Backfill mode:** A small "Edit round" tap target reveals the full `roundOptions(for: drawSize)`
picker. Backfill is allowed if the chosen round is not already in `existingRoundsInStream`.
The API will also validate (no-duplicate rule at §D.4).

**Terminal state:** When `nextAllowedRound == nil` (no more rounds after the Final), the
"Add match" button for that stream is hidden in `TournamentDashboardView` (or disabled with
a label "Singles bracket complete").

### E.4 `MatchChip` / `ScheduleStripView` — round badge

Add a compact badge to each chip: e.g., `"R32 · Singles · BO3"` displayed as a
`.caption` row below the time string.

Format string helper:
```swift
var matchBadge: String {
    let roundStr  = RoundVocab.abbreviation(for: plan.roundNumeric ?? 32)
    let typeStr   = plan.format == "doubles" ? "DBL" : "S"
    let fmtStr: String
    switch plan.scoreFormat {
    case "pro_set_8":          fmtStr = "Pro8"
    case "best_of_3_super_tb": fmtStr = "BO3+TB"
    default:                   fmtStr = "BO3"
    }
    return "\(roundStr) · \(typeStr) · \(fmtStr)"
}
```

### E.5 `MatchDetailView` — expanded round/format row

Full-text row near the top: `"Round of 32 · Singles · Best of 3 sets"` using
`RoundVocab.label(for:)` and `ScoreFormat.displayName`.

### E.6 `FakeData.swift` — update constructors

Add `scoreFormat: "best_of_3"` to all `Match` and `Plan` constructors that pass the
field (once Codable struct is updated). Dallas demo uses singles/best_of_3 by default.

---

## §F — Acceptance Criteria

**AC#1:** New tournament with `draw_size=64` → first singles match's round picker defaults
locked to 64 (showing "Round of 64" label). Parent cannot select R32/QF/SF/F without
entering backfill mode.

**AC#2:** After a singles R64 match exists → second singles match's round picker defaults
locked to 32 ("Round of 32"). Backend rejects duplicate R64 with 422 if attempted.
Doubles stream is unaffected (can still accept R64 for doubles).

**AC#3:** Setting `score_format = 'pro_set_8'` on a match → rules engine uses the
`("singles", "pro_set_8")` duration key → `{30, 45, 65}` minutes. Verified via plan
generation with `score_format` in the payload.

**AC#4:** Setting `score_format = 'best_of_3_super_tb'` → rules engine uses
`("singles", "best_of_3_super_tb")` → `{50, 75, 115}` minutes.

**AC#5:** API rejects a second `singles` match with the same `round` as an existing
`singles` match (422: "A singles match for round 64 already exists").

**AC#6:** Existing pre-migration matches (null `score_format`) render correctly — `MatchChip`
badge falls back to "BO3", plan generation uses `("singles", None)` duration fallback.
Zero crash, zero blank field.

---

## §G — Edge Cases

**G.1 Stream terminal at round=2:** When the deepest existing round in a stream is 2
(Final), the `nextAllowedRound` returns nil. `TournamentDashboardView` hides the "Add
match" button for that stream type, or shows a disabled "Singles bracket complete" label.

**G.2 Draw size 32, add four singles matches:** R32 → R16 → QF → SF → F. After the Final
is added, singles is complete. Doubles can still progress independently.

**G.3 `score_format` + `doubles_format` for doubles:** For doubles matches, both fields
are set. The rules engine uses `(format, score_format)` as the primary key.
`doubles_format` stays for back-compat. Equivalence: `score_format='pro_set_8'` ↔
`doubles_format='pro_set_8'`; `score_format='best_of_3'` or `'best_of_3_super_tb'` ↔
`doubles_format='best_of_3'`.

**G.4 Parent back-fills R64 after R32 already exists:** iOS backfill mode allows it.
API accepts it (not a duplicate; both rounds are different). Stream now shows R64 and R32.
If parent then tries to add R32 again, API rejects with 422 (duplicate).

**G.5 No existing matches from a stream yet:** `nextAllowedRound = drawSize`. First
singles match always defaults to the draw's opening round.

---

## §H — Out of Scope (deferred, with OQ IDs)

| Item | OQ | Rationale |
|------|----|-----------|
| Game-by-game score capture (6-4, 7-5) | OQ-ROUND-2 | Separate feature, distinct UX surface, substantial new schema. Not what user asked for. |
| Round-robin format | OQ-ROUND-3 | Junior is overwhelmingly single-elimination. Defer until a user requests it. |
| Consolation / back-draw | OQ-ROUND-4 | Adds complexity. Not in user request. |
| Doubles partner tracking (name/info) | OQ-ROUND-5 | Cold-start UX burden. Parent can use match notes. |
| 16/8/4-draw support | OQ-ROUND-6 | Needs check-constraint widening. File as a small Engineering ticket if a user requests it. |
| Win/loss result field | OQ-ROUND-7 | Implicit today (next round added = advanced). No separate field needed for MVP. |
| Consolation bracket | OQ-ROUND-4 | Same as round-robin — out of scope. |
| Auto-cascade round edit | OQ-ROUND-8 | If parent edits round 1's value, gap detection is a UX nice-to-have. Warn-only at most. |

**Score capture (OQ-ROUND-2) defended:** The user said "scores and rounds and tournaments."
PM reads "scores" as score **format** (this spec) because: (a) the user immediately
followed with "two out of three sets or the eight-game pro set" — clearly format, not
capture; (b) score capture needs win/loss derivation, bracket display, a new data surface,
and is a substantially different UX from anything shipped. If the user actually wants
game-by-game capture, it's a separate spec.

---

## §J — Engineering Scope

### Backend (7 items)

1. **`db/supabase/migrations/0018_score_format.sql`** (NEW) — DDL verbatim from §B.1.

2. **`MatchRow` in `models/db.py`** — add `score_format: str = "best_of_3"`.

3. **`MatchCreate` in `routes/matches.py`** — add `score_format: Optional[str] = "best_of_3"`,
   with a `field_validator` validating it is one of `{'best_of_3', 'pro_set_8', 'best_of_3_super_tb'}`.

4. **`MatchUpdate` in `routes/matches.py`** — add `score_format: Optional[str] = None`,
   same validator.

5. **`_validate_round_progression()` helper** in `routes/matches.py` — §D.4 exact spec.
   Called in `create_match` after existing date-range validation. Stream = `body.format or "singles"`.

6. **`rules/constants.py`** — add 5 new entries to `SCENARIO_DURATIONS_MIN` per §C.1,
   bump `RULES_CONSTANTS_VERSION` from `"1.1.0"` to `"1.2.0"`.

7. **`routes/plans.py`** — `build_plan_envelope(...)` call site passes
   `score_format=match.score_format` (or equivalent). Update `build_plan_envelope`
   signature in `rules/plan.py` to accept and use `score_format` in the duration lookup.
   Duration lookup: `SCENARIO_DURATIONS_MIN.get((match.format or "singles", score_format))
   or SCENARIO_DURATIONS_MIN[("singles", None)]`.

8. **`tests/test_round_progression.py`** (NEW) — ≥10 tests:
   - First match in stream → accepted with `round = draw_size`
   - Second singles match → accepted at `draw_size / 2`
   - Third singles match → accepted at `draw_size / 4`
   - Duplicate round in singles stream → 422
   - Duplicate round in doubles stream → 422
   - Duplicate round in singles does NOT block doubles at same round → 201
   - `score_format = 'pro_set_8'` → plan duration uses pro_set_8 values
   - `score_format = 'best_of_3_super_tb'` → plan duration uses super_tb values
   - `score_format` defaults to `'best_of_3'` if omitted
   - Legacy match (null `score_format`) → falls back to `("singles", None)` correctly

### iOS (8 items)

1. **`Models/ScoreFormat.swift`** (NEW) — enum per §E.2.

2. **`Models/Match.swift`** — add `let scoreFormat: String?`.

3. **`Networking/DTOs.swift`** — add `scoreFormat: String?` to `MatchDTO`, map in `toModel()`.

4. **`Views/MatchCreateView.swift`**:
   - Add `@State private var scoreFormat: ScoreFormat = .bestOf3`
   - Add `existingRoundsInStream: [Int]` parameter (passed from `TournamentDashboardView`)
   - Add `nextAllowedRound` computed property per §E.3
   - Add score format picker (segmented, per §E.2)
   - Replace unconstrained round picker with progression-aware display per §E.3
   - Wire `scoreFormat` into `createMatch(...)` call

5. **`Views/TournamentDashboardView.swift`**:
   - Compute `existingSinglesRounds: [Int]` and `existingDoublesRounds: [Int]` from
     `appState.currentPlanEnvelope.allPlans` (using `plan.format` and `plan.roundNumeric`)
   - Pass the appropriate array to `MatchCreateView` when the sheet opens
   - Hide/disable "Add match" button per stream when that stream is at terminal (§G.1)

6. **`Views/ScheduleStripView.swift` / `MatchChip`** — add compact badge per §E.4.

7. **`Views/MatchDetailView.swift`** — add full-text row per §E.5.

8. **`Data/FakeData.swift`** — add `scoreFormat: "best_of_3"` to all `Match` constructors
   once Codable struct is updated. Dallas demo uses R32 singles best_of_3.

### Self-verification gate (paste verbatim stdout before declaring done)

```bash
# Migration
ls db/supabase/migrations/0018_score_format.sql
# Expected: file exists

# Backend fields
grep -n "score_format" apps/api/src/playfuel_api/routes/matches.py
# Expected: ≥4 matches (MatchCreate field, MatchUpdate field, validator, _validate_round_progression call)

grep -n "score_format\|RULES_CONSTANTS_VERSION" apps/api/src/playfuel_api/rules/constants.py
# Expected: ≥6 matches (new dict entries + version string)

# Backend tests
cd apps/api && python3.12 -m pytest src/playfuel_api/tests/test_round_progression.py -v 2>&1 | tail -12
# Expected: ≥10 passed, 0 failed

cd apps/api && python3.12 -m pytest src/playfuel_api/tests/ 2>&1 | tail -5
# Expected: ≥677 passed (666 baseline + ≥10 new), 0 failed

# iOS fields
grep -rn "scoreFormat\|ScoreFormat\|nextAllowedRound\|existingRoundsInStream" apps/ios/PlayFuel/Sources/PlayFuel/
# Expected: ≥12 matches across ≥5 files

# iOS build
cd apps/ios/PlayFuel && xcodebuild -scheme PlayFuel -destination 'platform=iOS Simulator,name=iPhone 17' build 2>&1 | tail -5
# Expected: BUILD SUCCEEDED

# Migration applied to local DB (DR_18)
supabase migration list 2>&1 | tail -5
# Expected: 0018 appears as applied

# RULES_CONSTANTS_VERSION bump
grep "RULES_CONSTANTS_VERSION" apps/api/src/playfuel_api/rules/constants.py
# Expected: "1.2.0"
```

---

## §K — Open Questions

| ID | Priority | Question | Owner | Blocking |
|----|----------|----------|-------|----------|
| **OQ-ROUND-1** | 🟡 | Singles `pro_set_8` durations `{30,45,65}` and `best_of_3_super_tb` `{50,75,115}` are DRAFT — derived from observed norms, not a published source. Doubles `("doubles","best_of_3_super_tb")` `{50,75,110}` also DRAFT. Validate with USTA junior coach before Phase 7 cutover. | Planning Lead / USTA coach | No (rules engine falls back safely) |
| **OQ-ROUND-2** | 🟢 | Game-by-game score capture (6-4, 7-5) deferred. If user requests it, scope as separate spec. | Planning Lead | No |
| **OQ-ROUND-3** | 🟢 | Round-robin format. Out of scope. | Planning Lead | No |
| **OQ-ROUND-4** | 🟢 | Consolation / back-draw bracket. Out of scope. | Planning Lead | No |
| **OQ-ROUND-5** | 🟢 | Doubles partner tracking. Out of scope. | Planning Lead | No |
| **OQ-ROUND-6** | 🟢 | 16/8/4-draw support requires `CHECK (draw_size IN (4,8,16,32,64,128,256))` widening. Easy fix when a user requests it. | Engineering Lead | No |
| **OQ-ROUND-7** | 🟢 | Win/loss result field. Deferred — implicit via next-round creation. | Planning Lead | No |
| **OQ-ROUND-8** | 🟢 | Auto-cascade editing: if parent edits the round on an existing match, gap detection could re-order stream. Warn-only at most. | Engineering Lead | No |

---

## §L — Dependencies Before Engineering Starts

1. **Engineering** — confirm `rules/scenarios.py` is the actual duration-lookup call site
   (vs. `rules/plan.py` — grep before proceeding). The brief assumed `scenarios.py`;
   verify on disk.

2. **Engineering** — confirm the correct `build_plan_envelope` signature shape. The match-done
   spec added `is_done` in this same session; ensure the `score_format` param is additive to
   that, not a replacement.

3. **Validation** — pre-validate the six new `SCENARIO_DURATIONS_MIN` entries against
   `DOUBLES_SPEC_V1.md §B.3` derivation rationale before merge. The singles pro-set and
   super-tb values are DRAFT; Validation should note "DRAFT — OQ-ROUND-1" explicitly in
   the merge report.

---

*End of spec. Engineering can execute against §J immediately. Validation has clear ACs
in §F and the DR_15 self-verification gate in §J.*
