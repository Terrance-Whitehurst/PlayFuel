# PlayFuel — MVP Product Requirements Document

> **Status:** Phase 0 draft · Authority: Product Manager · Last updated: 2026-04-26

---

## 1. One-Sentence Pitch (§2)

> An iPhone app that helps junior tennis parents manage tournament-day logistics with schedule-aware, weather-aware, location-aware recommendations for meals, hydration, warm-ups, recovery, and between-match planning.

---

## 2. Core Problem (§4)

Junior tennis tournaments are chaotic. Parents make critical nutrition, hydration, warm-up, and logistics decisions without their child's coach present. They don't lack information — **they lack a plan.**

---

## 3. Target Users (§3)

| Role | Who They Are | What They Need |
|---|---|---|
| **Primary** | Parent of a junior tennis player | A clear, ready-to-execute tournament-day plan |
| **Secondary** | Junior tennis player | Timing on warm-up, food, hydration, and recovery |
| **Future** | Coach | Remote guidance; multi-player oversight (out of MVP scope) |

---

## 4. Core Product Principle (§5)

> **Rules engine first. LLM as explanation layer only.**

- The backend generates a structured, deterministic plan.
- The LLM receives that plan and converts it into parent-friendly language.
- The LLM **must never** invent: hydration quantities, medical advice, injury guidance, food safety claims, restaurant menu items, tournament rules, or schedule logic.
- Both the structured plan and the LLM summary are stored.

---

## 5. MVP Goal (§6)

A parent must be able to:

1. Sign in with Apple.
2. Create a player profile.
3. Create a tournament with location and dates.
4. Add a 9:00 AM match and an estimated 1:00 PM next match.
5. Generate a match-day plan.
6. View short / normal / long match-duration scenarios.
7. View nearby food options.
8. View weather-adjusted hydration guidance.
9. Save the plan.

---

## 6. Canonical Demo Scenario

```
Tournament:  Dallas Junior Open (USTA Level 4)
Location:    XYZ Tennis Center, Dallas, TX
Weather:     88°F, 72% humidity
Match 1:     9:00 AM
Est. Match 2: ~1:00 PM

Required output:
  - Wake-up plan
  - Pre-match meal window
  - Warm-up window
  - During-match hydration reminders
  - Short / Normal / Long match scenarios with timings
  - Parent food pickup windows per scenario
  - 3–5 nearby food options with recommended orders
  - Weather-specific adjustments (hot + humid flags)
```

---

## 7. First Serious Milestone (§41)

> A parent creates a tournament, enters a 9:00 AM match and possible 1:00 PM next match, and gets a clear, weather-aware, food-aware, scenario-based plan that feels like something a real coach would have told them.

---

## 8. Architecture Summary (§7)

```
iPhone App (SwiftUI)
  → FastAPI Backend (Python)
    → Supabase Postgres (data)
    → Weather API (WeatherKit or OpenWeather)
    → Places API (Google Places or Yelp Fusion)
    → LLM API (explanation layer only)
```

See spec §7–8 for full stack rationale. Do not redesign in Phase 0.

---

## 9. Data Model Summary (§9–10)

Top-level object is `Tournament`. Entity hierarchy:

```
User → PlayerProfile → Tournament → Matches
                                  → WeatherSnapshots
                                  → FoodOptions
                                  → Plans (structured JSON + LLM summary)
                                  → MatchScenarios
```

Full schema SQL in spec §10. Row-level security pattern: `auth.uid() = user_id` on all user-owned tables (see §11).

---

## 10. MVP Build Phases (§23)

| Phase | Goal | Deliverable |
|---|---|---|
| 0 | Rules + scope | PRD, user stories, safety docs, scenario acceptance |
| 1 | Static prototype | SwiftUI shell with fake data |
| 2 | Auth + DB | Sign in with Apple, Supabase schema, RLS |
| 3 | FastAPI backend | Plan generation engine, scenario logic |
| 4 | Weather integration | Weather flags, plan adjustments |
| 5 | Food/places integration | Nearby options, recommended order templates |
| 6 | LLM explanation layer | Parent-friendly plan summary |

---

## 11. Privacy Posture (§27)

- Parent account owns all data. No child-owned accounts in MVP.
- Do not collect exact birthdate (use age range/birth year).
- Injury and dietary notes are optional.
- No data selling. No targeted advertising. No public player profiles.
- Store tournament venue location, not live player location history.
- Implement data deletion.
- COPPA review required before accepting users with children under 13 (see FTC source in §27).

---

## Open Questions

1. **App name**: §2 lists 8 working names. No final name selected. Needs decision before App Store submission (not blocking Phase 0–3).
2. **Weather API choice**: Spec recommends WeatherKit (iOS-native) or OpenWeather (backend-simple). No decision recorded. Engineering Lead should decide in Phase 3/4.
3. **Places API choice**: Google Places vs. Yelp Fusion. Spec defers to "whichever gets you working faster." Engineering Lead should decide in Phase 5.
4. **LLM provider**: Spec references OpenAI structured outputs (§8.7). No provider confirmed. AI Agent should decide in Phase 6.
5. **Match duration defaults**: §14 gives short=75min, normal=120min, long=180min as "configurable defaults." It is not specified where these are configured (app settings? admin config? player profile?). Needs decision before Phase 3.
6. **COPPA threshold**: The spec notes COPPA applies to users under 13 but defers to legal counsel. If the app targets players 10–18, this must be resolved before any public launch.
