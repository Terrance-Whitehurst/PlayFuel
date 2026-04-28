# PlayFuel — Doubles Spec v1

> **Version:** 1.0.0-draft
> **Status:** DRAFT — awaiting Engineering review
> **Authority:** Planning (author) · Engineering Lead (implementation executor)
> **Last updated:** 2026-04-27
> **Sources:** `RULES_CONSTANTS_V1.md`, `PRD.md §6`, `USER_STORIES.md`,
> `apps/api/src/playfuel_api/models/api.py`, `models/db.py`, `models/enums.py`,
> `rules/plan.py`, `rules/scenarios.py`, `rules/constants.py`,
> `routes/matches.py`, `apps/ios/…/Views/MatchCreateView.swift`,
> `Views/TournamentDashboardView.swift`, `State/AppState.swift`,
> `Models/Match.swift`, `db/supabase/migrations/0002_tables.sql`

---

## Purpose & Non-Goals

This document is an **additive extension** to `RULES_CONSTANTS_V1.md`. It introduces
match-type awareness (singles vs. doubles), doubles format selection (best_of_3 vs.
pro_set_8), and adapted scenario durations for doubles matches. It does **not** modify
any existing value in `RULES_CONSTANTS_V1.md`.

**Non-goals:**
- Does not change weather flag thresholds, food bucket boundaries, pickup bucket
  boundaries, or hydration cadence (all identical for both match types in v1).
- Does not support per-player doubles dietary / hydration profiles.
- Does not add live scoresheet, point-tracking, or partner management.
- Does not change LLM safety guardrails or the prohibited-phrase list.

---

## §A. Enums

### A.1 Three-representation table

| Concept | DB (column) | Pydantic (Python) | Swift |
|---|---|---|---|
| Match type | `matches.format` — nullable text; `'singles'` \| `'doubles'`; null → treat as `'singles'` | `MatchType(StrEnum)` — `.singles = "singles"`, `.doubles = "doubles"` | `enum MatchType: String, Codable, CaseIterable { case singles, doubles }` |
| Doubles format | `matches.doubles_format` — nullable text; `'best_of_3'` \| `'pro_set_8'`; null when format ≠ doubles | `DoublesFormat(StrEnum)` — `.best_of_3 = "best_of_3"`, `.pro_set_8 = "pro_set_8"` | `enum DoublesFormat: String, Codable, CaseIterable { case bestOf3 = "best_of_3"; case proSet8 = "pro_set_8" }` |
| Per-plan type | `plans.match_type` — nullable text; null = legacy = singles | same `MatchType` enum | same `MatchType` enum |

### A.2 Column placement and migration status

| Column | Table | Nullable | Default | Migration | Status |
|---|---|---|---|---|---|
| `format` | `public.matches` | yes | null | 0002_tables.sql | **ALREADY EXISTS** — used as match type |
| `doubles_format` | `public.matches` | yes | null | 0007_doubles_support.sql | **NEW** |
| `match_type` | `public.plans` | yes | null | 0007_doubles_support.sql | **NEW** (null = legacy = singles) |

> ⚠️ **[OQ-DBL-3] Verification catch — pre-decided brief vs. reality:**
> The orchestrator brief specified "add a new `match_type` column (NOT NULL DEFAULT
> 'singles') to `matches`." However, `db/supabase/migrations/0002_tables.sql` **already
> contains** `format text -- e.g. "singles", "doubles"` on `public.matches`, and
> `models/db.py` already has `MatchRow.format: Optional[str] = None`, and
> `routes/matches.py` `MatchCreate`/`MatchUpdate` already expose `format`.
> **Resolution:** use the existing `format` column as the match-type vehicle. Do NOT add
> a redundant `match_type` column to `matches`. Migration 0007 adds only `doubles_format`
> to `matches` (and `match_type` to `plans`). All rules-engine code must read
> `match.format` (defaulting to `"singles"` when null).

### A.3 New Pydantic enums — add to `models/enums.py`

