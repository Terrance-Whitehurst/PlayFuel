# PlayFuel — Rules Constants v1

> **Version:** 1.0.0  
> **Status:** FROZEN (Phase 0 Task #2 complete)  
> **Authority:** Planning (author) · Engineering1 (OQ-05/13/14 resolutions)  
> **Last updated:** 2026-04-26  
> **Sources:** `PRD.md`, `USER_STORIES.md`, `MVP_SCOPE.md`, `SAFETY_DISCLAIMERS.md`, `SCENARIO_ACCEPTANCE.md`, Engineering1 OQ resolutions (session mog052owzfj7)

---

## Purpose & Non-Goals

This document is the deterministic source of truth for all constants, thresholds, bucket definitions, and contracts consumed by the PlayFuel rules engine (`generate_match_scenarios()`). Every numeric value, boundary condition, derived flag, and hard-coded string that drives plan generation must be traceable to a section here. The LLM explanation layer (Phase 6) receives structured output from the rules engine and must not override, re-derive, or invent any value defined in this document.

**Non-goals:** This document does not own iOS rendering logic, database schema definitions, API endpoint contracts, or LLM prompt engineering — except the hard-coded string registry (§H). Those are owned by their respective phase deliverables.

> **Read-only rule for the rules engine:** Phase 3 code imports this document's constants at initialization via a frozen version string (§J). No runtime code may mutate these constants. All changes require a version bump per §J change-control rules.

---

## §A — Scenario Durations

### A.1 Constants

Per Engineering1 resolution of **OQ-05**. Canonical location: `backend/app/rules/constants.py`.

```python
SCENARIO_DURATIONS_MIN = {
    "short":  75,   # minutes
    "normal": 120,  # minutes
    "long":   180,  # minutes
}
```

| Scenario | Duration (min) | Estimated end — 9:00 AM start |
|---|---|---|
| `short` | 75 | ~10:15 AM |
| `normal` | 120 | ~11:00 AM |
| `long` | 180 | ~12:00 PM |

Source: `SCENARIO_ACCEPTANCE.md` "Duration Defaults (from §14)"; `PRD.md` OQ-5.

### A.2 Override Hierarchy (v1.0.0)

| Level | Mechanism | Status in v1 |
|---|---|---|
| Hardcoded defaults | `SCENARIO_DURATIONS_MIN` in `constants.py` | ✅ Active |
| Player profile JSONB | `duration_overrides` kwarg on `generate_match_scenarios()` — reserved, unused | v1.1 (additive) |
| Age / format / surface lookup | Backend lookup table at plan-generation time | v1.2 (additive) |

v1.0.0 has **no per-profile or per-format overrides**. The function signature reserves `duration_overrides=None` to keep the interface stable across versions.

Source: Engineering1 OQ-05 resolution; `USER_STORIES.md` OQ-3; `MVP_SCOPE.md` deferrals table.

---

## §B — Gap-Bucket Boundaries

### B.1 Gap Definition

```
gap_minutes = estimated_next_match_start − (scheduled_match_start + scenario_duration_min)
```

Result is in minutes (integer or float). Negative values trigger the overrun contract (§G). Null `estimated_next_match_start` triggers `no_next_match` (§G.5).

> **Derivation note:** This formula is not stated verbatim in Phase 0 source docs; it is derived from the canonical scenario arithmetic in `SCENARIO_ACCEPTANCE.md` Scenarios 1–4.

### B.2 Food Strategy Buckets

Per Engineering1 resolution of **OQ-13**. **Pseudocode is canonical over prose.** All intervals are **half-open, lower-inclusive**: `gap ∈ [a, b)` means `a ≤ gap_minutes < b`.

| Bucket name | Range (min) | Food strategy text |
|---|---|---|
| `bag_only` | [0, 45) | "Use immediate bag food only: banana, pretzels, applesauce pouch, electrolyte drink, simple sandwich if tolerated." |
| `portable` | [45, 90) | "Use pre-bought portable food immediately after match. Avoid waiting in line." |
| `quick_pickup` | [90, 150) | "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal." |
| `light_meal` | [150, ∞) | "There is enough time for a light meal, but avoid heavy/greasy foods." |

Boundary cases: `gap = 45` → `portable` (not `bag_only`). `gap = 150` → `light_meal` (not `quick_pickup`). Buckets tile with no gaps and no overlap across [0, ∞).

Source: `SCENARIO_ACCEPTANCE.md` "Gap → Food Strategy Rules"; Engineering1 OQ-13 resolution (resolves `SCENARIO_ACCEPTANCE.md` OQ-1 and OQ-2).

### B.3 Parent Pickup Strategy Buckets

Per Engineering1 resolution of **OQ-13**.

| Bucket name | Range (min) | Parent pickup strategy text |
|---|---|---|
| `bring_portable` | [0, 60) | "Parent should have portable food ready before match ends." |
| `pickup_during_match` | [60, 120) | "If match is trending long, parent should pick up food during the final portion of the match if another trusted adult is present." |
| `wait_until_end` | [120, ∞) | "Parent can likely wait until the match ends before getting food." |

Boundary case: `gap = 60` → `pickup_during_match`. `gap = 120` → `wait_until_end`.

Source: `SCENARIO_ACCEPTANCE.md` "Parent Pickup Window Rules"; Engineering1 OQ-13 resolution.

### B.4 Worked Example — Dallas 9 AM / 1 PM (Canonical Demo Scenario)

```
Match 1 start:    9:00 AM
Match 2 start:    1:00 PM (estimated)
Total span:       240 minutes
```

| Scenario | Duration (min) | Match 1 end | Gap (min) | Food bucket | Pickup bucket |
|---|---|---|---|---|---|
| `short` | 75 | 10:15 AM | 165 | `light_meal` (165 ≥ 150) | `wait_until_end` (165 ≥ 120) |
| `normal` | 120 | 11:00 AM | 120 | `quick_pickup` (90 ≤ 120 < 150) | `wait_until_end` (120 ≥ 120) |
| `long` | 180 | 12:00 PM | 60 | `portable` (45 ≤ 60 < 90) | `pickup_during_match` (60 ≤ 60 < 120) |

> **OQ-13 impact on Normal scenario:** Pre-resolution ambiguity placed `gap = 120` in either `quick_pickup` or `light_meal` depending on source (prose vs. pseudocode). Resolution: `[90, 150)` is canonical → `gap = 120` → `quick_pickup`. This supersedes any pre-v1 document that cited `light_meal` for the Normal scenario.

Source: `PRD.md` §6 "Canonical Demo Scenario"; `SCENARIO_ACCEPTANCE.md` Scenario 1.

---

## §C — Hydration Cadence

> ⚠️ **[DRAFT — OQ-A]** Numeric oz/min quantities are **not present in any Phase 0 source document**. Trigger structure and event names are confirmed by Engineering1's foundation memo. All quantity fields are placeholders pending sports medicine review. See §I OQ-A.

### C.1 Trigger Events

All offsets relative to `scheduled_match_start` unless otherwise noted.

| Trigger ID | Event | Offset | Quantity | Notes |
|---|---|---|---|---|
| `HYD_PRE_1` | Pre-match hydration load | T−2h | `[DRAFT — OQ-A]` oz | Steady pre-load |
| `HYD_PRE_2` | Pre-match top-up | T−30m | `[DRAFT — OQ-A]` oz | Before warm-up begins |
| `HYD_CHANGEOVER` | During-match reminder | Every changeover | `[DRAFT — OQ-A]` oz | Present regardless of weather — see `SCENARIO_ACCEPTANCE.md` Scenario 1 |
| `HYD_POST` | Post-match recovery hydration | T+0 (match end) | `[DRAFT — OQ-A]` oz | |

### C.2 Weather Quantity Adjustments

| Weather flag | Adjustment | Quantity modifier |
|---|---|---|
| `hot` or `extreme_heat_risk` (§E.2) | Increase frequency; attach electrolyte note | `[DRAFT — OQ-A]` |
| `humid` | Attach electrolyte note (additive with `hot`) | `[DRAFT — OQ-A]` |
| `cold` | Maintain schedule; note warm fluids acceptable | `[DRAFT — OQ-A]` |

Source (trigger structure): Engineering1 §C foundation memo; `SCENARIO_ACCEPTANCE.md` Scenario 1 Must Include.

---

## §D — Pre-Match & Warm-Up Offsets

> ⚠️ **[DRAFT — OQ-C]** All values in this section are sourced from Engineering1's §D foundation memo. No Phase 0 source document provides explicit numeric values for these offsets. Values must be confirmed by Planning + Engineering1 before Phase 3 implementation. See §I OQ-C.

### D.1 Pre-Match Timeline

All offsets relative to `scheduled_match_start` (T = match start time).

| Event ID | Event | Offset | Duration | Notes |
|---|---|---|---|---|
| `WAKE_UP` | Wake-up | T−3h | — | [DRAFT — OQ-C] |
| `PRE_MATCH_MEAL` | Pre-match meal window | T−2.5h to T−3h | — | Window, not point-in-time [DRAFT — OQ-C] |
| `ARRIVE_SNACK` | Arrive at venue / light snack | T−60m | — | [DRAFT — OQ-C] |
| `DYNAMIC_WARMUP` | Dynamic warm-up | T−30m | 20 min | Active movement [DRAFT — OQ-C] |
| `COURT_WARMUP` | Court warm-up | T−10m | — | On-court with opponent [DRAFT — OQ-C] |

### D.2 Re-Warm-Up Between Matches

Re-warm-up offset is relative to `estimated_next_match_start`. Applies only when `gap_minutes ≥ 60`; otherwise `rewarm_up: null` per §G overrun contract.

| Event ID | Event | Offset from next match start | Duration | Notes |
|---|---|---|---|---|
| `REWARM_DYNAMIC` | Dynamic re-warm-up | T−30m | 20 min | [DRAFT — OQ-C] |
| `REWARM_COURT` | Court re-warm-up | T−10m | — | [DRAFT — OQ-C] |

Source: Engineering1 §D foundation memo; `SCENARIO_ACCEPTANCE.md` Scenario 3 Must Include ("re-warm-up timing specified for all three scenarios").

---

## §E — Weather Flag Thresholds

### E.1 Primary Flags

Per `SCENARIO_ACCEPTANCE.md` "Weather Flag Thresholds (from §17)". Implemented in `classify_weather()` — Phase 4.

| Flag | Field | Operator | Threshold | Unit |
|---|---|---|---|---|
| `hot` | `temp_f` | ≥ | 85 | °F |
| `very_hot` | `temp_f` | ≥ | 90 | °F |
| `humid` | `humidity` | ≥ | 65 | % |
| `cold` | `temp_f` | ≤ | 50 | °F |
| `windy` | `wind_mph` | ≥ | 15 | mph |
| `rain_risk` | `precipitation_probability` | ≥ | 40 | % |

Note: `very_hot` and `hot` are independent flags. A reading of 92°F sets **both** `hot` and `very_hot`.

Source: `SCENARIO_ACCEPTANCE.md` §17 table.

### E.2 Derived Flag

| Derived flag | Formula | Fires for canonical Scenario 2? | Where defined |
|---|---|---|---|
| `extreme_heat_risk` | `very_hot OR (hot AND humid)` | ✅ (88°F → `hot`; 72% → `humid`) | Engineering1 §E memo |

**[OQ-D]** Name `extreme_heat_risk` is Engineering1's proposal. Confirm naming convention before Phase 4. See §I.

When `extreme_heat_risk` is `true`, the plan **must** attach the heat-illness emergency text. Reference: `SAFETY_DISCLAIMERS.md §B`.

> ⚠️ **Do not reproduce `SAFETY_DISCLAIMERS.md §B` wording inline in this document or in any generated plan.** Consume it from `SAFETY_DISCLAIMERS.md §B` at runtime. The wording is pending legal review (§I OQ-11).

### E.3 Plan Adjustments by Flag

Required content when flags are active. Source: `SCENARIO_ACCEPTANCE.md` Scenarios 2 and 5; `MVP_SCOPE.md` deferrals table.

| Flag | Required plan adjustments |
|---|---|
| `hot` | Increased hydration emphasis, electrolyte note, shade/rest recommendation, avoid heavy meals, cool-down reminder |
| `very_hot` | Same adjustments as `hot` — `very_hot`-specific additions pending **OQ-D** / `SCENARIO_ACCEPTANCE.md` OQ-5 |
| `humid` | Electrolyte note (additive with `hot`) |
| `extreme_heat_risk` | All `hot` adjustments + attach `HEAT_EMERGENCY_TEXT` (§H.2) |
| `cold` | Note warm fluids acceptable |
| `windy` | Tactical / mental notes — **[DRAFT — deferred]** per `MVP_SCOPE.md` deferrals table |
| `rain_risk` | Flexible meal timing note, extra snacks guidance, warm/dry clothing reminder |

---

## §F — Food Taxonomy

### F.1 Strategy Buckets

Maps `gap_minutes` → food strategy. Full boundary definitions in §B.2.

| Bucket name | Gap range (min) | Lifecycle tag | Notes |
|---|---|---|---|
| `bag_only` | [0, 45) | `between_match` | No restaurant run; bag food only |
| `portable` | [45, 90) | `between_match` | Pre-bought; no waiting in line |
| `quick_pickup` | [90, 150) | `between_match` | Drive-through or grab-and-go |
| `light_meal` | [150, ∞) | `between_match` | Sit-down acceptable; avoid heavy/greasy |

### F.2 Lifecycle Tags

| Tag | Used for |
|---|---|
| `pre_match` | Nutrition guidance before the first match of the day |
| `between_match` | Nutrition guidance for the gap between Match 1 and Match 2 |
| `recovery` | Post-last-match nutrition guidance |

### F.3 Restaurant Template Registry

| Template name | Status | Recommended order text |
|---|---|---|
| `fast_casual_bowl` | ✅ Confirmed | "Chicken rice bowl with light beans, mild toppings, sauce on the side" |
| `sandwich_shop` | [DRAFT — OQ-B] | [DRAFT — OQ-B] |
| `grocery_prepared` | [DRAFT — OQ-B] | [DRAFT — OQ-B] |
| `breakfast_cafe` | [DRAFT — OQ-B] | [DRAFT — OQ-B] |

Source (`fast_casual_bowl`): `USER_STORIES.md` US-08 ("Chicken rice bowl with light beans, mild toppings, sauce on the side").

### F.4 Bag-Food Fallback Items

Applied when no nearby food options are returned (zero-results from Places API) **or** when `bag_only` bucket fires. This is the content of `BAG_FOOD_FALLBACK` (§H.3).

```
Banana, pretzels, applesauce pouch, electrolyte drink, simple sandwich if tolerated.
```

Source: `SCENARIO_ACCEPTANCE.md` "Gap → Food Strategy Rules" `bag_only` row; `USER_STORIES.md` US-08.

---

## §G — Negative-Gap Contract

Per Engineering1 resolution of **OQ-14**. HTTP response is always **200** regardless of `gap_status`. Overrun is a degraded plan, not a server error.

### G.1 gap_status Enum

Every `ScenarioPlan` object carries a `gap_status` field.

| Value | Condition | Notes |
|---|---|---|
| `ok` | `gap_minutes ≥ tight_threshold` and next match exists | `tight_threshold` = [DRAFT — OQ-E] |
| `tight` | `0 ≤ gap_minutes < tight_threshold` | Engineering1 proposes 30 min; see §I OQ-E |
| `overrun` | `gap_minutes < 0` | Match 1 end > Match 2 start |
| `no_next_match` | `estimated_next_match_start` is `null` | |

### G.2 Normal ScenarioPlan JSON Shape

```json
{
  "scenario": "normal",
  "duration_min": 120,
  "estimated_end": "11:00 AM",
  "gap_minutes": 120,
  "gap_status": "ok",
  "food_strategy": {
    "bucket": "quick_pickup",
    "text": "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal."
  },
  "pickup_strategy": {
    "bucket": "wait_until_end",
    "text": "Parent can likely wait until the match ends before getting food."
  },
  "rewarm_up": {
    "start_offset_min": -30,
    "duration_min": 20
  },
  "overrun_warning": null,
  "warnings": []
}
```

### G.3 Overrun ScenarioPlan JSON Shape

On `overrun`: food clamped to `bag_only`, pickup clamped to `bring_portable`, `rewarm_up` set to `null`.

```json
{
  "scenario": "long",
  "duration_min": 180,
  "estimated_end": "12:00 PM",
  "gap_minutes": -60,
  "gap_status": "overrun",
  "food_strategy": {
    "bucket": "bag_only",
    "text": "Use immediate bag food only: banana, pretzels, applesauce pouch, electrolyte drink, simple sandwich if tolerated."
  },
  "pickup_strategy": {
    "bucket": "bring_portable",
    "text": "Parent should have portable food ready before match ends."
  },
  "rewarm_up": null,
  "overrun_warning": {
    "code": "MATCH_OVERRUN",
    "severity": "high",
    "minutes_over": 60,
    "message": "Match 1 may not finish before Match 2's estimated start time. Alert the tournament desk."
  },
  "warnings": ["MATCH_OVERRUN"]
}
```

### G.4 Plan-Level warnings[] Aggregation

The top-level `Plan` object aggregates warning codes from all `ScenarioPlan` children.

```json
{
  "plan_id": "abc123",
  "tournament_id": "xyz456",
  "generated_at": "2026-04-26T09:00:00Z",
  "warnings": ["MATCH_OVERRUN"],
  "scenario_plans": [
    {
      "scenario": "short",
      "gap_status": "ok",
      "overrun_warning": null,
      "warnings": []
    },
    {
      "scenario": "normal",
      "gap_status": "overrun",
      "overrun_warning": {
        "code": "MATCH_OVERRUN",
        "severity": "high",
        "minutes_over": 0,
        "message": "Match 1 may not finish before Match 2's estimated start time. Alert the tournament desk."
      },
      "warnings": ["MATCH_OVERRUN"]
    },
    {
      "scenario": "long",
      "gap_status": "overrun",
      "overrun_warning": {
        "code": "MATCH_OVERRUN",
        "severity": "high",
        "minutes_over": 60,
        "message": "Match 1 may not finish before Match 2's estimated start time. Alert the tournament desk."
      },
      "warnings": ["MATCH_OVERRUN"]
    }
  ]
}
```

### G.5 no_next_match JSON Shape

```json
{
  "scenario": "normal",
  "duration_min": 120,
  "estimated_end": "11:00 AM",
  "gap_minutes": null,
  "gap_status": "no_next_match",
  "food_strategy": null,
  "pickup_strategy": {
    "bucket": null,
    "text": "No next match provided. Parent can wait until match ends."
  },
  "rewarm_up": null,
  "overrun_warning": null,
  "warnings": []
}
```

Source: `USER_STORIES.md` US-04 ("the parent pickup strategy defaults to 'No next match provided. Parent can wait until match ends.'").

### G.6 iOS Render Contract

| Condition | iOS UI element |
|---|---|
| `gap_status = "overrun"` on any `ScenarioPlan` | Amber banner on that scenario card |
| `Plan.warnings` contains `"MATCH_OVERRUN"` | "Schedule conflict" pill on plan envelope |
| `gap_status = "no_next_match"` | No gap section rendered; pickup text with neutral styling |
| `gap_status = "tight"` | [DRAFT — OQ-E] Yellow indicator; exact UI TBD |
| HTTP response | Always **200** for all `gap_status` values |

Source: Engineering1 OQ-14 resolution.

---

## §H — Hard-Coded Strings Registry

> ⚠️ **These strings are never LLM-generated.** They are compiled into the backend. The LLM must not modify or re-interpret them at runtime. Changes require a version bump (§J).

| Constant name | Type | Defined |
|---|---|---|
| `OVERRUN_MESSAGE` | `str` | §H.1 — full string below |
| `HEAT_EMERGENCY_TEXT` | `str` | §H.2 — reference only |
| `BAG_FOOD_FALLBACK` | `str` | §H.3 — full string below |

### H.1 OVERRUN_MESSAGE

```python
OVERRUN_MESSAGE = (
    "Match 1 may not finish before Match 2's estimated start time. "
    "Alert the tournament desk."
)
```

Source: `SCENARIO_ACCEPTANCE.md` Scenario 4 Must Include (overrun warning text). Editorial note: "the" added before "tournament desk" for grammatical consistency — not a semantic change.

### H.2 HEAT_EMERGENCY_TEXT

> ⚠️ **Do not reproduce this string here.** The canonical, legally-pending wording lives in `SAFETY_DISCLAIMERS.md §B` ("Hard-Coded Emergency Guidance"). The rules engine must import it from `SAFETY_DISCLAIMERS.md §B` at runtime.
>
> **Pre-launch blocker (OQ-11):** `SAFETY_DISCLAIMERS.md §B` explicitly flags this wording for attorney review before App Store submission. `HEAT_EMERGENCY_TEXT` is draft until OQ-11 is resolved.

Reference: `SAFETY_DISCLAIMERS.md §B`.

### H.3 BAG_FOOD_FALLBACK

```python
BAG_FOOD_FALLBACK = (
    "Use immediate bag food only: banana, pretzels, applesauce pouch, "
    "electrolyte drink, simple sandwich if tolerated."
)
```

Source: `SCENARIO_ACCEPTANCE.md` "Gap → Food Strategy Rules" `bag_only` row (verbatim); `USER_STORIES.md` US-08.

---

## §I — Open Questions Carried Forward

| ID | Question | Blocks phase | Owner |
|---|---|---|---|
| OQ-A | Hydration cadence — what are the specific fluid quantities (oz) per trigger event (`HYD_PRE_1`, `HYD_PRE_2`, `HYD_CHANGEOVER`, `HYD_POST`)? Must be grounded in sports medicine source, not inferred. | Phase 6 | Engineering1 / Planning |
| OQ-B | Restaurant template confirmed orders for `sandwich_shop`, `grocery_prepared`, `breakfast_cafe`. Only `fast_casual_bowl` is grounded in source docs (`USER_STORIES.md` US-08). | Phase 5 | Engineering1 / Planning |
| OQ-C | Pre-match and warm-up offset values — are wake T−3h, meal T−2.5–3h, arrive T−60m, dynamic warm-up T−30m/20min, court warm-up T−10m grounded in any authoritative source, or are they Engineering1 proposals? Confirm before Phase 3 cutover. | Phase 3 | Planning Lead |
| OQ-D | `extreme_heat_risk` flag name — Engineering1's proposal. Confirm naming convention. Also confirm whether `very_hot` alone (without `humid`) triggers additional adjustments beyond `hot` adjustments. Resolves `SCENARIO_ACCEPTANCE.md` OQ-5. | Phase 4 | Engineering1 |
| OQ-E | `tight` gap threshold — Engineering1 proposes `< 30 min` but no Phase 0 source defines this value. Confirm threshold and iOS render contract for `tight` state before Phase 3 delivery. | Phase 3 | Engineering1 |
| OQ-F | Rain-delay handling — what does `generate_match_scenarios()` return when `rain_delay_risk` flag is `true` and schedule is uncertain? Defers `SCENARIO_ACCEPTANCE.md` OQ-4. | Phase 4 | Engineering1 / Planning |
| OQ-G | `schedule_confidence` field — rain-delay scenario (Scenario 5) requires a mechanism to signal schedule uncertainty when `estimated_next_match_time` is `null` + `rain_risk` is `true`. Define the data model field before Phase 2 schema migration. Defers `SCENARIO_ACCEPTANCE.md` OQ-4. | Phase 2 (schema) | Engineering1 / Backend Dev |
| OQ-06 | COPPA handling for under-13 players — spec recommends parent-owned accounts only. Legal confirmation required before any public launch. App targets players 10–18. **Pre-launch blocker.** Source: `PRD.md` OQ-6; `SAFETY_DISCLAIMERS.md §F`. | Pre-launch | Legal / Founder |
| OQ-11 | Legal review of heat-illness emergency wording — `SAFETY_DISCLAIMERS.md §B` explicitly flags this for attorney review. `HEAT_EMERGENCY_TEXT` (§H.2) is draft until resolved. **Pre-launch blocker.** Source: `SAFETY_DISCLAIMERS.md` OQ-1. | Pre-launch | Legal / Founder |

---

## §J — Versioning & Change Control

### J.1 Version Declaration

```python
RULES_CONSTANTS_VERSION = "1.0.0"
```

### J.2 Import Rule for Phase 3 Rules Engine

```python
from backend.app.rules.constants import RULES_CONSTANTS_VERSION

assert RULES_CONSTANTS_VERSION == "1.0.0", (
    f"Rules constants version mismatch: expected 1.0.0, got {RULES_CONSTANTS_VERSION}"
)
```

Fail fast — do not degrade silently on version mismatch.

### J.3 Change-Control Rules

| Change type | Required approval | Version bump |
|---|---|---|
| Typo / formatting only | Planning sign-off | Patch: `1.0.0 → 1.0.1` |
| Boundary value change (§B, §C, §D, §E) | Planning + Engineering1 joint sign-off | Minor: `1.0.x → 1.1.0` |
| New section or structural change | Planning + Engineering1 joint sign-off | Minor or major |
| Resolution of any `[DRAFT]` value (§C, §D, §F) | Planning + Engineering1 joint sign-off | Minor: `1.x.y → 1.(x+1).0` |
| Pre-launch legal blocker (OQ-06, OQ-11) | Legal / Founder approval + Planning record; update §H | Patch or minor |

### J.4 DRAFT Sections Summary

All `[DRAFT]` values that must be resolved before their blocking phase:

| Section | Draft item | Blocking phase | OQ |
|---|---|---|---|
| §C Hydration cadence | Fluid quantities (oz) for all 4 trigger events | Phase 6 | OQ-A |
| §D Pre-match offsets | All offset values | Phase 3 | OQ-C |
| §E `extreme_heat_risk` | Flag name + `very_hot`-specific adjustments | Phase 4 | OQ-D |
| §F Restaurant templates | `sandwich_shop`, `grocery_prepared`, `breakfast_cafe` orders | Phase 5 | OQ-B |
| §G `tight` gap state | Threshold value + iOS render contract | Phase 3 | OQ-E |
| §H `HEAT_EMERGENCY_TEXT` | Pending attorney review | Pre-launch | OQ-11 |
