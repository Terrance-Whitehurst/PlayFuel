# PlayFuel — Nutrition-First IA Spec v1

> **Version:** 1.0.0
> **Status:** LOCKED — Engineering executes §H verbatim
> **Authority:** Planning Lead (decisions) · Product Manager (author / scribe)
> **Last updated:** 2026-04-27
> **Sources:** `PRD.md`, `USER_STORIES.md`, `SAFETY_DISCLAIMERS.md §B`,
> `DOUBLES_SPEC_V1.md`, `apps/ios/.../TournamentDashboardView.swift`,
> `apps/ios/.../PlanEnvelope.swift`, `db/supabase/migrations/0002_tables.sql`,
> `db/supabase/migrations/0007_doubles_support.sql`

---

## Purpose

The user requested a IA pivot: **nutrition and schedule are the hero surfaces**.
Weather data is demoted — parents already feel the heat; a weather card that leads
the dashboard adds noise without action. This spec locks the new dashboard card
order, introduces two new components (ScheduleStripView and NextActionCard),
demotes WeatherCard to a compact expandable pill, and changes the API envelope
from one-plan-per-type to one-plan-per-match so the schedule strip can show
every match's scenarios independently.

**Non-goals of this spec:**
- Does not change any rules engine constants or food bucket logic.
- Does not change weather flag classification or extreme_heat_risk triggers.
- Does not change the LLM safety guardrails or PROHIBITED_PHRASES list.
- Does not introduce real-time client-side clock recomputation (see OQ-IA-6).

---

## §A. Principles

1. **Nutrition + schedule lead** — the only surfaces a parent can act on are what
   to eat and when. Everything else is supporting context. Hero cards are ordered
   by actionability.
2. **Weather data stays accessible but never demands attention** — parents are
   already outside, already feeling the conditions. The weather card provides
   ambient data; it must not be the first thing they see.
3. **Safety banner is the ONLY exception** — `EmergencyBanner` renders at the
   absolute top when `extreme_heat_risk == true`. Per `SAFETY_DISCLAIMERS.md §B`,
   this is non-negotiable and cannot be moved, suppressed, or demoted by any
   visual pivot. Demoting weather prominence does NOT touch safety logic.
4. **Calm coach voice frames the day; data cards execute the plan** — LLM prose
   (PlanSummaryCard) provides the calm narrative. Below it, every card is
   an executable action: strip shows the schedule, NextActionCard says "do this
   now," FoodCard says "go here," scenario cards frame the three possible endings.
5. **Glance-test: parent knows "what's next" within 2 seconds of opening** —
   the NextActionCard satisfies this. A parent opening the app during a match
   should see the most immediately actionable item without scrolling.

---

## §B. Dashboard Card Order

### Locked visual order — top to bottom

| # | Card | Visual weight | Conditional |
|---|---|---|---|
| 0 | `EmergencyBanner` | hero / red | `extreme_heat_risk == true` only — **never move or gate differently** |
| 1 | Singles / Doubles segmented Picker | inline header | only when `envelope.hasBoth == true` per `DOUBLES_SPEC_V1.md §E` |
| 2 | `PlanSummaryCard` (LLM coach voice) | hero | when `selectedPlan.llmSummary != nil` |
| 3 | `ScheduleStripView` (NEW — multi-match strip) | hero | when `matches.count > 0`; hidden + empty-CTA when 0 |
| 4 | `NextActionCard` (NEW — next actionable item) | hero | always — has deterministic fallback copy when no future event |
| 5 | `FoodCardView` | hero | always (bag fallback when no places options) |
| 6 | Scenario cards — horizontal scroll (short / normal / long) | standard | always |
| 7 | "Full Day Timeline" button | standard | when `selectedPlan.timeline.count > 0` |
| 8 | `WeatherPill` (DEMOTED from `WeatherCardView`) | compact — 1-line pill, expand-in-place | always |
| 9 | Disclaimer footer (§A link) | compact | always |

### What moved and why