```python
class MatchType(StrEnum):
    """Doubles-spec extension. Stored in matches.format column (pre-existing, §A.2).
    Also stored in plans.match_type (new column, 0007_doubles_support.sql)."""
    singles = "singles"
    doubles = "doubles"


class DoublesFormat(StrEnum):
    """Doubles-spec extension. Stored in matches.doubles_format (new, 0007).
    Null / absent means singles or format not specified."""
    best_of_3 = "best_of_3"
    pro_set_8 = "pro_set_8"
```

Add `partnerCoordination = "partnerCoordination"` to the existing `TimelineEventKind`
enum. `TimelineEventKind` is **API-contract only** (not a Postgres enum per the existing
comment in `enums.py`) — no migration required.

### A.4 New Swift enums — new file `Models/MatchType.swift`

```swift
/// Match type. Raw values match DB text column values exactly.
enum MatchType: String, Codable, CaseIterable {
    case singles
    case doubles
}

/// Doubles format. Relevant only when matchType == .doubles.
/// Raw values match DB text column values exactly.
enum DoublesFormat: String, Codable, CaseIterable {
    case bestOf3 = "best_of_3"
    case proSet8 = "pro_set_8"

    var displayName: String {
        switch self {
        case .bestOf3: return "Best of 3"
        case .proSet8: return "8-Game Pro Set"
        }
    }
}
```

---

## §B. Scenario Duration Constants

> ⚠️ **[DRAFT — OQ-DBL-1]** All doubles values below are derived from observed
> USTA Junior Level 1–4 / ITF junior tournament norms. No published authoritative
> source provides exact minute values. Every doubles cell is tagged DRAFT. **Validate
> with a USTA junior coach or tournament director before Phase 7 cutover.**

### B.1 Duration table (canonical Python — replaces flat `SCENARIO_DURATIONS_MIN`)

```python
# rules/constants.py — replaces the flat dict[str, int].
# Keyed by (match_type_str, doubles_format_str | None).
# RULES_CONSTANTS_VERSION must be bumped to "1.1.0" when this lands (§J.2 minor bump).

SCENARIO_DURATIONS_MIN: dict[tuple[str, str | None], dict[str, int]] = {
    ("singles", None):          {"short": 75,  "normal": 120, "long": 180},  # v1 — FROZEN
    ("doubles", "best_of_3"):   {"short": 60,  "normal": 90,  "long": 135},  # [DRAFT — OQ-DBL-1]
    ("doubles", "pro_set_8"):   {"short": 45,  "normal": 70,  "long": 100},  # [DRAFT — OQ-DBL-1]
}
```

### B.2 Tabular view

| match_type | doubles_format | short (min) | normal (min) | long (min) | Source |
|---|---|---|---|---|---|
| singles | — | 75 | 120 | 180 | RULES_CONSTANTS_V1 §A.1 — FROZEN |
| doubles | best_of_3 | 60 | 90 | 135 | [DRAFT — OQ-DBL-1] Derived |
| doubles | pro_set_8 | 45 | 70 | 100 | [DRAFT — OQ-DBL-1] Derived |

### B.3 Derivation rationale (OQ-DBL-1 audit trail)

- Doubles is generally **25–35% faster** than equivalent-length singles: shorter rallies,
  junior no-ad scoring, 10-point match tiebreak in lieu of a 3rd set.
- **best_of_3 doubles**: typical USTA junior doubles runs 60–90 min. Long cap at 135 min
  accounts for super-tiebreak extension. Values are derived, not cited.
- **pro_set_8 doubles**: 8-game pro set typically runs 35–60 min in juniors; super-tiebreak
  at 8-all. Short floor at 45 min; long cap at 100 min. Values are derived, not cited.

### B.4 Worked example — Dallas 9 AM / 1 PM with doubles (pro_set_8)

| Scenario | Duration | Match end | Gap | Food bucket | Pickup bucket |
|---|---|---|---|---|---|
| short | 45 | 9:45 AM | 195 | `light_meal` (≥150) | `wait_until_end` (≥120) |
| normal | 70 | 10:10 AM | 170 | `light_meal` (≥150) | `wait_until_end` (≥120) |
| long | 100 | 10:40 AM | 140 | `quick_pickup` (90≤140<150) | `wait_until_end` (≥120) |

