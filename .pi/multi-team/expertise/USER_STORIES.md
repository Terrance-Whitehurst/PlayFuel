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

## US-DASH-5 · Background Info One Tap Away (NEW)

> Source: `HEADER_BUBBLES_V1.md §E` · Added: 2026-04-27

**As a** parent opening the app in the venue parking lot,
**I want** to see the actionable schedule and next step immediately on the dashboard,
**so that** I'm not buried in explanatory text before I can act.

### Acceptance Criteria

**Given** the dashboard has loaded a plan,
**When** I open the Tournament Dashboard,
**Then** the area above the match schedule strip shows only a row of two small icon buttons (Plan Summary, Weather) — no inline text cards.

**Given** I want to read the coach voice summary,
**When** I tap the Plan Summary bubble (pencil-and-bubble icon),
**Then** a sheet presents with title "Today's Plan" showing the full summary, weather note, food note, and safety disclaimer — without leaving the dashboard.

**Given** I want to see detailed weather data,
**When** I tap the Weather bubble (cloud-and-sun icon),
**Then** a sheet presents with title "Conditions" showing the full weather card (temperature, humidity, flags, adjustments).

**Given** I dismiss either sheet,
**When** I drag the sheet down (iOS standard),
**Then** the sheet closes and I return to the dashboard scroll position I was at before.

---

## US-DASH-6 · Extreme Heat Warning — Unavoidable but Not Overwhelming (NEW)

> Source: `HEADER_BUBBLES_V1.md §E` · Added: 2026-04-27

**As a** parent whose child is playing in extreme heat,
**I want** to see an unmissable heat warning without having to navigate to it,
**so that** I am never unaware of a heat emergency even if I don't read the dashboard carefully.

### Acceptance Criteria

**Given** `extreme_heat_risk == true`,
**When** the dashboard renders,
**Then** a full-width red 1-line strip appears at the very top reading "⚠️ Extreme heat — tap for guidance" — before any match schedule, picker, or bubble row.

**Given** I tap the red EmergencyStrip,
**When** the sheet opens,
**Then** it displays `HardCodedStrings.heatEmergencyText` verbatim (never paraphrased) followed by `HardCodedStrings.userDisclaimer` verbatim.

**Given** `extreme_heat_risk == false`,
**When** the dashboard renders,
**Then** the red strip is not shown — the dashboard top begins with the segmented picker (if both match types exist) or the bubble row directly.

**Given** `extreme_heat_risk == true` AND `envelope.hasBothTypes == true`,
**When** the dashboard renders,
**Then** the EmergencyStrip appears ABOVE the Singles/Doubles segmented picker (not below it) — heat warning is always the topmost visible element.

---

## US-FOOD-1 · Food Deck Glanceability (Phase 8.3)

**As a** parent at a tennis tournament,
**I want** to see nearby food options as a swipeable deck of cards (not a wall of text),
**so that** I can see multiple options at a glance without scrolling through a long list.

**Given** the plan has at least 1 non-bag-only food option,
**When** I scroll to the food section of the dashboard,
**Then** I see a horizontal scroll-snap deck of cards, each showing restaurant name, category, and drive time. The edge of the next card is visible, signaling more options.

**Given** the plan has no nearby food (bag_fallback_only),
**When** I scroll to the food section,
**Then** I see a single full-width bag-food fallback card with the verbatim HardCodedStrings.bagFoodFallback text.

---

## US-FOOD-2 · Per-Restaurant Structured Suggestions (Phase 8.3)

**As a** parent deciding what to order at Starbucks or any nearby restaurant,
**I want** to tap the card and see structured suggestions — what to order, what to drink, what to avoid, and timing notes,
**so that** I do not have to parse a single wall of text.

**Given** I tap a food option card in the deck,
**When** the detail sheet opens,
**Then** I see structured sections for what to order, add-ons, drinks, and items to avoid. Empty sections are hidden. A timing note and allergy disclaimer appear at the bottom.

