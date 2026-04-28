# PlayFuel — User Stories & Acceptance Criteria

> **Status:** Phase 0 draft · Authority: Product Manager · Last updated: 2026-04-26
> Constraints pulled from spec §9–10 (data model), §12 (API design), §21 (UX plan).

---

## US-01 · Sign In with Apple

**As a** parent of a junior tennis player,
**I want** to sign in using my Apple Account,
**so that** I don't have to create or manage a separate password.

### Acceptance Criteria

**Given** I open the app for the first time,
**When** I tap "Sign in with Apple",
**Then** the iOS Sign in with Apple sheet appears.

**Given** I complete Apple authentication,
**When** the app receives the Apple identity token,
**Then** the app sends the token to Supabase Auth, a session is created, and I am taken to the tournament list screen.

**Given** I have previously signed in,
**When** I reopen the app with a valid session,
**Then** I am taken directly to the tournament list (no re-authentication required).

**Given** the backend receives any authenticated request,
**When** processing it,
**Then** the user identity is extracted from the verified Supabase JWT — never trusted from the client payload (see §8.2 auth rule).

---

## US-02 · Create Player Profile

**As a** parent,
**I want** to create a profile for my junior player,
**so that** the app can personalize plans to my child's needs and constraints.

### Acceptance Criteria

**Given** I am signed in and have no player profiles,
**When** I navigate to create a player profile,
**Then** I see fields for: name (required), birth year or age range (optional), level (optional), dominant hand (optional), dietary notes (optional), hydration notes (optional), injury notes (optional).

**Given** I submit a profile with only the required name field,
**When** the profile is saved,
**Then** a `player_profiles` record is created with `user_id` matching my authenticated user ID (see §10 schema).

**Given** I submit a profile,
**When** it is saved,
**Then** injury notes, dietary notes, and hydration notes are all optional — saving without them must succeed.

**Given** another user attempts to read my player profile,
**When** the database query runs,
**Then** RLS policy (`auth.uid() = user_id`) prevents access (see §11).

---

## US-03 · Create Tournament

**As a** parent,
**I want** to create a tournament record with venue and dates,
**so that** the app has the location context needed for weather and food recommendations.

### Acceptance Criteria

**Given** I am signed in,
**When** I create a tournament,
**Then** I must provide: tournament name, start date. Venue name, address/location, and end date are optional but recommended.

**Given** I provide a venue address or location search result,
**When** the tournament is saved,
**Then** the `tournaments` record stores latitude and longitude for use by weather and places APIs (see §10 schema).

**Given** I save a tournament,
**When** the record is created,
**Then** `user_id` is set to my authenticated user ID and is not modifiable by the client.

**Given** another user queries tournaments,
**When** RLS is evaluated,
**Then** they see only their own tournaments (see §11).

**Given** I have saved a tournament,
**When** I return to the tournament list,
**Then** my tournament appears as a card showing name, dates, and status.

---

## US-04 · Add Match Times (Scheduled + Estimated Next Match)

**As a** parent,
**I want** to enter a scheduled match time and an estimated next match time,
**so that** the app can calculate scenario timings and parent pickup windows.

### Acceptance Criteria

**Given** I am viewing a tournament,
**When** I add a match,
**Then** I must provide: scheduled match time (required). Estimated next match time, round name, opponent name, court number are optional.

**Given** I enter a scheduled time of 9:00 AM and estimated next match of 1:00 PM,
**When** the match is saved,
**Then** the `matches` record stores `scheduled_time` as a timezone-aware timestamp and `estimated_next_match_time` as a timezone-aware timestamp (see §10 schema).

**Given** I enter a match without an estimated next match time,
**When** the plan is generated,
**Then** the plan generates without a gap calculation and the parent pickup strategy defaults to "No next match provided. Parent can wait until match ends." (see §19 pseudocode).

**Given** I save a match,
**When** the record is created,
**Then** `tournament_id`, `user_id`, and `scheduled_time` are all present and correctly linked.

---

## US-05 · Generate Plan

**As a** parent,
**I want** to tap "Generate Plan" for a tournament,
**so that** I receive a complete tournament-day timeline with scenario-based guidance.

### Acceptance Criteria

**Given** a tournament has at least one match with a scheduled time,
**When** I request plan generation via `POST /tournaments/{tournament_id}/generate-plan`,
**Then** the backend returns a `tournament_plans` record with a `plan_json` containing: summary, weather_flags, pre-match timeline events, and scenario plans for short/normal/long durations (see §13 output schema).

**Given** the plan is generated,
**When** I view it,
**Then** the timeline shows chronological events from wake-up through possible re-warm-up for a second match.

**Given** weather data is available for the tournament location,
**When** the plan is generated,
**Then** weather flags are evaluated and applied to hydration, meal, and warm-up guidance (see §17).

