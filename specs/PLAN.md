# PlayFuel — Build Plan

> iPhone-first tournament-day operating system for junior tennis parents.
> Status: **Phase 0 docs delivered. Awaiting greenlight to execute Phase 1+.**

---

## 1. Product in one paragraph

A parent enters a junior tennis tournament with a 9:00 AM match and an estimated 1:00 PM next match. PlayFuel returns a weather-aware, location-aware, scenario-based tournament-day plan covering wake-up, pre-match meal, warm-up, hydration, three match-duration scenarios (short / normal / long), parent food-pickup windows, and recovery — in language that sounds like a calm coach, not a chatbot.

## 2. Non-negotiable product principle

**Rules engine first. LLM explains only.**
The deterministic backend owns timings, hydration logic, food categories, and weather adjustments. The LLM converts structured JSON into parent-friendly language. The LLM never invents restaurants, menu items, medical advice, or schedule logic.

## 3. Stack (locked)

| Layer | Choice |
|---|---|
| iOS | SwiftUI + Sign in with Apple |
| Auth / DB | Supabase (Postgres + RLS, `auth.uid() = user_id` everywhere) |
| Backend | FastAPI (Python, Pydantic), verifies Supabase JWT |
| Weather | WeatherKit *or* OpenWeather (decide in Phase 4) |
| Places | Google Places (preferred) or Yelp Fusion — **no menu scraping in MVP** |
| LLM | Structured-output prompt that consumes the rules-engine JSON |

## 4. Phased build

| Phase | Task IDs | Owner | Deliverable |
|---|---|---|---|
| **0 — PRD + rules** | #1 ✅, #2 | Planning | PRD, user stories, scope, safety, scenario acceptance, rules constants v1 |
| **1 — Static SwiftUI prototype** | #3 | Engineering2 (mobile) | App shell with fake data: sign-in, tournament list, dashboard, timeline, scenario/food/weather cards |
| **2 — Supabase** | #4 | Engineering3 (data) | Schema migrations, RLS policies, Sign in with Apple wired to Supabase Auth |
| **3 — FastAPI + plan engine** | #5, #6 | Engineering1 (backend) + Engineering2 (mobile) | JWT verify, CRUD, `generate_match_scenarios()`, `POST /generate-plan`; mobile swaps fake data for live API |
| **4 — Weather** | #7 ✅ | Engineering1 | Open-Meteo client (keyless), `weather_snapshots`, flag classifier, forecast targeting for future-dated tournaments, wind/precip in API response |
| **5 — Food / Places** | #8 ✅ | Engineering1 | Google Places (New) integration, 12-bucket cuisine categorizer, restaurant templates, recommended orders, safety lint |
| **6 — LLM explanation** | #9 ✅ | Engineering1 | AnthropicProvider (`claude-3-5-haiku-latest`) + TemplateProvider fallback; tool-use structured output; §C safety lint; PII-stripped input; `llm_summary JSONB` in `plans` |
| **7 — Feedback & personalization** | #10 | Engineering2 | Post-tournament rating screen, what-worked / what-didn't, feed into player preferences |
| **8 — Beta** | #11 | Planning + Engineering2 | TestFlight build, 5–10 junior tennis families, analytics, bug tracking |
| **Cross-cutting — Privacy** | #12 | Planning | COPPA review, App Store privacy disclosures, data minimization, data deletion flow |
| **Cross-cutting — Eval** | #13 | Planning + Engineering1 | 5 canonical scenario tests (cool 9/1, hot/humid, long gap, back-to-back, rain delay) |

## 5. Parallelization plan (when greenlit)

Once unblocked, work runs in 4 rounds:

**Round 1 (parallel):**
- Engineering1 → resolve open questions OQ-05/13/14 + draft rules constants foundation (feeds #2)
- Engineering2 → SwiftUI prototype with fake data (#3)
- Engineering3 → Supabase schema + RLS migrations (#4)
- Planning → privacy/compliance doc (#12)

**Round 2 (parallel):**
- Engineering1 → full FastAPI backend with rules engine (#5)
- Planning → rules constants doc using Engineering1's resolutions (#2)
- Planning → eval harness scenarios (#13)

**Round 3 (parallel):**
- Engineering1 → weather integration (#7)
- Engineering2 → mobile↔backend wiring (#6)
- Engineering3 → food/places integration design (#8)

**Round 4 (parallel):**
- Engineering1 → LLM explanation layer (#9)
- Engineering2 → feedback screen (#10)
- Engineering3 → TestFlight beta plan (#11)

## 6. Phase 0 deliverables (already on disk)

In `.pi/multi-team/expertise/`:

- `PRD.md` — anchored to the Dallas 9 AM / 1 PM / 88°F demo
- `USER_STORIES.md` — 9 stories (US-01…US-09) in Given/When/Then, mapped to schema and API
- `MVP_SCOPE.md` — explicit in/out scope, 11-category out-of-scope list
- `SAFETY_DISCLAIMERS.md` — verbatim disclaimer, prohibited phrases, safer-language map, LLM constraints
- `SCENARIO_ACCEPTANCE.md` — must / must-not checks for all 5 eval scenarios

## 7. Open questions blocking later phases

### Engineering blockers (resolve before Phase 3 / Task #5)

| ID | Question | Why it matters |
|---|---|---|
| OQ-05 | Are 75 / 120 / 180-min scenario durations hardcoded constants or configurable per age / format / surface? | Determines schema and rules-engine API |
| OQ-13 | Gap-boundary off-by-one: §19 pseudocode uses `<150`, §16 prose says "90–150" inclusive | Two sources of truth → bugs |
| OQ-14 | Negative gap: what does the engine return if a match runs *past* the next match's scheduled start? | Spec doesn't cover it |

### Pre-launch legal blockers (need a lawyer, not a team)

| ID | Question |
|---|---|
| OQ-06 | COPPA handling for under-13 players (spec recommends parent-owned accounts only — confirm) |
| OQ-11 | Exact heat-illness emergency wording |

## 8. MVP success criteria

A parent can:

1. Sign in with Apple
2. Create a player profile
3. Create a Dallas tournament with location and dates
4. Add a 9:00 AM match and estimated 1:00 PM next match
5. Tap "Generate Plan" and within seconds see: weather card, three match-duration scenarios, food options with recommended orders, parent pickup window guidance, and an LLM-written explanation that doesn't invent any facts

If that works reliably, MVP is done.

## 9. What is explicitly NOT in MVP

Fine-tuning · on-device LLM · video analysis · menu scraping · coach dashboard · recruiting · social network · player rankings · wearable integrations · automatic draw ingestion · USTA schedule scraping.

## 10. Status

- ✅ Phase 0 docs delivered
- ⏸️ All other tasks paused — **awaiting user greenlight before kickoff**
- Recommended first move on greenlight: route OQ-05/13/14 to Engineering1, then fan out Round 1
