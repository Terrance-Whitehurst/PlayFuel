# match-done-state-cards.md — Per-Match "Done" Toggle + State-Aware Card Deck
> Authority: Product Manager · Date: 2026-05-04
> Status: READY FOR ENGINEERING — execute §J verbatim after reading §I findings
> Ref: SAFETY_DISCLAIMERS.md, chain-menu-items.md (structural mirror), RULES_CONSTANTS_V1.md

---

## PM Verification Findings (pre-spec — read before any §)

> All key source files read before scribing. Pre-baked decisions verified against disk.
> Divergences flagged below. Engineering must read all findings before touching code.

| # | Finding | Source read | Impact on spec |
|---|---------|-------------|----------------|
| **V-1** | `recommended_oz` does NOT exist anywhere in the codebase — not on `Plan`, `ScenarioPlan`, `WeatherBlock`, `rules/constants.py`, or any iOS model. Brief proposed interpolating it on hydration cards. | `grep -rn "recommended_oz"` → no output | Cards must NOT interpolate this field. Hydration cards revised to static general-guidance copy, optionally heat-qualified using existing `WeatherBlock.flagHot` / `flagVeryHot`. Per §C of SAFETY_DISCLAIMERS.md a specific quantity would be a prohibited "hydration quantity as medical prescription." Static copy is both safer and simpler. |
| **V-2** | `is_done` and `done_at` are genuinely new columns on `matches`. The current schema (`0002_tables.sql`) has `actual_end_at timestamptz` (nullable, for analytics) but NO `is_done` or `done_at`. | `0002_tables.sql` | Migration 0017 needed. `actual_end_at` kept separate — different semantics (analytics vs. parent toggle). `is_done bool NOT NULL DEFAULT false` + `done_at timestamptz NULL`. |
| **V-3** | `MatchChip.matchStatus` is pure client-side time arithmetic (ISO timestamp + normal scenario duration). NOT a stored field. There is no server-driven done state yet. | `ScheduleStripView.swift L~161–173` | Once `Plan.isDone: Bool` is added (V-4), chip logic must check `plan.isDone == true` FIRST, short-circuiting the time arithmetic. `.inProgress` auto-derive still fires when `isDone == false AND now ∈ [start, start+duration]`. |
| **V-4** | `Plan` (both Pydantic `models/api.py` and Swift `Models/Plan.swift`) does NOT carry `is_done`. It is a genuinely new field on both. `build_plan_envelope()` (`rules/plan.py`) also needs a new `is_done: bool = False` parameter. | `models/api.py L~220–260`, `Plan.swift`, `rules/plan.py L~150–162` | `is_done: bool = False` added to Pydantic `Plan`. `isDone: Bool` added to Swift `Plan`. `build_plan_envelope()` gains `is_done: bool = False` kw arg, forwarded from `MatchRow.is_done`. |
| **V-5** | Route verb is `PUT` not `PATCH`; path is `/v1/tournaments/{tid}/matches/{mid}`. Brief said "PATCH /v1/matches/{id}". The existing `update_match` handler is a `PUT`. | `routes/matches.py L~207` | Spec corrects all references to use the correct verb and path. No new route needed — `MatchUpdate` is extended. |
| **V-6** | `MatchUpdate` (`routes/matches.py`, NOT `models/api.py`) needs `is_done` and `done_at` added. `MatchRow` (`models/db.py L~61–80`) also needs both fields so `plans.py` can forward them into `build_plan_envelope()`. | `routes/matches.py`, `models/db.py` | Three file edits for server-side state (routes/matches.py, models/db.py, rules/plan.py). Spec §J lists them explicitly. |
| **V-7** | "All Done" is genuinely additive to the `•••` menu. Currently the `Menu` in `TournamentDashboardView` toolbar has only one item: "Delete tournament" (destructive). "Mark day done" is a non-destructive addition. No structural conflict, but Engineering must add it as a non-destructive `Button` above the destructive one. | `TournamentDashboardView.swift L~83–93` | §E.4 specifies exact placement: non-destructive item first in the `Menu`. Confirmation alert logic in §E.4. |
| **V-8** | `nextActionablePlan` concept does NOT exist in `PlanEnvelope`. The brief said "define it in spec §E." `PlanEnvelope` has `nextUpcomingPlan(now:)` (time-based) but nothing `is_done`-aware. | `PlanEnvelope.swift` | New computed property `nextActionablePlan: Plan?` added to `PlanEnvelope` in §J. Logic: first plan in `allPlans` (ordered by scheduledStart ASC) where `isDone == false`; falls back to most-recently-done plan if all done. |
| **V-9** | `actual_end_at` exists on `matches` (migration 0002). Kept separate — different semantics: analytics (when a match physically ended) vs. parent toggle (parent marks it done). These columns coexist without conflict. Brief's recommendation to keep them separate is correct. | `0002_tables.sql L~137` | No change to `actual_end_at`. `is_done` and `done_at` are independent columns. |
| **V-10** | Card deck needs `PlanEnvelope` context to determine which deck to show — specifically, whether any undone plans remain after the current match. The active `Plan` alone is insufficient. | `PlanEnvelope.swift`, `TournamentDashboardView.swift planContent()` | `MatchStateDeckView` receives `activePlan: Plan` + `allPlans: [Plan]`. Deck state is derived in `MatchStateDeckView` from `activePlan.isDone` + `allPlans.contains(where: { !$0.isDone })`. |
| **V-11** | `WeatherBlock.flagHot` and `flagVeryHot` ARE available on `Plan.weather` at iOS render time. These drive heat-contextual card copy without inventing hydration quantities. | `models/api.py WeatherBlock`, `Models/Plan.swift` | Cards use static copy; iOS view appends heat suffix when `plan.weather?.flagHot == true || plan.weather?.flagVeryHot == true`. Encoded via `heat_aware: true` boolean on the card JSON — iOS decides the suffix text. |
| **V-12** | Correct field name for gap filtering is `ScenarioPlan.gapMinutes: Int?` (camelCase, "normal" scenario). The `min_gap_minutes` filter on between-match cards must compare against `activePlan.scenarioPlans.first(where: { $0.scenario == "normal" })?.gapMinutes`. | `models/api.py ScenarioPlan`, `Models/ScenarioPlan.swift` | Spec §E and §D encode `min_gap_minutes` on cards. iOS render logic uses normal-scenario `gapMinutes` for comparison. |