Food/pickup bucket boundaries are **unchanged** from §B.2/§B.3 of `RULES_CONSTANTS_V1`.

---

## §C. Plan Deltas per Match Type

| Dimension | Singles | Doubles | Justification |
|---|---|---|---|
| Food bucket boundaries | [0,45)/[45,90)/[90,150)/[150,∞) | **same** | Gap-driven, not match-type-driven |
| Pickup bucket boundaries | [0,60)/[60,120)/[120,∞) | **same** | Same reason |
| Hydration cadence (OQ-A, draft) | DRAFT | **same as singles for v1** | Per-player intensity is lower but rally pace is reactive — net wash. Revisit with sports medicine post OQ-A resolution. `[DRAFT — OQ-DBL-2]` |
| Pre-match warm-up offsets (OQ-C, draft) | DRAFT | **same as singles for v1** | Court warm-up occupies court with opponent regardless of format |
| Re-warm-up trigger (gap ≥ 60 min) | same | **same** | Physiological, not format-driven |
| Heat / weather flag thresholds (§E v1) | all unchanged | **same** | Environmental, not format-driven |
| `TIGHT_GAP_THRESHOLD_MIN` (OQ-E) | 30 min [DRAFT] | **same** | |
| Scenario duration values | §A.1 v1 | **different — see §B** | Core change of this spec |
| Timeline events | wakeUp / meal / etc. | **add `partnerCoordination` at T−60m** | Only doubles-specific addition; details in §C.1 |
| LLM prose voice | "you" / "your player" | "you and your partner" / "your doubles team" | Via `match_type` field on `PlanExplanationInput` |

### C.1 New timeline event: `partnerCoordination`

| Property | Value |
|---|---|
| Kind constant | `TimelineEventKind.partnerCoordination` (Python) / `.partnerCoordination` (Swift) |
| DB requirement | None — API-contract enum only (mirrors existing note in `enums.py`) |
| Trigger condition | `match.format == "doubles"` |
| Offset | T−60 min relative to `scheduled_start` |
| Title | `"Confirm with your doubles partner"` |
| Detail | `"Agree on warm-up time, court arrival, and pre-match strategy with your partner."` |

### C.2 `PlanExplanationInput` extension

Add `match_type: str = "singles"` field to the existing `PlanExplanationInput` model in
`models/api.py`. `TemplateProvider.explain_plan()` branches on this field:
- `"singles"` → prose uses "you" / "your player"
- `"doubles"` → prose uses "you and your partner" / "your doubles team"

---

## §D. Plan Response Shape

### D.1 Response envelope — replaces `GeneratePlanResponse`

`GeneratePlanResponse.plan` (single `Plan`) is **replaced** by named optional fields.

```python
class GeneratePlanResponse(BaseModel):
    """HTTP 200 from POST /v1/tournaments/{tid}/plans/generate.
    singlesPlan and doublesPlan are null when the corresponding match type
    has no match in the tournament."""
    model_config = _CAMEL
    singles_plan: Optional[Plan] = None   # alias: singlesPlan
    doubles_plan: Optional[Plan] = None   # alias: doublesPlan
```

> ⚠️ **BREAKING CHANGE.** `plan` (current field) is removed. iOS `Repository.generatePlan()`
> currently returns `Plan`; it must be updated to return a new `PlanEnvelope` Swift type.
> All view references to `appState.currentPlan` must migrate to `appState.currentPlanEnvelope`.

### D.2 JSON examples

**Singles-only tournament (`doublesPlan: null`):**
```json
{
  "singlesPlan": {
    "planId": "...", "tournamentId": "...", "generatedAt": "...",
    "scenarioPlans": [
      {"scenario":"short","durationMin":75,"gapStatus":"ok",...},
      {"scenario":"normal","durationMin":120,...},
      {"scenario":"long","durationMin":180,...}
    ],
    "weather": {...}, "foodOptions": [...], "llmSummary": {...}
  },
  "doublesPlan": null
}
```

**Both types present:**
```json
{
  "singlesPlan": { "scenarioPlans": [{"durationMin":75},{"durationMin":120},{"durationMin":180}], ... },
  "doublesPlan": { "scenarioPlans": [{"durationMin":60},{"durationMin":90},{"durationMin":135}], ... }
}
```