| Card | Before | After | Rationale |
|---|---|---|---|
| `WeatherCardView` | #2 (second visible element after EmergencyBanner) | #8 (compact pill, default collapsed) | User steer: parents feel the weather; it is not actionable |
| `ScheduleStripView` | did not exist | #3 | Multi-match schedule is the core MVP action loop |
| `NextActionCard` | did not exist | #4 | Satisfies the 2-second glance test |
| `FoodCardView` | #4 (after scenarios) | #5 (before scenarios) | Food timing is more actionable than scenario math |
| Scenario cards | #3 | #6 | Still essential; comes after the actionable "what now" cards |

---

## §C. ScheduleStripView (NEW component spec)

### Purpose

A horizontally-scrollable strip of MatchChip views — one per match — ordered by
`scheduledStart` ascending. This is the primary navigation control: tapping a
chip drives `AppState.selectedMatchId`, which re-renders the plan content below
against that match's plan.

### MatchChip layout (per chip)

```
┌─────────────────────────────────┐
│  R16           9:00 AM          │
│  ● upcoming                     │
│  [Singles]                      │
└─────────────────────────────────┘
```

Fields:
- **Round label** — `match.roundLabel ?? "Match \(displayOrder)"` (fallback)
- **Time** — `scheduledStart` formatted as `"h:mm a"` (device-local time, OQ-IA-1)
- **Status indicator** — derived from clock vs scheduled_start + estimated_duration:
  - `upcoming` (grey pill) — `scheduledStart > now`
  - `in-progress` (yellow pill) — `scheduledStart <= now && estimatedEnd > now`
  - `done` (green check) — `estimatedEnd <= now`
  - `estimatedEnd` = `scheduledStart + selectedPlan.scenarios[normal].durationMinutes`
    when available; else `scheduledStart + 120 min` (singles default; OQ-IA-1)
- **Type pill** — `"Singles"` / `"Doubles · BO3"` / `"Doubles · Pro Set 8"`
  (derived from `match.matchType` + `match.doublesFormat`)
- **Selected state** — highlighted card background (`.accentColor.opacity(0.15)`)
  when `match.id == appState.selectedMatchId`

### Default selection rule (in priority order)

1. The next upcoming match where `scheduledStart > now` (device-local time)
2. If all matches are in the past — the match with the largest `scheduledStart`
   (most recently played)
3. If no matches — hide the strip entirely; show empty-state CTA:
   `"Add your first match"` (plus-button → MatchCreateView sheet)

### Selection persistence

- `selectedMatchId` lives in `AppState` — in-session only, not persisted to disk
- On each `.task` of TournamentDashboardView: reset to the default selection rule
  above (so returning to the dashboard re-anchors to the most actionable match)
- Tapping a chip: `appState.selectedMatchId = match.id`
- All content below the strip (PlanSummaryCard through Timeline button) renders
  against the **selected match's Plan**, not the first plan in the envelope array

### Empty state

When `matches.count == 0`, ScheduleStripView renders a full-width CTA card
with `Image(systemName: "calendar.badge.plus")`, text "Add your first match",
and a button that triggers `showingCreateMatch = true`.

---

## §D. NextActionCard (NEW component spec)

### Purpose

A single card surfaces the most immediately actionable item from the selected
match's timeline, given the current server-generation time. Satisfies the
2-second glance test — no taps required.

### Logic — deterministic, rules engine only, never LLM

Computed in `rules/next_action.py`. Input:
```python
derive_next_action(
    timeline: list[TimelineEvent],
    now: datetime,        # server now() at generation time
    extreme_heat_risk: bool,
    lookahead_hours: int = 6
) -> NextAction | None
```

Algorithm:
1. Filter `timeline` to events where `start_time > now` and
   `start_time <= now + timedelta(hours=lookahead_hours)`
2. Sort ascending by `start_time`
3. Take the first event — this is the next action
4. Compute `mins_until = int((event.start_time - now).total_seconds() / 60)`
5. Look up `detail` from `NEXT_ACTION_COPY_MAP[event.kind]` (see below)
6. If `extreme_heat_risk == True` AND `event.kind in HEAT_SENSITIVE_KINDS`:
   prepend `"Extreme heat — extra hydration. "` to `detail` (verbatim,
   never replace the existing detail copy)