---

## §A — Scope

### User intent (verbatim)

> "I want to add a button that can tell you if a match is 'done' when you have it in the schedule. What I want is that next up, the recovery, to be focused before and after the match. Before the match, it is going to be before the match where it says maybe 'warm up'. Give it a slide show of little things that they can do. They can slide through with different cards of suggestions, and they can tap that that pops out.
>
> When they click 'done', that is giving suggestions based on in between that match. If they have a next match, it'll give suggestions based on that next match in that time. If they're done, then yeah.
>
> Please add a little more button. I could say 'done'. I can mark a day 'done' for all matches, so then you can give suggestions. All the suggestions can be about what you do for the next day, things like that."

### PM interpretation

Three surfaces in one feature:
1. **Per-match "Done" toggle** — a tappable button in each `MatchChip` that persists `is_done` to the backend. One tap done, one tap undo. No dialog.
2. **State-aware swipeable card deck** — 5 cards that change content based on the active plan's done state and whether a next match exists. Tapping any card expands it to a sheet.
3. **"Mark day done" button** — marks every match in the day done at once. Lives in the `•••` overflow menu.

---

## §B — Safety Boundary (load-bearing)

**This is the hardest constraint. Read it before writing any card copy.**

The PRD and SAFETY_DISCLAIMERS.md §A are explicit: PlayFuel is "not medical advice, nutrition therapy, or a substitute for a coach, physician, athletic trainer, or registered dietitian."

Card copy lives next to that boundary. These rules are non-negotiable:

### Allowed ✅

| Category | Example |
|----------|---------|
| General hydration reminders | "Sip water steadily. Don't wait until you're thirsty." |
| General eating timing | "Eat your pre-match snack 60–90 min before match time." |
| Vague general movement | "5–10 min of light movement to wake the body up. You know what works for your kid." |
| Equipment / logistics reminders | "Rackets, towel, water, snack, sunscreen. Anything missing?" |
| Mental/emotional general | "Take 3 deep breaths. One match at a time." |
| Recovery general | "Rest in the shade. Feet up if possible." |
| Sleep general | "Aim for 9+ hours tonight." |

### Forbidden ❌

| Prohibited | Why | SAFETY_DISCLAIMERS.md ref |
|------------|-----|--------------------------|
| "Do these stretches: quad stretch, calf stretch, shoulder rolls" | Specific physical instructions by body part | §C implied by §28 / §8.7 |
| "This will prevent cramps" | Medical causal claim | §C verbatim |
| "This will prevent heat illness" | Medical causal claim | §C verbatim |
| "Drink {X} oz of water every {N} minutes" | Hydration quantity as medical prescription | §C additional prohibited |
| "This is safe for every player" | Blanket safety claim | §C verbatim |
| "This is the right amount of sleep for a tennis player" | Prescriptive claim | §C implied |
| "Your player needs protein within 30 min of finishing" | Nutrition-therapy advice | §C implied by §8.7 |
| Any claim that a card item "prevents" or "guarantees" any outcome | Causal/guarantee claim | §C verbatim |

### Borderline rewrites (mandatory)

| Draft copy | Problem | Safe rewrite used in §D |
|------------|---------|------------------------|
| "Dynamic warm-up: jog, arm circles, ball-bounce" | Names specific movement drills | "5–10 min of light movement to wake the body up. You know what works for your kid." |
| "Do some stretching" | Vague but still prescriptive | "Easy movement or stretching if your kid likes it — nothing intense." |
| "Drink 16–20 oz of water with the meal" | Specific hydration quantity | "Sip water steadily. Don't wait until you're thirsty." |
| "Light electrolyte drink to replace sodium" | Nutrition-therapy advice | "If you brought electrolyte mix, now's a reasonable time — if tolerated." |

### Disclaimer footer — verbatim, must appear on every expanded card sheet

> "General tournament-day reminders. Not medical, nutrition, or training advice. Talk to your coach, physician, or athletic trainer for anything specific to your child."

This disclaimer is NOT in SAFETY_DISCLAIMERS.md (§A and §B are for the app-wide disclaimer and heat emergency). This card-level disclaimer is newly authored here. It must NOT be removed or paraphrased. It is the safety gate for this feature analogous to the chain-menu disclaimer in chain-menu-items.md §B.

---

## §C — State Model + DDL

### Migration 0017 — `match_done_state.sql`

```sql
-- =============================================================================
-- PlayFuel Migration 0017: Add is_done + done_at to matches
-- =============================================================================
-- Adds parent-visible match completion toggle to the matches table.
-- is_done is the user-facing toggle (parent marks a match done).
-- done_at records when is_done was first set to true (audit/sort only).
-- actual_end_at (existing) is preserved for future analytics (when the match
-- physically ended, not when the parent tapped "done").
-- =============================================================================

alter table public.matches
  add column if not exists is_done   boolean     not null default false,
  add column if not exists done_at   timestamptz null;

comment on column public.matches.is_done is
  'Parent-visible completion toggle. True when the parent has marked this match done. '
  'Does not correspond to actual match end time — see actual_end_at for that.';

comment on column public.matches.done_at is
  'Timestamp when is_done was first set to true. Cleared when is_done is set back to false. '
  'Nullable — null when is_done is false.';
```