**Given** food options are available for the tournament location,
**When** the plan is generated,
**Then** nearby options with recommended orders appear in the plan (see §16).

**Given** a plan has been generated,
**When** I navigate away and return,
**Then** the most recent plan is retrievable via `GET /tournaments/{tournament_id}/plans/latest`.

---

## US-06 · View Short / Normal / Long Match Scenarios

**As a** parent,
**I want** to see three match-duration scenarios before the match starts,
**so that** I know what to do regardless of how long the match runs.

### Acceptance Criteria

**Given** a plan has been generated for a 9:00 AM match with estimated 1:00 PM next match,
**When** I view scenarios,
**Then** I see exactly three: Short (~75 min → ends ~10:15 AM), Normal (~120 min → ends ~11:00 AM), Long (~180 min → ends ~12:00 PM).

**Given** each scenario card,
**When** I view it,
**Then** I see: estimated match end time, gap before next match in minutes, food strategy, parent pickup strategy, recovery strategy, and re-warm-up timing (see §13 `ScenarioPlan` schema and §14).

**Given** the Short scenario with a 165-minute gap,
**When** the food strategy is determined,
**Then** it reads "There is enough time for a light meal, but avoid heavy/greasy foods." (gap > 150 min rule — see §19 pseudocode).

**Given** the Long scenario with a 60-minute gap,
**When** the parent pickup strategy is determined,
**Then** it indicates the parent should have portable food ready before the match ends (gap < 60 min rule — see §15).

**Given** a scenario is displayed,
**When** it is rendered,
**Then** no medical claims, invented restaurant names, or guaranteed performance outcomes appear.

---

## US-07 · View Weather Card

**As a** parent,
**I want** to see a weather summary and its impact on the plan,
**so that** I know how to adjust hydration and preparation for the conditions.

### Acceptance Criteria

**Given** the tournament has a location with latitude/longitude,
**When** weather data is fetched,
**Then** the app stores a `weather_snapshots` record with: temperature_f, humidity, wind_mph, precipitation_probability, and optionally uv_index (see §10 schema).

**Given** temperature is 88°F and humidity is 72%,
**When** weather flags are classified,
**Then** flags include "hot" and "humid" (see §17 `classify_weather` thresholds: hot ≥ 85°F, humid ≥ 65%).

**Given** "hot" and "humid" flags are set,
**When** the weather card is displayed,
**Then** the card shows: increased hydration emphasis, electrolyte note, shade/rest recommendation, and avoid-heavy-meals guidance (see §17 hot + humid adjustments).

**Given** precipitation probability ≥ 40%,
**When** the weather card is displayed,
**Then** a rain delay note appears with flexible meal timing and extra snack guidance (see §17 rain risk adjustments).

---

## US-08 · View Nearby Food Options

**As a** parent,
**I want** to see nearby food options with recommended orders,
**so that** I know what to pick up and when without researching it during the tournament.

### Acceptance Criteria

**Given** the tournament has a location,
**When** nearby food options are fetched,
**Then** 3–5 options are returned, each with: name, category, estimated drive time, and a recommended order template (see §16 food strategy).

**Given** a place is categorized as "fast_casual_bowl" (e.g., Chipotle),
**When** displayed,
**Then** the recommended order template matches the spec's restaurant template: "Chicken rice bowl with light beans, mild toppings, sauce on the side" (see §16 `RESTAURANT_TEMPLATES`).

**Given** a food option is displayed,
**When** rendered,
**Then** no claims are made that the food "prevents cramps," "guarantees performance," or is "safe for every player."

**Given** no food options are found near the tournament location,
**When** the food section is displayed,
**Then** the app shows bag-food fallback guidance (banana, pretzels, applesauce pouch, electrolyte drink) rather than an error or empty state.

---

## US-09 · Save and Recall a Plan

**As a** parent,
**I want** saved plans to be retrievable when I return to the app,
**so that** I can review the plan during the tournament without regenerating it.

### Acceptance Criteria

**Given** a plan has been generated,
**When** it is stored,
**Then** a `tournament_plans` record is created with `plan_json` (structured plan) and `llm_summary` (explanation text), linked to `tournament_id` and `user_id` (see §10 schema).

**Given** I close and reopen the app,
**When** I navigate to a tournament with a saved plan,
**Then** `GET /tournaments/{tournament_id}/plans/latest` returns the saved plan without regeneration.

**Given** I regenerate a plan,
**When** the new plan is saved,
**Then** a new `tournament_plans` record is created (versioned), and the latest endpoint returns the new version. Prior versions remain accessible by `plan_id`.

**Given** another user attempts to retrieve my plan,
**When** the database query runs,
**Then** RLS policy prevents access.

---

---

## US-DASH-1 · Nutrition-First Dashboard (UPDATE — replaces weather-first assumption)