### D.3 `plans` table — per-type rows

Each call to `/generate` upserts one `plans` row per match type present. The new
`match_type` column disambiguates rows for the same tournament.

| Condition | plans rows created | `match_type` column |
|---|---|---|
| Singles only | 1 | `"singles"` |
| Doubles only | 1 | `"doubles"` |
| Both present | 2 | `"singles"` + `"doubles"` |

"Latest plan" retrieval (`GET /v1/tournaments/{tid}/plans/latest`) must return the
envelope shape as well — see OQ-DBL-6.

---

## §E. iOS UX

### E.1 TournamentDashboardView — segmented picker behavior

| Tournament state | Dashboard behavior |
|---|---|
| 0 matches | Existing empty/CTA state — unchanged |
| ≥1 singles only | Dashboard renders as today — **no picker** |
| ≥1 doubles only | Dashboard renders with doubles plan — **no picker** |
| ≥1 of BOTH types | Segmented `Picker` "Singles \| Doubles" appears **above EmergencyBanner** |

**Picker placement (pseudocode):**
```swift
// Inside planContent(plan:) — BEFORE the EmergencyBanner check
if case .loaded(let envelope) = appState.currentPlanEnvelope, envelope.hasBothTypes {
    Picker("Match Type", selection: $appState.selectedMatchType) {
        Text("Singles").tag(MatchType.singles)
        Text("Doubles").tag(MatchType.doubles)
    }
    .pickerStyle(.segmented)
    .padding(.horizontal, 16)
    .padding(.top, 8)
}
```

Resolve the active `Plan` for display:
```swift
let plan = envelope.plan(for: appState.selectedMatchType) ?? envelope.singlesPlan ?? envelope.doublesPlan
```

**Selection persistence:** `AppState.selectedMatchType: MatchType = .singles` — session-only,
not UserDefaults.

### E.2 MatchCreateView form additions

Add these two sections **before** the existing "Estimated Duration" section:

**1. Match type picker (always visible, default Singles):**
```swift
Section(header: Text("Match Type")) {
    Picker("Type", selection: $matchType) {
        Text("Singles").tag(MatchType.singles)
        Text("Doubles").tag(MatchType.doubles)
    }
    .pickerStyle(.segmented)
    .labelsHidden()
}
```

**2. Doubles format picker (visible only when matchType == .doubles):**
```swift
if matchType == .doubles {
    Section(header: Text("Doubles Format")) {
        Picker("Format", selection: $doublesFormat) {
            Text("Best of 3").tag(DoublesFormat.bestOf3)
            Text("8-Game Pro Set").tag(DoublesFormat.proSet8)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
    }
}
```

**3. Dynamic duration labels** (replace the current hardcoded `durationOptions` constant
with a computed property that reflects §B values):
```swift
private var durationOptions: [(label: String, minutes: Int)] {
    switch (matchType, doublesFormat) {
    case (.doubles, .proSet8):
        return [("Short (45)", 45), ("Normal (70)", 70), ("Long (100)", 100)]
    case (.doubles, .bestOf3):
        return [("Short (60)", 60), ("Normal (90)", 90), ("Long (135)", 135)]
    default: // singles or unspecified
        return [("Short (75)", 75), ("Normal (120)", 120), ("Long (180)", 180)]
    }
}
```
Reset `durationIndex = 1` (Normal) in an `.onChange(of: matchType)` and
`.onChange(of: doublesFormat)` modifier.

### E.3 New iOS model types

**`Models/MatchType.swift`** (NEW) — see §A.4.

**`Models/PlanEnvelope.swift`** (NEW):
```swift
/// Wraps optional singles and doubles plans from GeneratePlanResponse.
struct PlanEnvelope: Codable {
    let singlesPlan: Plan?
    let doublesPlan: Plan?

    var hasBothTypes: Bool { singlesPlan != nil && doublesPlan != nil }

    func plan(for type: MatchType) -> Plan? {
        type == .singles ? singlesPlan : doublesPlan
    }
}
```

### E.4 AppState.swift changes