**FK pattern:** No new FK columns. `is_done` and `done_at` are scalar columns on `matches` with no references to `public.users(id)` or `auth.users(id)`. The existing `tournament_id` FK covers ownership via RLS (one-hop: `matches.tournament_id → tournaments.user_id = auth.uid()`).

### done_at semantics

| Transition | done_at behavior |
|------------|-----------------|
| `false → true` (user taps Done) | Set `done_at = now()` on the server in `update_match` when `is_done` transitions to `true` AND `done_at` is not explicitly provided. |
| `true → false` (user taps Done again to undo) | Clear `done_at = null`. |
| `is_done` not in payload | `done_at` unchanged. |

`done_at` is used for: (a) audit trail; (b) sorting "most recently done" when all matches are done and the deck falls back to end-of-day. It is NOT used for display — the card deck cares only about `isDone: Bool`.

### "All done for the day" semantics

No separate `day_done` flag. Derived: `allMatchesInDayDone: Bool` is true when every plan in `PlanEnvelope.allPlans` has `isDone == true`. This is computed in `PlanEnvelope` (see §J) — no new DB column, no extra API call.

### MatchUpdate extension (routes/matches.py)

```python
class MatchUpdate(BaseModel):
    # ... existing fields unchanged ...
    # Done-state toggle — match-done-state-cards spec §C
    is_done: Optional[bool] = None
    done_at: Optional[datetime] = None   # client may override; server fills on false→true
```

**Route behavior** (`update_match`): when `body.is_done` is in the payload:
- `false → true`: if `body.done_at` is None, inject `done_at = datetime.utcnow()` into the DB payload.
- `true → false` (undo): force `done_at = None` in the DB payload (override any client value).
- `done_at` in payload without `is_done`: pass through as-is (rare; supports manual correction).

### MatchRow extension (models/db.py)

```python
class MatchRow(BaseModel):
    # ... existing fields unchanged ...
    # match-done-state-cards spec §C
    is_done: bool = False
    done_at: Optional[datetime] = None
```

**`select("*")` in `plans.py`** already fetches all columns — the new columns appear automatically once the migration runs. No query change needed.

### Plan model extension

**Pydantic (models/api.py):**
```python
class Plan(BaseModel):
    # ... existing fields unchanged ...
    # match-done-state-cards spec §C — forwarded from match.is_done at plan-gen time
    is_done: bool = False   # alias: isDone
```

**Swift (Models/Plan.swift):**
```swift
// match-done-state-cards spec §C
/// True when the parent has marked this match done.
/// NO stored-property default (Codable discipline — all call sites explicit).
let isDone: Bool
```

**`build_plan_envelope()` (rules/plan.py):**
```python
def build_plan_envelope(
    ...
    is_done: bool = False,     # NEW — forwarded from match.is_done
) -> Plan:
    ...
    return Plan(
        ...
        is_done=is_done,
    )
```

**`plans.py` call site:**
```python
plan = build_plan_envelope(
    ...
    is_done=match.is_done,    # NEW — forwarded from MatchRow
)
```

---

## §D — Card Content (15 cards)

### Card JSON schema

File: `apps/ios/PlayFuel/Sources/PlayFuel/Data/MatchStateCards.json` (bundled in iOS app — NOT in the API)

```json
{
  "version": "1.0.0",
  "cards": [
    {
      "id": "<slug>",
      "deck": "pre_match | between_matches | end_of_day",
      "title": "<short label>",
      "icon_sf_symbol": "<SF Symbol name>",
      "short": "<1-line card thumbnail copy>",
      "long": "<2–4 sentence expanded sheet copy>",
      "heat_aware": false,
      "heat_suffix": "<appended to long when flagHot || flagVeryHot — omit key if not heat_aware>",
      "min_gap_minutes": null
    }
  ]
}
```

**Field rules:**
- `heat_aware: true` → iOS appends `heat_suffix` to `long` when `plan.weather?.flagHot == true || plan.weather?.flagVeryHot == true`. Never interpolate specific quantities.
- `min_gap_minutes: N` → iOS hides this card when the normal scenario's `gapMinutes < N`. Use `null` for always-show.
- `short` must fit on a ~120pt card thumbnail (≤60 chars recommended).
- `long` is shown in the expanded sheet (2–4 sentences, ≤300 chars).
- All copy pre-audited against §B. See per-card safety notes below.

### Full 15-card registry

#### Deck A — `pre_match` (shown when `activePlan.isDone == false`)

```json
[
  {
    "id": "pre_match_hydrate",
    "deck": "pre_match",
    "title": "Hydrate",
    "icon_sf_symbol": "drop.fill",
    "short": "Sip water now. Don't wait until you're thirsty.",
    "long": "Sip water steadily in the time before the match. Small amounts often. Avoid large gulps right before you walk on court.",
    "heat_aware": true,
    "heat_suffix": " It's warm out today — staying on top of fluids matters even before you start playing.",
    "min_gap_minutes": null
  },
  {
    "id": "pre_match_snack_timing",
    "deck": "pre_match",
    "title": "Snack timing",
    "icon_sf_symbol": "fork.knife",
    "short": "Pre-match snack 60–90 min before match time.",
    "long": "If you haven't eaten yet, now's the window. Something easy — a banana, crackers, a small sandwich. Light enough to sit well on court.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "pre_match_movement",
    "deck": "pre_match",
    "title": "Light movement",
    "icon_sf_symbol": "figure.walk",
    "short": "5–10 min of light movement to wake the body up.",
    "long": "A short walk, easy jogging, whatever your kid usually does before a match. You know what works for them — now's the time. Nothing intense.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "pre_match_pack_check",
    "deck": "pre_match",
    "title": "Pack check",
    "icon_sf_symbol": "bag.fill",
    "short": "Rackets, towel, water, snack, sunscreen.",
    "long": "Quick bag check before heading to the court. Rackets, towel, water bottle, snack for after, sunscreen. Anything missing? Now's the time to grab it.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "pre_match_mental_prep",
    "deck": "pre_match",
    "title": "Mental prep",
    "icon_sf_symbol": "brain.head.profile",
    "short": "Take 3 deep breaths. One match at a time.",
    "long": "One match at a time. What's done in practice is done. Take 3 slow deep breaths, shake out the hands, and walk on court ready to compete.",
    "heat_aware": false,
    "min_gap_minutes": null
  }
]
```