7. If no event in window: return `NextAction(title="Recovery", detail="Refuel
   within 30 min — see food options below", scheduled_for=None, kind="recovery_fallback")`

### NEXT_ACTION_COPY_MAP (hardcoded, not LLM)

```python
NEXT_ACTION_COPY_MAP: dict[str, str] = {
    "match_start":         "Head to court for warm-up",
    "pre_match_meal":      "Light, easy carbs — see food options below",
    "warmup":              "Begin warm-up with your player",
    "hydration_check":     "Offer water or electrolyte drink now",
    "parent_food_pickup":  "Time to pick up food — see options below",
    "recovery_window":     "Refuel within 30 min — see food options below",
    "partner_coordination": "Confirm warm-up time with your player's partner",
    "recovery_fallback":   "Refuel within 30 min — see food options below",
}

HEAT_SENSITIVE_KINDS: frozenset[str] = frozenset({
    "match_start", "warmup", "hydration_check",
})
```

### NextAction model

```python
class NextAction(BaseModel):
    model_config = _CAMEL
    title: str                       # event.title from timeline
    detail: str                      # from NEXT_ACTION_COPY_MAP, safety-prepended if heat
    scheduled_for: Optional[datetime]  # None on recovery_fallback
    kind: str                        # TimelineEventKind value or "recovery_fallback"
    mins_until: Optional[int]        # None on recovery_fallback
```

### iOS rendering (`NextActionCard.swift`)

```
┌──────────────────────────────────────────────────────────┐
│ ⚡ In 28 min                               NEXT UP        │
│                                                          │
│  Pre-match meal                                          │
│  Light, easy carbs — see food options below              │
│                                                          │
│  9:32 AM                                                 │
└──────────────────────────────────────────────────────────┘
```

- Lead icon: `Image(systemName: "bolt.fill")` tinted `.accentColor`
- "In N min" badge — not shown on recovery_fallback (no `scheduledFor`)
- `title` in `.headline` weight; `detail` in `.subheadline` secondary color
- `scheduledFor` formatted as `"h:mm a"` in caption below

---

## §E. API Envelope Shape (Option b — one Plan per match)

### Decision: option (b) — per-match plans

**Rejected:**
- (a) One plan per type (first-of-type) — breaks the ScheduleStrip; parent can't
  see each match's scenarios independently.
- (c) On-demand per-match endpoint — adds round-trips and cache logic for no MVP
  win; TemplateProvider is free.

**Chosen:** generate one `Plan` per match in the tournament. Group by match type
for the iOS envelope.

### API response shape

```python
class GeneratePlanResponse(BaseModel):
    model_config = _CAMEL
    singles_plans: list[Plan]  # ordered by match scheduled_start ASC; empty if no singles
    doubles_plans: list[Plan]  # ordered by match scheduled_start ASC; empty if no doubles
```

**Breaking change from DOUBLES_SPEC_V1 §D:** was `{singlesPlan: Plan|null, doublesPlan: Plan|null}`.
Worth executing — that shape is one session old, not on TestFlight, no downstream
consumers outside the iOS app.

### Plan model additions

```python
class Plan(BaseModel):
    # ... existing fields ...
    match_id: UUID            # NEW — surfaces plans.match_id FK
    match_type: str           # NEW — "singles" | "doubles"
    next_action: Optional[NextAction] = None   # NEW — derived at generation time
```

### `plans` table per-match rows

Each generated Plan becomes one row in `public.plans`. Keyed by `(match_id,
match_type)`. See §H.1 for migration details.

---

## §F. WeatherCard Demotion

### Treatment: compact pill at position #8, expand-in-place

```
┌──────────────────────────────────────────────────┐
│  🌡 88°F · humid · feels 95°F          ›         │
└──────────────────────────────────────────────────┘
```