```swift
// Replace:
@Published var currentPlan: LoadState<Plan> = .idle

// With:
@Published var currentPlanEnvelope: LoadState<PlanEnvelope> = .idle
@Published var selectedMatchType: MatchType = .singles
```
Update `generatePlan(for:)` to populate `currentPlanEnvelope`.

### E.5 Match.swift changes (EDIT)

Add two properties with `= nil` defaults (mirrors the `roundLabel` / `courtLabel`
pattern from Session 2 to avoid breaking FakeData call sites):

```swift
/// Match type: "singles" or "doubles". Nil for pre-doubles-spec matches (treat as singles).
let format: String? = nil

/// Doubles format: "best_of_3" or "pro_set_8". Nil when format != "doubles".
let doublesFormat: String? = nil
```

### E.6 FakeData.swift

Add `dallasPlanEnvelope: PlanEnvelope` using `dallasPlan` as `singlesPlan` and a
doubles-shaped fake plan as `doublesPlan` (or just `singlesPlan: dallasPlan, doublesPlan: nil`
for the minimal-working-preview case). Update `#Preview` references in
`TournamentDashboardView` from `state.currentPlan = .loaded(...)` to
`state.currentPlanEnvelope = .loaded(FakeData.dallasPlanEnvelope)`.

---

## §F. User Stories

### US-DBL-1 — Create a doubles match with format selection

**As a** parent whose child is playing doubles,
**I want** to specify the match type and choose the doubles format,
**so that** the plan uses realistic scenario durations for that format.

**Given** I am in `MatchCreateView`,
**When** I tap "Doubles" in the Match Type picker,
**Then** a "Doubles Format" picker appears with "Best of 3" and "8-Game Pro Set" options
(default: Best of 3), AND the Estimated Duration labels update to match the chosen
format's short/normal/long minute values.

**Given** I save a doubles match with format "8-game pro set",
**When** the record is created,
**Then** `matches.format = 'doubles'` and `matches.doubles_format = 'pro_set_8'` are persisted.

**Given** I save a singles match,
**When** the record is created,
**Then** `matches.format = 'singles'` and `matches.doubles_format = null` are persisted.

---

### US-DBL-2 — View per-type plans on a mixed tournament

**As a** parent whose child has both singles and doubles matches in the same tournament,
**I want** to see a "Singles | Doubles" tab control on the dashboard,
**so that** I can view each plan separately without either cluttering the other.

**Given** a tournament has ≥1 singles and ≥1 doubles match,
**When** I view the dashboard after generating a plan,
**Then** a segmented "Singles | Doubles" picker appears above the emergency banner,
and selecting a segment shows only that match type's plan.

**Given** a tournament has only singles matches,
**When** I view the dashboard,
**Then** no picker appears and the dashboard renders exactly as it does today.

**Given** I am viewing the doubles plan,
**When** I look at the scenario cards,
**Then** scenario durations reflect the doubles §B values, not 75/120/180.

---

### US-DBL-3 — LLM explanation addresses the doubles team

**As a** parent viewing the plan summary for a doubles match,
**I want** the plan summary to acknowledge my child is playing with a partner,
**so that** the summary feels relevant rather than written for a singles player.

**Given** the active plan is a doubles plan,
**When** `PlanSummaryCard` renders,
**Then** the `summary` field uses "you and your partner" or "your doubles team",
not "you" / "your player".

**Given** a tournament has both match types,
**When** I switch between "Singles" and "Doubles" tabs,
**Then** `PlanSummaryCard` updates to show the explanation matching the selected type.

---

## §G. Open Questions / DRAFT Flags