**§B per-card notes (pre_match):**
- `pre_match_hydrate`: no quantity specified; "don't wait until thirsty" is general guidance; heat suffix is additive context, not prescriptive. ✅
- `pre_match_snack_timing`: "60–90 min" is timing guidance, not a medical prescription; examples are common sense items. ✅
- `pre_match_movement`: "light movement," "nothing intense," "you know what works" — deliberate parent-deference; no specific exercises named. ✅
- `pre_match_pack_check`: pure logistics. ✅
- `pre_match_mental_prep`: "3 slow deep breaths" is general mindfulness, not clinical intervention. ✅

---

#### Deck B — `between_matches` (shown when `activePlan.isDone == true` AND `allPlans.contains(where: { !$0.isDone })`)

```json
[
  {
    "id": "between_cool_down",
    "deck": "between_matches",
    "title": "Cool down",
    "icon_sf_symbol": "figure.cooldown",
    "short": "Walk for a few minutes off-court. Don't sit right away.",
    "long": "A short walk off-court helps the body start recovering. Don't plop down immediately — a few minutes of easy walking before you rest makes a difference.",
    "heat_aware": true,
    "heat_suffix": " Find shade as soon as you can — get out of direct sun.",
    "min_gap_minutes": null
  },
  {
    "id": "between_refuel",
    "deck": "between_matches",
    "title": "Refuel",
    "icon_sf_symbol": "fork.knife.circle",
    "short": "Check your food card — eat if the gap allows.",
    "long": "If you have time, eating something real between matches is worth it. Check your food card for nearby options. Something with carbs and a little protein. Keep it light.",
    "heat_aware": false,
    "min_gap_minutes": 45
  },
  {
    "id": "between_shade_rest",
    "deck": "between_matches",
    "title": "Rest in shade",
    "icon_sf_symbol": "sun.max.trianglebadge.exclamationmark.fill",
    "short": "Rest in shade. Feet up if possible.",
    "long": "Find a shaded spot and get off your feet. Elevate your legs if you can — lean them against a bag, a chair, whatever's around. Even 10 minutes makes a difference.",
    "heat_aware": true,
    "heat_suffix": " Today's conditions make shade especially important — don't skip this one.",
    "min_gap_minutes": null
  },
  {
    "id": "between_gear_reset",
    "deck": "between_matches",
    "title": "Gear reset",
    "icon_sf_symbol": "tshirt.fill",
    "short": "Dry shirt, dry socks, reapply sunscreen.",
    "long": "If you have a spare shirt or socks, now's the time to swap. Reapply sunscreen. A quick change out of wet gear helps more than it sounds.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "between_mental_reset",
    "deck": "between_matches",
    "title": "Mental reset",
    "icon_sf_symbol": "arrow.counterclockwise.circle",
    "short": "Last match is done. Reset for the next one.",
    "long": "Whatever happened in that match — good or bad — it's over. Take a breath, let it go, and start thinking about the next match fresh. One match at a time.",
    "heat_aware": false,
    "min_gap_minutes": null
  }
]
```

**§B per-card notes (between_matches):**
- `between_cool_down`: "short walk," "easy walking" — vague; no specific exercise protocol. ✅
- `between_refuel`: "something with carbs and a little protein, keep it light" — general guidance; no specific quantities, no nutrition-therapy claim; gated by `min_gap_minutes: 45` (hides when gap < 45). ✅
- `between_shade_rest`: general comfort guidance; "10 minutes makes a difference" is not a medical claim. ✅
- `between_gear_reset`: pure logistics. ✅
- `between_mental_reset`: general mental wellness tone; not clinical. ✅

---

#### Deck C — `end_of_day` (shown when all plans `isDone == true`)

```json
[
  {
    "id": "eod_hydrate",
    "deck": "end_of_day",
    "title": "Keep sipping",
    "icon_sf_symbol": "drop.circle.fill",
    "short": "Steady hydration through the evening.",
    "long": "Keep sipping water through the evening — not all at once, steadily. If you brought electrolyte mix and it's been a hot day, this is a reasonable time to use it if tolerated.",
    "heat_aware": true,
    "heat_suffix": " Today was warm — fluids through the evening matter more than usual.",
    "min_gap_minutes": null
  },
  {
    "id": "eod_movement_shower",
    "deck": "end_of_day",
    "title": "Easy movement & shower",
    "icon_sf_symbol": "shower.fill",
    "short": "Easy movement or stretching if your kid likes it, then shower.",
    "long": "Easy movement or stretching if your kid likes it — nothing intense. A shower helps the body feel like the day is done. Nothing structured required.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "eod_real_meal",
    "deck": "end_of_day",
    "title": "Real meal",
    "icon_sf_symbol": "fork.knife",
    "short": "A balanced meal within 1–2 hours of finishing.",
    "long": "Aim for a solid, balanced meal within 1–2 hours of finishing the day — something with protein, carbs, and vegetables if possible. Don't skip dinner because you're tired.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "eod_gear_tomorrow",
    "deck": "end_of_day",
    "title": "Prep for tomorrow",
    "icon_sf_symbol": "bag.fill.badge.plus",
    "short": "Lay out tomorrow's gear tonight.",
    "long": "Pack the bag tonight — rackets, towel, water bottle, snacks. Lay out the outfit. One less thing to think about in the morning when you're rushing out the door.",
    "heat_aware": false,
    "min_gap_minutes": null
  },
  {
    "id": "eod_sleep",
    "deck": "end_of_day",
    "title": "Sleep",
    "icon_sf_symbol": "moon.zzz.fill",
    "short": "Aim for 9+ hours tonight.",
    "long": "Earlier is better, especially if tomorrow has an early first match. Turn off screens a bit before bed if you can. Sleep is when recovery actually happens.",
    "heat_aware": false,
    "min_gap_minutes": null
  }
]
```