When tapped, expands inline to reveal the existing `WeatherCardView` body (temp
graph, flag pills, adjustment bullets). Collapses on second tap.

### Implementation

Modify `WeatherCardView` to accept `compact: Bool = false`:
- `compact == false` → existing card body (unchanged; used in any non-dashboard
  context if ever needed)
- `compact == true` → `HStack` pill with icon + 1-line summary + chevron; `@State
  private var expanded = false`; when `expanded`, show existing card body inline
  below the pill

Pill summary string: `"\(tempF, specifier: "%.0f")°F · \(flagSummary) · feels \(apparentTempF, specifier: "%.0f")°F"`.
`flagSummary` = comma-joined flag display names (e.g. "humid", "hot"). If no
flags: omit the flags segment.

Expansion state: per-session, default collapsed. Do NOT persist — cost of
re-tapping is trivial and persisting adds state complexity.

### What is UNCHANGED by this demotion

- Weather classification logic (`classify_weather`, all flag thresholds)
- `weather` field on `Plan` and `plan_json` storage
- `weather_snapshots` DB table and insert logic
- Open-Meteo fetch in `services/weather.py`
- `extreme_heat_risk` flag — still triggers `EmergencyBanner` at position #0
- **All safety logic is unchanged.** Demoting visual prominence ≠ disabling
  safety triggers. This must be stated explicitly in engineering comments.

---

## §G. User Stories (Updated)

### US-DASH-1 (UPDATE — replaces US-07 weather-first assumption)

**As a** parent opening the tournament dashboard,
**Given** a plan has been generated and no extreme heat risk exists,
**When** I open the dashboard,
**Then** the first visible content is the coach summary (PlanSummaryCard) and the
  match schedule strip — not a weather card — so I can immediately orient to
  the day plan.

### US-DASH-2 (NEW — multi-match schedule visibility)

**As a** parent with multiple matches entered for a tournament,
**Given** ≥2 matches have been added,
**When** I view the dashboard,
**Then** I see all matches in a horizontally-scrollable strip, can tap any chip to
  see that match's scenarios and food picks, and the currently-selected chip is
  visually highlighted.

### US-DASH-3 (NEW — glance-test)