> Source: `NUTRITION_FIRST_IA_V1.md §G` · Added: 2026-04-27

**As a** parent opening the tournament dashboard,
**I want** the first visible hero content to be the coaching summary and match schedule,
**so that** I can immediately orient to the day plan without scrolling past a weather report.

### Acceptance Criteria

**Given** a plan has been generated and `extreme_heat_risk == false`,
**When** I open the dashboard,
**Then** the first visible content below the optional safety banner is the LLM coach summary (PlanSummaryCard) and the match schedule strip — the weather card is NOT visible at the top of the page.

**Given** `extreme_heat_risk == true`,
**When** I open the dashboard,
**Then** the `EmergencyBanner` renders at the absolute top of the layout, overriding all other ordering decisions — this is non-negotiable per `SAFETY_DISCLAIMERS.md §B`.

**Given** the dashboard renders,
**When** I view it,
**Then** weather data is visible only as a compact 1-line pill at the bottom of the scrollable content, collapsed by default, accessible via tap.

---

## US-DASH-2 · Multi-Match Schedule Visibility (NEW)

> Source: `NUTRITION_FIRST_IA_V1.md §G` · Added: 2026-04-27

**As a** parent who has entered multiple matches for a tournament,
**I want** to see all my matches in a scrollable strip at the top of the dashboard,
**so that** I can quickly see the full day and tap into any match's plan.

### Acceptance Criteria

**Given** a tournament with ≥2 matches added,
**When** a plan has been generated and I open the dashboard,
**Then** I see a horizontally-scrollable strip with one chip per match, ordered by scheduled time, each showing: round label (or match number), scheduled time, match type (singles/doubles), and status (upcoming / in-progress / done).

**Given** I tap a match chip,
**When** the chip is selected,
**Then** the scenario cards, food options, next-action card, and timeline below all update to reflect that specific match's plan.

**Given** no matches have been added to the tournament,
**When** I view the strip area,
**Then** I see an empty-state card with a "Add your first match" call-to-action button.

---

## US-DASH-3 · Glance Test — Next Action (NEW)

> Source: `NUTRITION_FIRST_IA_V1.md §G` · Added: 2026-04-27

**As a** parent during a tournament,
**I want** the app to surface the most immediately actionable item when I open it,
**so that** I know what to do right now without scrolling or tapping.

### Acceptance Criteria

**Given** a plan has been generated and a future timeline event exists within the next 6 hours,
**When** I open the dashboard,
**Then** the NextActionCard shows the next upcoming event's title, a brief actionable detail, and how many minutes away it is — no taps required.

**Given** no future timeline event exists within the next 6 hours,
**When** I open the dashboard,
**Then** the NextActionCard shows fallback copy: "Recovery — Refuel within 30 min, see food options below."

**Given** `extreme_heat_risk == true` and the next action is a heat-sensitive event (match start, warm-up, hydration check),
**When** the NextActionCard renders,
**Then** the detail is prepended with "Extreme heat — extra hydration." (verbatim, never replacing the existing copy).

---

## US-DASH-4 · Weather as Ambient Context (UPDATE)

> Source: `NUTRITION_FIRST_IA_V1.md §G` · Added: 2026-04-27

**As a** parent who is already at the tournament venue and can feel the conditions,
**I want** weather data to be available but unobtrusive,
**so that** I can access it if I want it without it dominating the screen.

### Acceptance Criteria

**Given** non-emergency weather conditions (no extreme heat risk),
**When** the dashboard renders,
**Then** the weather is shown as a compact 1-line pill at position #8 in the card order (below scenarios, above the disclaimer footer), collapsed by default.

**Given** I tap the weather pill,
**When** it expands,
**Then** the full weather card body (temperature, humidity, flag pills, adjustment bullets) appears inline — no navigation, no sheet.

**Given** `extreme_heat_risk == true`,
**When** the dashboard renders,
**Then** the EmergencyBanner appears at position #0 (top of layout) and the weather pill still renders at position #8 — both are present simultaneously.

---

## Open Questions

1. **Multiple player profiles**: The spec shows a `player_profiles` table but does not specify whether the MVP UI supports creating more than one profile per user. The monetization tiers in §29 imply free = 1 profile, paid = multiple. Needs explicit scoping for Phase 2.
2. **Plan regeneration UX**: When a parent regenerates a plan (e.g., after weather changes), does the app warn them they are creating a new version? UX for versioned plans is unspecified.
3. **Scenario duration configurability**: §14 notes default durations (75/120/180 min) "should eventually depend on age group, format, surface, etc." but doesn't specify whether Phase 3 allows any configuration. Treating as hardcoded defaults for MVP.
4. **Offline access**: Whether saved plans must be accessible offline is not specified. Given tournament venue connectivity may be poor, this may be important for UX.