| ID | Question | Blocks | Recommendation | Source |
|---|---|---|---|---|
| OQ-DBL-1 | All doubles duration values in §B are derived from observed junior tournament norms, not a published authoritative source. Are 60/90/135 (best_of_3) and 45/70/100 (pro_set_8) acceptable for demo? | Phase 7 | Validate with a USTA junior coach before Phase 7 cutover. Values are conservative. | Derived |
| OQ-DBL-2 | Hydration cadence for doubles — should per-player fluid quantities differ from singles? | Phase 7+ | Keep parity for v1; revisit with sports medicine when OQ-A is resolved. | Physiological assessment pending |
| OQ-DBL-3 | `matches.format` already exists (0002_tables.sql) with "singles"/"doubles" as examples. Brief specified a new `match_type` column — that would be redundant. **Resolved here:** use `format`, add only `doubles_format` to `matches`. | Migration 0007 | Confirmed in this spec. Engineering must NOT add a second match-type column to `matches`. | `0002_tables.sql`, `models/db.py`, `routes/matches.py` |
| OQ-DBL-4 | `AppState.currentPlan: LoadState<Plan>` → `currentPlanEnvelope: LoadState<PlanEnvelope>` is a broad refactor touching every view. Engineering should consider a clean one-pass replacement vs. a parallel-property transition. | iOS | Recommend clean replacement (views are small). | `State/AppState.swift` |
| OQ-DBL-5 | `SCENARIO_DURATIONS_MIN` dict shape change (flat → nested) breaks current `constants.py` and `scenarios.py`. Requires `RULES_CONSTANTS_VERSION` bump to `"1.1.0"` per §J.2 minor-change rule. Confirm version bump before shipping. | API tests | Confirm with Engineering Lead; eval harness version-assert will fail until bumped. | `rules/constants.py`, `rules/scenarios.py` |
| OQ-DBL-6 | `GET /v1/tournaments/{tid}/plans/latest` currently returns a single `Plan`. With doubles, two rows may exist. Should this route return the envelope shape or accept `?match_type=` query param? | API | Recommend: return `GeneratePlanResponse` envelope shape from `/latest` as well, matching `/generate`. | `routes/plans.py` |

---

## §H. Engineering Hand-Off

### H.1 DB migration skeleton

**File: `db/supabase/migrations/0007_doubles_support.sql`**

```sql
-- 0007_doubles_support.sql
-- Adds doubles format support to matches and match_type column to plans.
-- IMPORTANT: matches.format (added in 0002_tables.sql) is already used as match type.
-- Do NOT add a new match_type column to matches — see DOUBLES_SPEC_V1.md §A.2 OQ-DBL-3.
-- Both statements are idempotent (IF NOT EXISTS).

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS doubles_format text;
COMMENT ON COLUMN public.matches.doubles_format IS
  'Doubles match format. NULL when format != ''doubles''. '
  'Valid values: ''best_of_3'', ''pro_set_8''. See DOUBLES_SPEC_V1.md §A.';

ALTER TABLE public.plans
  ADD COLUMN IF NOT EXISTS match_type text;
COMMENT ON COLUMN public.plans.match_type IS
  'Match type this plan was generated for. NULL = legacy (treat as ''singles''). '
  'Valid values: ''singles'', ''doubles''. See DOUBLES_SPEC_V1.md §D.3.';
```

Update `db/supabase/README.md` migration table: add 0007 row.

### H.2 Backend file list

| File | Change |
|---|---|
| `models/enums.py` | Add `MatchType(StrEnum)`, `DoublesFormat(StrEnum)`, `TimelineEventKind.partnerCoordination` |
| `models/db.py` | `MatchRow`: add `doubles_format: Optional[str] = None` (note: `format` already present). `PlanRow`: add `match_type: Optional[str] = None` |
| `models/api.py` | `MatchInput`: add `match_type: MatchType = MatchType.singles`, `doubles_format: Optional[DoublesFormat] = None` (derived from `format` + `doubles_format` columns). `PlanExplanationInput`: add `match_type: str = "singles"`. Replace `GeneratePlanResponse.plan` with `singles_plan: Optional[Plan] = None` + `doubles_plan: Optional[Plan] = None` |
| `rules/constants.py` | Replace flat `SCENARIO_DURATIONS_MIN` with nested dict per §B.1. Bump `RULES_CONSTANTS_VERSION = "1.1.0"` |
| `rules/scenarios.py` | `generate_match_scenarios()`: add `match_type: str = "singles"` and `doubles_format: Optional[str] = None` kwargs. Lookup: `SCENARIO_DURATIONS_MIN[(match_type, doubles_format)][kind.value]` |
| `rules/plan.py` | `build_timeline()`: emit `partnerCoordination` event at T−60m when `any(m.format == "doubles" for m in matches)`. `build_plan_envelope()`: accept and pass `match_type` for LLM input |
| `routes/plans.py` | Group matches by `format` column; for each match type present call `generate_match_scenarios(match_type=..., doubles_format=...)` and `build_plan_envelope()`; persist separate `plans` rows with `match_type`; return `GeneratePlanResponse(singles_plan=..., doubles_plan=...)` |
| `routes/matches.py` | `MatchCreate` / `MatchUpdate`: add `doubles_format: Optional[str] = None` (note: `format` field already present) |
| `services/llm.py` | `build_explanation_input()`: pass `match_type`. `TemplateProvider.explain_plan()`: branch on `match_type` for partner-aware prose (§C.2) |