**As a** parent during a tournament,
**Given** a plan has been generated,
**When** I open the dashboard at any time of day,
**Then** the NextActionCard immediately surfaces the next thing I should do (based
  on my plan's timeline and the current time) without me having to scroll or tap.

### US-DASH-4 (UPDATE — weather is ambient)

**As a** parent viewing the dashboard,
**Given** the weather is within normal safe parameters (no extreme heat risk),
**When** the dashboard renders,
**Then** weather data appears only as a compact 1-line pill below all actionable
  cards — I am not required to interact with it to access nutrition guidance.

**Given** `extreme_heat_risk == true`,
**When** the dashboard renders,
**Then** the `EmergencyBanner` renders at the very top of the screen, overriding
  all other layout decisions — the weather safety trigger is unaffected by the
  visual pivot.

---

## §H. Engineering Hand-Off

> Execute exactly in numbered order. §H is the build brief for Delegate 2.

### Backend (BD)

**1. Migration `0008_per_match_plans.sql`**

> ⚠️ PM VERIFICATION FINDING (2026-04-27):
> `db/supabase/migrations/0002_tables.sql` was read before scribing this section.
> **`plans.match_id` does NOT exist.** The `plans` table was created WITHOUT a
> `match_id` column. It has only: `id, tournament_id, plan_json, llm_summary,
> rules_constants_version, warnings, schedule_confidence, created_at, updated_at`.
> Migration 0007 added `plans.match_type` (nullable text) and `matches.doubles_format`.
> **No existing unique index on `plans(match_id, match_type)` exists.**
>
> Therefore migration 0008 must:
> (a) ADD the `match_id` column (it does not exist — cannot be index-only)
> (b) THEN create the unique index
>
> If the Planning Lead's §H.1 had said "add only the index" that would have been
> wrong. The column must be added first.

```sql
-- 0008_per_match_plans.sql
-- Adds match_id FK to plans so each plan can be anchored to a specific match.
-- Also adds a unique index to enforce one plan per (match_id, match_type) pair.
-- See NUTRITION_FIRST_IA_V1.md §E and §H.1.
--
-- NOTE: plans.match_type was added as nullable text in 0007_doubles_support.sql.
--       It is still nullable; null = legacy row = treat as 'singles'.
--       The unique index uses WHERE to exclude null match_ids (legacy rows).

ALTER TABLE public.plans
  ADD COLUMN IF NOT EXISTS match_id uuid REFERENCES public.matches (id)
    ON DELETE CASCADE;

COMMENT ON COLUMN public.plans.match_id IS
  'FK to the specific match this plan was generated for. '
  'NULL on legacy rows (pre-0008, generated per-tournament not per-match). '
  'See NUTRITION_FIRST_IA_V1.md §E.';

-- One plan per (match, match_type). WHERE excludes legacy null-match_id rows.
CREATE UNIQUE INDEX IF NOT EXISTS plans_match_id_match_type_uq
  ON public.plans (match_id, match_type)
  WHERE match_id IS NOT NULL;
```

Update `db/supabase/README.md` migration table with 0008 row.

**2. `rules/next_action.py` (NEW)**

```python
# rules/next_action.py
NEXT_ACTION_COPY_MAP: dict[str, str] = { ... }   # per §D
HEAT_SENSITIVE_KINDS: frozenset[str] = { ... }    # per §D

def derive_next_action(
    timeline: list[TimelineEvent],
    now: datetime,
    extreme_heat_risk: bool,
    lookahead_hours: int = 6,
) -> "NextAction | None": ...
```

- Implement algorithm per §D verbatim
- `recovery_fallback` kind is a string literal — no enum entry needed (not a DB value)

**3. `models/api.py` (EDIT)**

- Add `class NextAction(BaseModel)` with fields per §D
- `Plan`: add `match_id: UUID`, `next_action: Optional[NextAction] = None`
- Replace `GeneratePlanResponse` (was `{singles_plan, doubles_plan}`) with:
  ```python
  class GeneratePlanResponse(BaseModel):
      model_config = _CAMEL
      singles_plans: list[Plan] = []
      doubles_plans: list[Plan] = []
  ```

**4. `models/db.py` (EDIT)**

- `PlanRow`: add `match_id: Optional[UUID] = None`

**5. `routes/plans.py` (EDIT — generate_plan)**

Replace single-match-per-type logic with per-match loop:
```
for each match in tournament (ordered by display_order ASC):
    match_type = match.format or "singles"
    doubles_format = match.doubles_format
    → call existing scenarios/weather/food/llm/sanitize chain
    → set Plan.match_id = match.id
    → set Plan.match_type = match_type
    → call derive_next_action(plan.timeline, now=datetime.now(UTC), extreme_heat_risk)
    → attach NextAction to Plan.next_action
    → persist plan row (tournament_id, match_id, match_type, plan_json, llm_summary)
    → append to singles_plans or doubles_plans based on match_type

return GeneratePlanResponse(
    singles_plans=sorted(singles_plans, key=lambda p: match_start),
    doubles_plans=sorted(doubles_plans, key=lambda p: match_start),
)
```

**6. Tests (NEW under `apps/api/src/playfuel_api/tests/`)**

- `test_next_action.py` — 5 cases:
  - Event within 6h → correct NextAction returned
  - No future events in window → `recovery_fallback` returned
  - `extreme_heat_risk + match_start kind` → detail prepended with heat warning
  - `extreme_heat_risk + pre_match_meal kind` → detail NOT prepended (not in HEAT_SENSITIVE_KINDS)
  - `partner_coordination` kind → `"Confirm warm-up time with your player's partner"`
- `test_per_match_plans.py` — 4 cases:
  - Tournament with 2 singles + 1 doubles → `singlesPlans.length == 2`, `doublesPlans.length == 1`
  - Each plan has unique `matchId`
  - Each plan's `nextAction` is non-null (or null on recovery_fallback correctly)
  - `POST /generate` on singles-only tournament → `doublesPlans == []`
- **UPDATE existing tests** that decode old `{singlesPlan, doublesPlan}` envelope → new array shape

**7. Update `db/supabase/README.md`**: add 0008 row to migration table.

---

### iOS (FE)

**8. `Models/PlanEnvelope.swift` (EDIT)**

Replace singular `singlesPlan: Plan?` / `doublesPlan: Plan?` with arrays:

```swift
struct PlanEnvelope: Codable, Sendable {
    let singlesPlans: [Plan]   // ordered by match scheduledStart ASC
    let doublesPlans: [Plan]   // ordered by match scheduledStart ASC

    var hasBoth: Bool { !singlesPlans.isEmpty && !doublesPlans.isEmpty }
    var hasBothTypes: Bool { hasBoth }  // alias for existing call sites
    var anyPlan: Plan? { singlesPlans.first ?? doublesPlans.first }
    var allPlans: [Plan] { singlesPlans + doublesPlans }

    /// Returns the plan for the given match UUID, searching both arrays.
    func plan(for matchId: UUID) -> Plan? {
        allPlans.first { $0.matchId == matchId }
    }

    /// Returns the plan for the given match type (first in that type's array).
    /// Used for Singles|Doubles picker when hasBoth == true.
    func plan(for type: MatchType) -> Plan? {
        type == .singles ? singlesPlans.first : doublesPlans.first
    }

    /// Next upcoming plan by scheduledStart > now, across both types.
    func nextUpcomingPlan(now: Date = .now) -> Plan? {
        allPlans
            .filter { $0.scheduledStart > now }
            .sorted { $0.scheduledStart < $1.scheduledStart }
            .first
    }
}
```

**9. `Models/NextAction.swift` (NEW)**

```swift
struct NextAction: Codable, Hashable, Sendable {
    let title: String
    let detail: String
    let scheduledFor: Date?
    let kind: String
    let minsUntil: Int?
}
```

**10. `Models/Plan.swift` (EDIT)**

Add to `Plan`:
```swift
let matchId: UUID
let nextAction: NextAction?
```

Note: `matchId` replaces no existing property — it is new. No default needed
(call sites must pass explicitly — Session 2 lesson).

**11. `Views/ScheduleStripView.swift` (NEW)**

Per §C. Accepts:
```swift
struct ScheduleStripView: View {
    let allPlans: [Plan]                    // from envelope.allPlans
    @Binding var selectedMatchId: UUID?     // drives AppState
    let onAddMatch: () -> Void              // triggers showingCreateMatch
}
```

Internal: `MatchChip` sub-view per plan. Default selection logic applied in
`AppState.defaultMatchId(from:now:)` helper; the strip itself just renders.

**12. `Views/NextActionCard.swift` (NEW)**

Per §D. Accepts `nextAction: NextAction?`. Renders fallback copy when nil:
```swift
struct NextActionCard: View {
    let nextAction: NextAction?   // nil → show recovery_fallback copy inline
}
```

**13. `Views/WeatherCard.swift` (EDIT)**

Add `compact: Bool = false` init parameter:
- `compact == false` → existing body (unchanged)
- `compact == true` → 1-line `HStack` pill + `@State private var expanded = false`
  toggle; when `expanded`, render existing card body inline below the pill
- `expanded` defaults to `false` (per §F)

**14. `Views/TournamentDashboardView.swift` (EDIT)**

Re-order `planContent(plan:)` per §B locked table. New order inside `planContent`:
```
0. EmergencyBanner (if plan.weather.extremeHeatRisk)
1. (Picker at envelopeContent level — unchanged)
2. PlanSummaryCard (if plan.llmSummary != nil)
3. ScheduleStripView(allPlans: envelope.allPlans, selectedMatchId: $appState.selectedMatchId, onAddMatch: {...})
4. NextActionCard(nextAction: plan.nextAction)
5. FoodCardView (if plan.foodOptions.isNotEmpty)
6. scenariosSection(plan: plan)
7. Timeline button (if plan.timeline.isNotEmpty)
8. WeatherCard(weather: plan.weather, compact: true)
9. footerDisclaimer
```

Update `resolveActivePlan(from:)`: use `selectedMatchId` first, fall back to
first plan in `singlesPlans` or `doublesPlans`:
```swift
private func resolveActivePlan(from envelope: PlanEnvelope) -> Plan? {
    if let id = appState.selectedMatchId, let p = envelope.plan(for: id) { return p }
    return envelope.anyPlan
}
```

Update `.task` block: after resetting, set `appState.selectedMatchId` to
`envelope.nextUpcomingPlan()?.matchId ?? envelope.anyPlan?.matchId`.

**15. `State/AppState.swift` (EDIT)**

Add:
```swift
@Published var selectedMatchId: UUID? = nil
```

Add helper:
```swift
func defaultMatchId(from envelope: PlanEnvelope, now: Date = .now) -> UUID? {
    envelope.nextUpcomingPlan(now: now)?.matchId ?? envelope.anyPlan?.matchId
}
```

Remove `selectedMatchType` if the segmented Picker (singles/doubles tab)
is now derived from the selected match's `matchType` field rather than stored
separately. **Preserve `selectedMatchType` if it is needed for the doubles
Picker at the envelope level** — the `hasBoth` picker still operates at the
type level. Use `selectedMatchType` only for the type picker; `selectedMatchId`
for the specific-match selection within a type.

**16. `Networking/DTOs.swift` (EDIT)**

- `PlanEnvelopeDTO`: fields become `singlesPlans: [PlanCoreDTO]` / `doublesPlans: [PlanCoreDTO]`
- `PlanCoreDTO`: add `matchId: UUID`, `nextAction: NextActionDTO?`
- Add `NextActionDTO` struct + `.toModel()` → `NextAction`
- `PlanEnvelopeDTO.toModel()` maps arrays to `PlanEnvelope` arrays

**17. `Networking/Repository.swift` (EDIT)**

- `generatePlan(tournamentId:)` decodes `PlanEnvelopeDTO` (now with arrays)
- After decode, set `appState.selectedMatchId = appState.defaultMatchId(from: envelope)`
- No other changes to Repository needed

**18. `Data/FakeData.swift` (EDIT)**

Build a multi-match Dallas envelope:
- `dallasSinglesPlan1`: R16, 9:00 AM, match_id = UUID-A, nextAction with pre_match_meal
- `dallasSinglesPlan2`: QF, 1:00 PM, match_id = UUID-B, nextAction with match_start
- `dallasDoublesPlan1`: Doubles QF, 3:00 PM (best_of_3), match_id = UUID-C
- `dallasPlanEnvelope`: `singlesPlans: [dallasSinglesPlan1, dallasSinglesPlan2]`,
  `doublesPlans: [dallasDoublesPlan1]`
- Update all existing `#Preview` call sites that referenced singular `singlesPlan`
  / `doublesPlan` fields → use the new array fields

**19. `apps/ios/PlayFuel/README.md` (EDIT)**

Update Screen Tour section to new card order (§B locked table). Add sections:
- **ScheduleStripView** — purpose, chip layout, default selection rule
- **NextActionCard** — purpose, fallback behavior
- **WeatherPill** — why demoted, tap-to-expand behavior

---

## §I. DRAFT-Flagged Open Questions

| ID | Severity | Assumption | Justification |
|---|---|---|---|
| **OQ-IA-1** | Post-MVP | Status indicator `estimatedEnd` uses device-local time. Tournament timezone not stored — parents typically attend same-timezone events. Future: add `tournament.timezone` field. | Low immediate impact; same-day same-city assumption holds for MVP. |
| **OQ-IA-2** | Post-MVP | NextAction lookahead window = 0–6 hours. | Prevents surfacing stale "post-match recovery" copy at 9am next day; 6h covers a full long match including recovery. |
| **OQ-IA-3** | Post-MVP | WeatherPill expansion state is per-session, default collapsed. | Minimal state overhead; cost of re-tapping is trivial vs. persisting expansion across app launches. |
| **OQ-IA-4** | Post-MVP | WeatherPill is always rendered (not gated on weather flags). | Gives parent ambient temp awareness without demanding attention; aligns with "accessible but not demanding" principle §A.2. |
| **OQ-IA-5** | Post-MVP | Per-match plan generation is O(N matches); currently calls TemplateProvider (free). | ≤10 matches per tournament is the realistic ceiling for MVP. When real Anthropic/OpenAI replaces TemplateProvider, rate limiting will be needed. Flag as OQ for Phase 7. |
| **OQ-IA-6** | Post-MVP | `nextAction` "now" = server `now()` at generate time. iOS does NOT recompute client-side. | Known staleness if dashboard stays open across event boundary. Client-side recompute is a Phase 8+ refinement; requires Plan.timeline to be stored in a client-queryable format. |
| **OQ-IA-7** | Engineering | `NextAction.kind` taxonomy = existing `TimelineEventKind` values + `"recovery_fallback"` string literal. No new DB enum entry. | `TimelineEventKind` is API-contract only (no Postgres enum), per existing comment in `models/enums.py`. |
| **OQ-IA-8** | Engineering | Migration 0008 adds `plans.match_id` as nullable (NOT NULL would break legacy rows with no match context). Legacy rows are treated as singles-type, tournament-level plans. | All new plans post-0008 will always have match_id set by the generation loop; only pre-0008 rows will have null. |

---

## §J. Schema Verification Summary

> PM read `0002_tables.sql` and `0007_doubles_support.sql` before authoring §H.1.
> These findings replace the Planning Lead's assumed state ("If yes (expected) →
> migration adds only a unique index").

| Column | Table | Expected by brief | Actual state | Action in 0008 |
|---|---|---|---|---|
| `match_id` | `plans` | "probably exists" (verify) | **DOES NOT EXIST** | `ADD COLUMN IF NOT EXISTS match_id uuid REFERENCES public.matches(id) ON DELETE CASCADE` |
| `match_type` | `plans` | added as NOT NULL DEFAULT 'singles' | Added as **nullable text** (0007) — OQ-DBL-7 | No column change; 0008 just adds the unique index |
| Unique index on `(match_id, match_type)` | `plans` | "add if not exists" | **DOES NOT EXIST** | `CREATE UNIQUE INDEX IF NOT EXISTS ... WHERE match_id IS NOT NULL` |
| `doubles_format` | `matches` | added in 0007 | **EXISTS** (0007 shipped) | No action |
| `format` (match type) | `matches` | reuse existing | **EXISTS** since 0002 | No action |

---

## §K. Acceptance Criteria (for Validation)

1. `pytest` count ≥ 231 + new doubles/per-match tests (target +20 net new); Scenario 5 still xfail
2. `run_acceptance.py` exit 0
3. Migration 0008 idempotent; `plans.match_id` FK to `matches` with cascade; unique index present
4. `POST /v1/tournaments/{tid}/plans/generate` returns `{singlesPlans: [...], doublesPlans: [...]}` — arrays, not singular
5. Each Plan in the arrays has `matchId`, `matchType`, and `nextAction` populated
6. iOS: `PlanEnvelope` uses array fields; `ScheduleStripView` renders ≥1 chip per match; `NextActionCard` renders next action or fallback copy
7. iOS: `WeatherCard` renders as compact pill on dashboard by default; existing card body accessible via tap
8. iOS: Dashboard card order matches §B exactly — EmergencyBanner → [Picker] → PlanSummaryCard → ScheduleStrip → NextActionCard → FoodCard → Scenarios → Timeline button → WeatherPill → Disclaimer
9. iOS: EmergencyBanner still fires when `extreme_heat_risk == true`, positioned at absolute top of layout
10. iOS compiles file-level (no simulator required in sandbox)
11. 231 prior tests still pass (only test deltas for envelope shape change)