**Given** the food option is a DRAFT template (e.g. Starbucks, Jimmy John's),
**When** the detail sheet opens,
**Then** a grey pill reading "Suggestions in development — confirm with your athlete" is visible at the top of the sheet.

---

## US-MAP-1 · Venue Map Overview (Phase 8.3)

**As a** parent unfamiliar with the tournament venue and surrounding area,
**I want** to tap a Map bubble to see a real interactive map centered on the tournament location with food option pins,
**so that** I can orient myself and see where food is relative to the courts.

**Given** I tap the Map bubble (third bubble in the header row),
**When** the map sheet opens,
**Then** I see a MapKit map centered on the tournament venue with a blue tennis-ball pin at the venue and orange fork-and-knife pins at nearby food locations.

**Given** no food options have coordinates,
**When** the map sheet opens,
**Then** only the venue pin is shown — no error state required.

---

## US-MAP-2 · Food Pin Drill and Directions (Phase 8.3)

**As a** parent who sees a food pin on the venue map,
**I want** to tap the pin to see that restaurant's structured suggestions, and then optionally get turn-by-turn directions,
**so that** I can decide and navigate without leaving the context I am in.

**Given** I tap an orange food pin on the venue map,
**When** the food detail sheet opens,
**Then** I see the same structured suggestions as tapping the card in the deck. An "Open in Maps" button at the bottom launches Apple Maps with directions to that restaurant.

---

---

## US-PLAYER-1 · Player Scouting Log

> Source: `PLAYER_SCOUTING_V1.md §F` · Added: 2026-04-28

**As a** parent of a junior tennis player,
**I want** to keep a running log of opponents I've tracked — with notes from before a match, during observation, or after playing them —
**so that** I can recall what I know about a player before sending my child onto the court against them.

### Acceptance Criteria

**Given** I navigate to Profile → Players,
**When** I tap the "+" button,
**Then** I can add a player with a required display name and optional club and city fields.

**Given** I have added a player,
**When** I tap their row,
**Then** I see the PlayerDetailView with their existing notes in reverse-chronological order.

**Given** I tap "+ Add Note" on a player's detail view,
**When** the AddPlayerNoteSheet opens,
**Then** I can select a source (Heard from others / I observed this / After we played), type a body (≤ 2000 characters), and save.

**Given** I save a note with body text exceeding 2000 characters,
**When** the API processes the request,
**Then** the API returns 422 and the note is not saved.

**Given** another user attempts to read my player or notes,
**When** the database query runs,
**Then** RLS prevents access — they see nothing.

---

## US-PLAYER-2 · Match Opponent Picker

> Source: `PLAYER_SCOUTING_V1.md §E.4` · Added: 2026-04-28

**As a** parent creating a match,
**I want** to search for an existing player from my roster as the opponent, or add a new one inline,
**so that** the match is linked to the player's scouting notes and future plan generation can use that context.

### Acceptance Criteria

**Given** I open MatchCreateView and tap the opponent field,
**When** the player search view appears,
**Then** I see a search-as-type list of my existing players with display name and club/city subtitle.

**Given** I type a name that partially matches an existing player,
**When** the list filters,
**Then** only matching players appear; "+ Add \"<typed name>\" as new player" appears at the bottom.

**Given** I tap an existing player in the search results,
**When** I return to MatchCreateView,
**Then** both `opponent_player_id` (FK) and `opponentLabelText` (display fallback) are populated.

**Given** I tap "+ Add new player" from the search view,
**When** AddPlayerSheet opens and I save a name,
**Then** the new player is created and returned, and both `opponent_player_id` and `opponentLabelText` are populated in MatchCreateView.

**Given** I leave the opponent field blank,
**When** I save the match,
**Then** the match saves successfully — opponent is optional.

---

## US-PLAYER-3 · Tactical Context in Day-of Plan

> Source: `PLAYER_SCOUTING_V1.md §D` · Added: 2026-04-28

**As a** parent reviewing the day-of plan summary,
**I want** the coaching summary to acknowledge that I have recorded notes about today's opponent,
**so that** I know to consult those notes for tactical preparation — without the app quoting them verbatim or revealing their source.

### Acceptance Criteria

**Given** a match has `opponent_player_id` linked to a player with ≥ 1 note,
**When** the plan is generated,
**Then** the `PlanExplanationInput.opponent_notes` list is non-empty (notes were fetched and sanitized).

**Given** `opponent_notes` is non-empty,
**When** `TemplateProvider._build_summary` runs,
**Then** the summary contains the phrase "Your notes mention N prior observation[s] — review the player profile for tactics." where N matches the count.

**Given** no notes exist for the opponent (or no opponent is linked),
**When** the plan is generated,
**Then** the summary does NOT contain "Your notes mention" — no phantom reference.

**Given** a note body contains a §C prohibited phrase,
**When** the sanitization pipeline runs,
**Then** that note's `body_paraphrasable` is replaced with `[note redacted]` and it is dropped from the LLM payload — it is not passed to the template provider.

**Given** any LLM explanation is generated (template or real provider),
**When** `validate_explanation` runs,
**Then** all §C prohibited phrases are checked across the full output — no new validation code is required.

---

## US-PLAYER-4 · Private by Design

> Source: `PLAYER_SCOUTING_V1.md §A` · Added: 2026-04-28

**As a** parent who records notes about other people's children,
**I want** those notes to be completely private to my account and never include contact information by design,
**so that** I am not inadvertently collecting regulated PII about minors.

### Acceptance Criteria

**Given** the `players` table schema,
**When** I inspect the columns,
**Then** there are no columns for email, phone, home address, photo, or physical description — data minimisation is enforced at the schema level.

**Given** I open AddPlayerNoteSheet,
**When** the sheet is displayed,
**Then** the verbatim text *"Notes are private to your account. Don't include personal contact info, photos, or anything not directly observable on court."* is visible as a static label.

**Given** any other user (different `auth.uid()`) attempts a GET/POST/PATCH/DELETE on my players or notes,
**When** the API processes the request,
**Then** all operations return 404 — the data is not visible and cannot be modified.

**Given** I submit a plan for a match with opponent notes,
**When** the LLM explanation is generated,
**Then** the output never contains a verbatim quote from any note body (TemplateProvider only counts notes; real LLM providers are bound by the system-prompt paraphrase rule, `OQ-SCOUT-LLM-1`).

---

## US-PLAYER-5 · Player Deletion Cascade

> Source: `PLAYER_SCOUTING_V1.md §A.4` · Added: 2026-04-28

**As a** parent,
**I want** to be able to delete a player and have all their notes removed at the same time,
**so that** I am not left with orphaned note data I can no longer see or manage.

### Acceptance Criteria

**Given** a player with ≥ 1 note in `player_notes`,
**When** I DELETE `/v1/players/{id}`,
**Then** the player row and all child `player_notes` rows are removed in the same transaction (CASCADE).

**Given** a match had `opponent_player_id` pointing to the deleted player,
**When** the player is deleted,
**Then** `matches.opponent_player_id` is SET NULL — the match record is preserved.

**Given** I delete my entire account (Settings → Delete Account),
**When** Supabase cascades from `auth.users` → `public.users`,
**Then** all my `players` rows cascade-delete, taking all `player_notes` with them in the same transaction.

**Given** a match linked to a note (via `player_notes.match_id`) is deleted,
**When** the match DELETE cascades,
**Then** `player_notes.match_id` is SET NULL — the note survives with its match link cleared.

---

## US-EVAL-1 · Post-Match Write-Up

> Source: `POST_MATCH_EVAL_V1.md §E` · Added: 2026-04-28

**As a** parent who just watched their child finish a match,
**I want** to fill out a structured post-match write-up covering result, what went well, what to improve, and opponent observations,
**so that** I have a running record of each match that I can review at any time.

### Acceptance Criteria

**Given** I tap a match in the schedule strip and open Match Details,
**When** no write-up exists yet,
**Then** I see a CTA card "Add Post-Match Write-Up" that opens the evaluation form.

**Given** I am in the evaluation form,
**When** I select a result (required) and optionally fill any other fields,
**Then** the Save button becomes active after result is selected.

**Given** I save the evaluation,
**When** the form dismisses,
**Then** Match Details now shows the read-only evaluation cards (Result, Ratings, What Went Well, What to Improve, Opponent Observations, Key Moments). Cards with empty content are omitted.

**Given** an evaluation already exists,
**When** I tap Edit,
**Then** the form re-opens pre-filled with existing data and I can update any field.

**Given** any generated evaluation is displayed,
**When** it is rendered,
**Then** no §C prohibited phrases appear in any field (no medical claims, no performance guarantees).

---

## US-EVAL-2 · Opponent Observations Auto-Sync to Scouting Log

> Source: `POST_MATCH_EVAL_V1.md §D` · Added: 2026-04-28

**As a** parent who linked an opponent to a match and then filled out a post-match write-up,
**I want** my opponent observations to automatically appear in that player's scouting log,
**so that** I don't have to enter the same information in two places.

### Acceptance Criteria

**Given** a match has `opponent_player_id` linked and I save an evaluation with non-empty `opponent_observations`,
**When** the eval is saved (POST or PATCH),
**Then** a `player_note` with `source='post_match'` and `body = opponent_observations` is created or updated for that player.

**Given** I update the evaluation's `opponent_observations` field and save again,
**When** the sync runs,
**Then** the existing `player_note` (same `match_id` + `source='post_match'`) is **updated** — no duplicate note is created.

**Given** the match has no `opponent_player_id` set,
**When** I save the evaluation with opponent observations,
**Then** no player_note is created — the sync is silently skipped.

**Given** the eval's `opponent_observations` is empty or whitespace,
**When** the sync runs,
**Then** no player_note is created or modified.

**Given** a scouting plan is generated for a future match against the same opponent,
**When** `fetch_opponent_notes_for_match` runs,
**Then** the auto-created `post_match` note (from the eval) appears in the opponent notes list and contributes to the plan summary acknowledgment ("Your notes mention N prior observations").

---

## US-EVAL-3 · Revisit Past Match Write-Ups

> Source: `POST_MATCH_EVAL_V1.md §E.2` · Added: 2026-04-28

**As a** parent,
**I want** to go back to any past match and see its structured write-up in scannable category cards,
**so that** I can review performance history without wading through unstructured notes.

### Acceptance Criteria

**Given** I navigate to a past match via the schedule strip and Match Details,
**When** a write-up exists,
**Then** I see structured cards for: Result + Score, Ratings (Effort / Focus), What Went Well (bullet list), What to Improve (bullet list), Opponent Observations, Key Moments. Cards with no content are omitted.

**Given** I view a match with a write-up where `went_well` has 3 items,
**When** the card is rendered,
**Then** all 3 items are visible without truncation (always-expanded for MVP; no accordion).

**Given** I view a match where `effort_rating` is nil (parent skipped it),
**When** the Ratings card is rendered,
**Then** the Ratings card is omitted (not shown as blank stars).

---

## US-EVAL-4 · Edit Write-Up at Any Time (No Time Lock)

> Source: `POST_MATCH_EVAL_V1.md §A.3` · Added: 2026-04-28

**As a** parent who wants to update a match write-up after reviewing video or reflecting later,
**I want** to edit the evaluation at any time without a time-based lock,
**so that** my record can be as accurate as possible.

### Acceptance Criteria

**Given** a match evaluation was created more than 24 hours ago,
**When** I tap Edit and save changes,
**Then** the PATCH succeeds and the evaluation is updated (no 403 / time-lock error). This contrasts with `player_notes` which has a 24-hour edit window (scouting-record integrity).

**Given** I edit `opponent_observations` in an existing evaluation and save,
**When** the edit is processed,
**Then** the corresponding `player_note` (source=post_match, same match_id) is also updated to reflect the new text.

**Given** I delete an evaluation via the app,
**When** the DELETE is processed,
**Then** the eval row is removed; the associated `player_note` (source=post_match) is NOT automatically deleted — it was a scouting observation that may have independent value. Flag as `OQ-EVAL-3` if deletion cascading to the derived note is desired.

---

## Open Questions

1. **Multiple player profiles**: The spec shows a `player_profiles` table but does not specify whether the MVP UI supports creating more than one profile per user. The monetization tiers in §29 imply free = 1 profile, paid = multiple. Needs explicit scoping for Phase 2.
2. **Plan regeneration UX**: When a parent regenerates a plan (e.g., after weather changes), does the app warn them they are creating a new version? UX for versioned plans is unspecified.
3. **Scenario duration configurability**: §14 notes default durations (75/120/180 min) "should eventually depend on age group, format, surface, etc." but doesn't specify whether Phase 3 allows any configuration. Treating as hardcoded defaults for MVP.
4. **Offline access**: Whether saved plans must be accessible offline is not specified. Given tournament venue connectivity may be poor, this may be important for UX.