**§B per-card notes (end_of_day):**
- `eod_hydrate`: "if tolerated" language used for electrolytes; no quantity; "this is a reasonable time" not prescriptive. ✅
- `eod_movement_shower`: "if your kid likes it," "nothing intense," "nothing structured required" — all parent-deference language. ✅
- `eod_real_meal`: "1–2 hours" is timing guidance, not a medical prescription; "if possible" hedge on vegetables. ✅
- `eod_gear_tomorrow`: pure logistics. ✅
- `eod_sleep`: "9+ hours" is general recommendation (commonly cited for youth athletes); "if you can" hedge on screens. ✅

---

## §E — UX

### §E.1 — Card deck placement in `TournamentDashboardView.planContent()`

Insert **between position #3 and #4** in the existing locked layout order:

```
3.  ScheduleStripView           (existing)
    "View match details" link   (existing)
3.5 [NEW] MatchStateDeckView    ← INSERT HERE
4.  NextActionCard              (existing)
5.  FoodOptionDeck              (existing)
...
```

`MatchStateDeckView` receives `activePlan: Plan` and `allPlans: [Plan]` (both already available in `planContent(plan:envelope:)`).

### §E.2 — Deck state machine

| Deck | Condition | iOS derivation |
|------|-----------|---------------|
| `pre_match` | `activePlan.isDone == false` | Default state — before parent taps Done |
| `between_matches` | `activePlan.isDone == true` AND `allPlans.contains { !$0.isDone }` | Done but next match exists |
| `end_of_day` | `activePlan.isDone == true` AND `allPlans.allSatisfy { $0.isDone }` | All done for the day |

**Active plan resolution:** The "active plan" for the deck is `envelope.nextActionablePlan` — see `PlanEnvelope` extension in §J. This is the first plan with `isDone == false`, ordered by `scheduledStart` ASC. If all plans are done, it falls back to the most-recently-done plan (latest `scheduledStart`). This ensures the end-of-day deck always renders even when all matches are done.

### §E.3 — Swipeable carousel (TabView pattern)

```swift
struct MatchStateDeckView: View {
    let activePlan: Plan
    let allPlans: [Plan]
    
    private var visibleCards: [MatchStateCard] { /* filtered per deck + min_gap_minutes */ }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Section header
            Label(deckTitle, systemImage: deckIcon)
                .font(.headline)
                .padding(.horizontal, 16)
            
            TabView {
                ForEach(visibleCards) { card in
                    MatchStateCardThumbnail(card: card, plan: activePlan)
                        .onTapGesture { /* present MatchStateCardSheet */ }
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .frame(height: 120)
            .padding(.horizontal, 16)
        }
    }
}
```

- **`TabView` with `.page` style** — SwiftUI-native horizontal swipe + page dots. Matches the existing `ScrollView(.horizontal)` rhythm of `ScheduleStripView` and `scenariosSection`. Chosen over `ScrollView` because: (a) page dots are native "slideshow" affordance the user explicitly asked for; (b) `TabView(.page)` handles snap-to-card automatically.
- Card thumbnail height: **120pt** — enough for icon + title + 1-line short copy.
- `.indexViewStyle(.page(backgroundDisplayMode: .always))` — page dots always visible (not hidden when scrolling stops).
- Gap filter: cards with `min_gap_minutes > nil` are hidden when `normalScenario.gapMinutes < min_gap_minutes`. If ALL between-match cards are hidden by gap filter (gap < 45 min), show a single fallback card: `"Take a beat — sip water, breathe."` Never show an empty deck.

### §E.4 — Card thumbnail structure

```swift
struct MatchStateCardThumbnail: View {
    let card: MatchStateCard
    let plan: Plan

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: card.iconSfSymbol)
                    .foregroundStyle(.accent)
                Text(card.title)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(card.short)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(12)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
        .contentShape(RoundedRectangle(cornerRadius: 12))
    }
}
```

- `chevron.right` in top-right signals tap-ability — consistent with `WeatherCardView` affordance pattern.
- `.contentShape(RoundedRectangle(cornerRadius: 12))` ensures full card area registers taps without phantom hit-testing.

### §E.5 — Tap-to-expand sheet (mirrors `FoodOptionDetailSheet` pattern)

```swift
struct MatchStateCardSheet: View {
    let card: MatchStateCard
    let plan: Plan
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Icon + long copy
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: card.iconSfSymbol)
                            .font(.title2)
                            .foregroundStyle(.accent)
                        Text(longCopy)  // card.long + heat suffix if applicable
                            .font(.body)
                    }
                    
                    Divider()
                    
                    // Verbatim disclaimer (must not be removed or paraphrased)
                    Text("General tournament-day reminders. Not medical, nutrition, or training advice. Talk to your coach, physician, or athletic trainer for anything specific to your child.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .navigationTitle(card.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
    
    // Append heat suffix to long copy when plan.weather?.flagHot or flagVeryHot is true
    private var longCopy: String {
        guard card.heatAware,
              let weather = plan.weather,
              (weather.flagHot || weather.flagVeryHot),
              let suffix = card.heatSuffix else { return card.long }
        return card.long + suffix
    }
}
```