### H.3 iOS file list

| File | Status | Change |
|---|---|---|
| `Models/MatchType.swift` | NEW | `MatchType` + `DoublesFormat` Swift enums (§A.4) |
| `Models/PlanEnvelope.swift` | NEW | `PlanEnvelope` struct (§E.3) |
| `Models/Match.swift` | EDIT | Add `format: String? = nil` + `doublesFormat: String? = nil` (use `= nil` default pattern matching `roundLabel`) |
| `Networking/DTOs.swift` | EDIT | `MatchCreateRequest`: add `format: String`, `doublesFormat: String?`. `MatchDTO.toModel()`: map `format` + `doublesFormat`. Add `PlanEnvelopeDTO` + `.toModel()` |
| `Networking/Repository.swift` | EDIT | `createMatch()`: add `matchType: MatchType` + `doublesFormat: DoublesFormat?` params; pass `format` + `doublesFormat` in body. `generatePlan()`: return `PlanEnvelope` |
| `State/AppState.swift` | EDIT | Replace `currentPlan: LoadState<Plan>` with `currentPlanEnvelope: LoadState<PlanEnvelope>`; add `selectedMatchType: MatchType = .singles` |
| `Views/MatchCreateView.swift` | EDIT | Add `@State private var matchType: MatchType = .singles` and `@State private var doublesFormat: DoublesFormat = .bestOf3`; add two new form sections (§E.2); convert `durationOptions` to computed property (§E.2 §3) |
| `Views/TournamentDashboardView.swift` | EDIT | Add conditional segmented picker above EmergencyBanner (§E.1); resolve `Plan` from `currentPlanEnvelope` using `selectedMatchType` |
| `Data/FakeData.swift` | EDIT | Add `dallasPlanEnvelope: PlanEnvelope`; update `#Preview` in `TournamentDashboardView` to use envelope |

### H.4 Required new test files

| File | Coverage |
|---|---|
| `test_doubles_durations.py` | `[("doubles","best_of_3")]` → 60/90/135; `[("doubles","pro_set_8")]` → 45/70/100; `[("singles",None)]` still → 75/120/180 |
| `test_doubles_scenarios.py` | `generate_match_scenarios(match_type="doubles", doubles_format="pro_set_8")` short=45/normal=70/long=100; gap arithmetic correct; singles default unchanged |
| `test_doubles_routes.py` | POST `/generate` with doubles match → `doublesPlan` non-null, `singlesPlan` null; both present → both non-null; singles only → `doublesPlan` null |
| `test_doubles_timeline.py` | `build_timeline()` emits `partnerCoordination` at T−60m for doubles match; NOT emitted for singles |

### H.5 Acceptance criteria

1. `pytest` ≥ 180 + 4 new test files pass; Scenario 5 stays xfail.
2. Eval harness exit 0.
3. `0007_doubles_support.sql` exists and is idempotent.
4. POST `/generate` with only singles → `doublesPlan: null`. With both → both non-null with correct durations.
5. iOS `MatchCreateView` shows match type picker; doubles format picker reveals on Doubles; duration labels match §B values for selected combo.
6. iOS Dashboard shows "Singles | Doubles" picker ONLY when both plan types are non-null; singles-only tournaments render unchanged.
7. `RULES_CONSTANTS_VERSION = "1.1.0"` in `rules/constants.py`.
8. `test_doubles_durations.py` verifies all three rows of §B.1 duration table.