### §E.6 — Done button on MatchChip

```swift
// In MatchChip.body, replace the static statusView with a Done-aware version:
// Add to the VStack (Row 2 / Row 3 area):

HStack {
    statusView          // unchanged — clock / orange "In Progress" / green "Done"
    Spacer()
    DoneToggleButton(isDone: plan.isDone, onToggle: {
        // Calls parent closure → appState.toggleMatchDone(matchId, tournamentId)
    })
}
```

`DoneToggleButton`:
```swift
private struct DoneToggleButton: View {
    let isDone: Bool
    let onToggle: () -> Void
    
    var body: some View {
        Button(action: onToggle) {
            Image(systemName: isDone ? "checkmark.circle.fill" : "checkmark.circle")
                .foregroundStyle(isDone ? Color.green : Color.secondary)
                .font(.body)
        }
        .buttonStyle(.plain)   // prevent chip-level tap from intercepting
        .accessibilityLabel(isDone ? "Mark undone" : "Mark done")
    }
}
```

`DoneToggleButton` lives INSIDE the chip `VStack`. SwiftUI routes its taps directly to the `Button` action, NOT to the chip's `.onTapGesture`. No conflict with the existing chip-selection gesture.

**`AppState.toggleMatchDone(matchId:tournamentId:)` (new method):**
1. Determine new `isDone` value (toggle current plan's `isDone`).
2. Optimistically update the in-memory `Plan.isDone` in `currentPlanEnvelope` (instant UI response — no spinner).
3. Call `PUT /v1/tournaments/{tid}/matches/{mid}` with `{ "isDone": newValue }`.
4. On success: call `appState.generatePlan(for: tournamentId)` to refresh the full envelope.
5. On failure: revert optimistic update + show brief error toast (matches the delete-tournament pattern).

### §E.7 — "Mark day done" (All Done) button

Location: `TournamentDashboardView` toolbar `•••` overflow `Menu`.

```swift
Menu {
    // NEW — non-destructive, listed ABOVE the destructive delete
    Button {
        Task { await markDayDone() }
    } label: {
        Label("Mark day done", systemImage: "checkmark.circle.fill")
    }
    
    // EXISTING — destructive
    Button(role: .destructive) {
        showDeleteTournamentConfirm = true
    } label: {
        Label("Delete tournament", systemImage: "trash")
    }
} label: {
    Image(systemName: "ellipsis.circle")
}
```

**Confirmation alert**: shown ONLY when at least one match in the day has `scheduledStart > now()` AND `isDone == false`. If all matches are in the past OR all already done, no confirmation — just execute.

```swift
// Confirmation dialog text
"Mark all matches as done for today? This will show end-of-day suggestions."
// Buttons: "Mark Done" (default) + "Cancel"
```

**`markDayDone()` implementation:**
1. For each plan in `allPlans` where `!isDone`: call `PUT /v1/tournaments/{tid}/matches/{mid}` with `{ "isDone": true }` (concurrent, `withThrowingTaskGroup`).
2. On all success: call `appState.generatePlan(for: tournamentId)`.
3. On partial failure: surface a toast; partial state is acceptable (some marked done, some not).
4. After completion, deck transitions to `end_of_day` automatically (derived from plan state).

### §E.8 — nextActionablePlan (PlanEnvelope extension)

```swift
// New computed property on PlanEnvelope
/// The most contextually relevant plan for the card deck:
/// - First plan with isDone == false, ordered by scheduledStart ASC
/// - Falls back to most-recently-done plan (latest scheduledStart) when all done
/// - Falls back to anyPlan as last resort
var nextActionablePlan: Plan? {
    // 1. First undone plan
    let iso = ISO8601DateFormatter()
    if let first = allPlans.first(where: { !$0.isDone }) { return first }
    
    // 2. Most recently done plan
    let done = allPlans.compactMap { plan -> (Plan, Date)? in
        guard plan.isDone,
              let str = plan.scheduledStart,
              let date = iso.date(from: str) else { return nil }
        return (plan, date)
    }
    if let latest = done.max(by: { $0.1 < $1.1 })?.0 { return latest }
    
    // 3. Fallback
    return anyPlan
}
```

### §E.9 — Backwards compatibility

Existing tournaments where `is_done` is `false` (default) on all matches look IDENTICAL to today. `MatchChip` time-arithmetic still derives `.inProgress` and time-based `.done`. The card deck shows `pre_match` cards (correct default). No migration of existing data required.

---

## §F — Acceptance Criteria

- **AC#1 — Done toggle persists:** Tapping the `DoneToggleButton` on a MatchChip calls `PUT /v1/tournaments/{tid}/matches/{mid}` with `{ "isDone": true }`, the server sets `is_done=true` and `done_at=now()` in the DB, and the plan re-generates with `isDone: true`. MatchChip shows filled green checkmark. Card deck transitions `pre_match → between_matches` (or `end_of_day` if no undone plans remain) within one render cycle.

- **AC#2 — Undo is one tap, no dialog:** Tapping the filled checkmark again calls `PUT` with `{ "isDone": false }`, server clears `done_at=null`, plan re-generates with `isDone: false`. Deck reverts to `pre_match`. No confirmation dialog shown.

- **AC#3 — Between-match gap filter:** When the active plan's normal-scenario `gapMinutes < 45`, the `between_refuel` card (the only card with `min_gap_minutes: 45`) is hidden. The deck shows 4 visible cards. When gap ≥ 45, all 5 are shown. When a gap filter would leave the deck empty (edge case — gap < 45 with ONLY a refuel-gated card), a single fallback card `"Take a beat — sip water, breathe."` is shown. Deck is NEVER completely empty after Done is tapped.

- **AC#4 — All Done transitions to end_of_day:** Tapping "Mark day done" marks every match in `allPlans` done. After the plan re-generates, `allPlans.allSatisfy { $0.isDone }` is true, and the deck shows the `end_of_day` deck (5 cards: Keep sipping, Easy movement & shower, Real meal, Prep for tomorrow, Sleep).

- **AC#5 — Verbatim disclaimer always present on expanded card sheet:** Every expanded `MatchStateCardSheet`, regardless of which card or which deck, shows the verbatim disclaimer: `"General tournament-day reminders. Not medical, nutrition, or training advice. Talk to your coach, physician, or athletic trainer for anything specific to your child."` No code path renders an expanded card without this footer.

- **AC#6 — Zero regression on existing pre-done state:** When `is_done=false` on all plans (including all existing plans after migration), the chip renders with time-derived status (unchanged), the card deck shows `pre_match` (unchanged from a parent's perspective since the deck is new), and the `•••` menu adds "Mark day done" without removing "Delete tournament."

---

## §G — Open Questions

| ID | Severity | Description | Owner |
|----|----------|-------------|-------|
| **OQ-CARDS-1** | 🟡 Pre-TestFlight | Disclaimer copy review: is "Not medical, nutrition, or training advice. Talk to your coach, physician, or athletic trainer..." sufficient for a minor-athlete app? Queue with OQ-CHAIN-1, OQ-CHAIN-2, OQ-06 at the same TestFlight legal gate. **Not a blocker.** | PM + External counsel |
| **OQ-CARDS-2** | 🟢 Pre-TestFlight | Add a Swift unit test for the heat-suffix append path: when `plan.weather.flagHot == true`, `longCopy` in `MatchStateCardSheet` appends `heat_suffix`. Minor test gap, analogous to QA-CHAIN-1. | Engineering |
| **OQ-CARDS-3** | 🟢 Post-beta | Card-tap analytics (which card was expanded, which deck, match number in the day) deferred until Phase 8.x analytics framework. No tracking in MVP. | PM |

---

## §H — Explicitly Out of Scope

- **Per-card analytics** — which cards are viewed or expanded. Deferred.
- **Custom card authoring** — parents or coaches writing their own cards.
- **Push notifications** — "time to warm up!" X minutes before match.
- **Partial-match "still playing" state** — distinct from `in_progress` (time-derived). Out of scope.
- **Multi-day "All Done"** — marking an entire multi-day tournament done at once.
- **Celebration UI** — animations or confetti on marking done.
- **Card ordering control** — cards always appear in the order they appear in the JSON file.
- **LLM-generated cards** — direct §C violation of SAFETY_DISCLAIMERS.md. Hard reject.
- **Specific stretch or exercise instructions** — see §B forbidden list.
- **Allergen or nutrition labels on cards** — out of scope; cards are general reminders, not nutrition advice.

---

## §I — Verification Findings Summary

Captured above in the findings table at the top of this document (V-1 through V-12). Findings are cross-referenced in the relevant § sections.

**Most impactful findings to highlight for Engineering:**
- **V-1 (recommended_oz):** Do not add this field to any model. Card copy is static; heat suffix is the only dynamic element, and it uses existing `flagHot`/`flagVeryHot`. Do not invent a hydration field.
- **V-3+V-4 (MatchChip + Plan.isDone):** The chip currently has no `isDone` awareness. This requires changes to both the `Plan` model (new field) AND the `MatchChip` render logic (check `isDone` first).
- **V-5 (route verb):** Use `PUT /v1/tournaments/{tid}/matches/{mid}`, not `PATCH /v1/matches/{id}`.
- **V-10 (allPlans context):** `MatchStateDeckView` must receive both `activePlan` AND `allPlans`. Passing only `activePlan` is insufficient to determine which deck to show.

---

## §J — Engineering Scope

### Self-verification gate (run before reporting done)

```bash
# Backend
grep -n "is_done" apps/api/src/playfuel_api/models/db.py
# Expected: ≥1 match (MatchRow.is_done)

grep -n "is_done" apps/api/src/playfuel_api/models/api.py
# Expected: ≥1 match (Plan.is_done)

grep -n "is_done" apps/api/src/playfuel_api/routes/matches.py
# Expected: ≥2 matches (MatchUpdate field + update_match done_at logic)

grep -n "is_done" apps/api/src/playfuel_api/rules/plan.py
# Expected: ≥2 matches (build_plan_envelope param + Plan() constructor)

cd apps/api && python3.12 -m pytest src/playfuel_api/tests/ -v 2>&1 | tail -5
# Expected: ≥657 passed (646 current + ≥11 new), 0 failed

# iOS
grep -rn "isDone\|MatchStateDeck\|DoneToggleButton" apps/ios/PlayFuel/Sources/
# Expected: ≥10 matches across ≥4 files

cd apps/ios/PlayFuel && xcodebuild -scheme PlayFuel \
  -destination 'platform=iOS Simulator,name=iPhone 17' build 2>&1 | tail -3
# Expected: BUILD SUCCEEDED
```

### File-by-file scope

**Backend (7 items):**

| File | Change | Key detail |
|------|--------|------------|
| `db/supabase/migrations/0017_match_done_state.sql` | **NEW** | DDL from §C: `is_done bool NOT NULL DEFAULT false`, `done_at timestamptz NULL`, with column comments |
| `apps/api/src/playfuel_api/models/db.py` | **MODIFY** `MatchRow` | Add `is_done: bool = False` and `done_at: Optional[datetime] = None` after `opponent_player_id` |
| `apps/api/src/playfuel_api/models/api.py` | **MODIFY** `Plan` | Add `is_done: bool = False` (alias: `isDone`) at the bottom of the field list, after `scheduled_start` |
| `apps/api/src/playfuel_api/routes/matches.py` | **MODIFY** `MatchUpdate` + `update_match` | Add `is_done: Optional[bool] = None` + `done_at: Optional[datetime] = None` to `MatchUpdate`; in `update_match`, inject `done_at = datetime.utcnow()` when `is_done` transitions `false → true` and `body.done_at` is None; set `done_at = None` when `is_done = false` |
| `apps/api/src/playfuel_api/rules/plan.py` | **MODIFY** `build_plan_envelope` | Add `is_done: bool = False` keyword argument; forward to `Plan(is_done=is_done, ...)` constructor |
| `apps/api/src/playfuel_api/routes/plans.py` | **MODIFY** `generate_plan` loop | Pass `is_done=match.is_done` to `build_plan_envelope(...)` call (line ~457 area) |
| `apps/api/src/playfuel_api/tests/test_match_done_state.py` | **NEW** ≥11 tests | See test list below |

**Required backend tests (≥11):**

| Test | AC |
|------|----|
| `test_create_match_default_is_done_false` | AC#6 — new matches default to `is_done=false` |
| `test_update_match_mark_done_sets_done_at` | AC#1 — `is_done=true` → `done_at` is set |
| `test_update_match_undo_done_clears_done_at` | AC#2 — `is_done=false` → `done_at=null` |
| `test_update_match_done_idempotent` | AC#1 — marking already-done match done again is 200, not an error |
| `test_plan_carries_is_done_true` | AC#1 — plan generation includes `is_done: True` when match is done |
| `test_plan_carries_is_done_false` | AC#6 — plan generation includes `is_done: False` when match is not done |
| `test_build_plan_envelope_is_done_forwarded` | AC#1 — `build_plan_envelope(is_done=True)` → `Plan.is_done == True` |
| `test_matchrow_accepts_is_done_and_done_at` | V-6 — `MatchRow` parses both new fields without error |
| `test_update_match_done_at_explicit_override` | §C done_at semantics — client-provided `done_at` is respected |
| `test_update_match_no_is_done_in_payload_preserves_done_at` | §C — patching other fields doesn't clear `done_at` |
| `test_patch_is_done_without_scheduled_start_skips_date_range_validation` | Regression — date-range validation only fires when `scheduled_start` is in payload |

**iOS (7 items):**

| File | Change | Key detail |
|------|--------|------------|
| `Models/Plan.swift` | **MODIFY** | Add `let isDone: Bool` (no stored default; strict Codable discipline) |
| `Networking/DTOs.swift` | **MODIFY** `PlanDTO` | Add `isDone: Bool?`; `toModel()` maps `isDone ?? false` for back-compat with pre-done-state API responses |
| `Models/PlanEnvelope.swift` | **MODIFY** | Add `nextActionablePlan: Plan?` computed property per §E.8 |
| `Views/ScheduleStripView.swift` | **MODIFY** `MatchChip` | (a) Add `onToggleDone: () -> Void` closure param; (b) Replace `statusView` section with `HStack { statusView; Spacer(); DoneToggleButton(isDone: plan.isDone, onToggle: onToggleDone) }`; (c) Add `matchStatus` override: check `plan.isDone == true` FIRST → return `.done` before time arithmetic |
| `Views/TournamentDashboardView.swift` | **MODIFY** | (a) Insert `MatchStateDeckView` call between "View match details" link and `NextActionCard` in `planContent()`; (b) Add `toggleMatchDone()` method on `AppState` call; (c) Add "Mark day done" non-destructive item to `•••` `Menu` above "Delete tournament"; (d) Pass `onToggleDone` closure to `ScheduleStripView → MatchChip` chain |
| `Views/MatchStateDeckView.swift` | **NEW** | `MatchStateDeckView` (§E.3) + `MatchStateCardThumbnail` (§E.4) + `MatchStateCardSheet` (§E.5) + `DoneToggleButton` (§E.6) + `MatchStateCard` data model + JSON loader for `MatchStateCards.json` bundle resource |
| `Data/MatchStateCards.json` | **NEW** | 15 cards verbatim from §D |
| `Data/FakeData.swift` | **MODIFY** | All `Plan(...)` constructors must pass `isDone: false` once the Codable struct adds the field (build will fail without it; Codable discipline) |

**AppState extension (in `AppState.swift` or `AppState+MatchDone.swift`):**

```swift
// NEW method
func toggleMatchDone(matchId: UUID, tournamentId: UUID) async {
    // 1. Derive current isDone from envelope
    guard case .loaded(let envelope) = currentPlanEnvelope,
          let plan = envelope.plan(for: matchId) else { return }
    let newIsDone = !plan.isDone
    
    // 2. Optimistic update in-memory
    optimisticallySetIsDone(matchId: matchId, isDone: newIsDone)
    
    // 3. API call
    let success = await repository.updateMatchDone(
        matchId: matchId, tournamentId: tournamentId, isDone: newIsDone
    )
    
    // 4. Refresh plan on success; revert + toast on failure
    if success {
        await generatePlan(for: tournamentId)
    } else {
        optimisticallySetIsDone(matchId: matchId, isDone: !newIsDone)  // revert
        // show error toast (same pattern as delete-tournament error toast)
    }
}
```

**Note on `AppState` optimistic update:** `optimisticallySetIsDone` must update `currentPlanEnvelope` in-place. This is a new helper that replaces the matching `Plan.isDone` in the loaded envelope without triggering a full plan re-generation. This is what makes the chip respond instantly without a spinner.

### Test count expectation

| State | Passed |
|-------|--------|
| Current (post-chain-menu-items) | 646 |
| After this feature | ≥ 657 (646 + ≥11 new) |

---

*End of spec — 340 lines approx.*
