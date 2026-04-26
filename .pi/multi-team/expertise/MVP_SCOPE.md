# PlayFuel — MVP Scope Definition

> **Status:** Phase 0 draft · Authority: Product Manager · Last updated: 2026-04-26
> Drawn from spec §6 (MVP Definition), §23 (Phase-by-Phase Build Plan), and §35/§36/§37 (agent prompts).

---

## In Scope (Phases 0–6)

These are the only things we build in the MVP. If it is not on this list, it is out of scope.

### Phase 0 — Product Rules & Scope
- [ ] MVP PRD
- [ ] User stories with acceptance criteria
- [ ] Core rules document (planning, food, weather, safety)
- [ ] Out-of-scope list
- [ ] Safety disclaimers
- [ ] Example generated plans

### Phase 1 — Static iPhone Prototype
- [ ] SwiftUI app shell (NavigationStack, Forms, Lists, Cards)
- [ ] Tournament list screen
- [ ] Tournament dashboard screen
- [ ] Static timeline view (vertical, time-left / action-right)
- [ ] Static scenario cards (short / normal / long)
- [ ] Static food recommendation cards
- [ ] Static weather card
- [ ] Sign-in placeholder screen

### Phase 2 — Auth + Database
- [ ] Supabase project setup
- [ ] Sign in with Apple (Apple identity token → Supabase Auth → session)
- [ ] Database schema: `app_users`, `player_profiles`, `tournaments`, `matches`, `weather_snapshots`, `food_options`, `tournament_plans`, `match_scenarios`, `plan_feedback`
- [ ] Row-Level Security policies on all user-owned tables
- [ ] Create tournament (name, venue, location, dates)
- [ ] Create player profile (name, birth year, level, hand, optional notes)
- [ ] Add match times (scheduled + estimated next match)

### Phase 3 — FastAPI Backend + Plan Engine
- [ ] FastAPI project structure (see §33)
- [ ] JWT verification middleware (user ID extracted from Supabase JWT — never from client)
- [ ] `GET /health`
- [ ] `GET /me`
- [ ] CRUD: `/player-profiles`
- [ ] CRUD: `/tournaments`
- [ ] CRUD: `/tournaments/{id}/matches`
- [ ] `POST /tournaments/{id}/generate-plan`
- [ ] `GET /tournaments/{id}/plans/latest`
- [ ] `GET /plans/{plan_id}`
- [ ] Deterministic plan generation engine (see §13, §19)
- [ ] Short / normal / long scenario logic (75 / 120 / 180 min defaults — see §14)
- [ ] Parent pickup window logic (see §15)
- [ ] Food strategy by gap bucket (see §16)
- [ ] Pydantic schemas for all request/response models (see §34)
- [ ] Unit tests for 9 AM / 1 PM canonical scenario

### Phase 4 — Weather Integration
- [ ] Weather API client (WeatherKit or OpenWeather — engineering decision)
- [ ] `GET /tournaments/{id}/weather`
- [ ] Weather snapshot storage
- [ ] `classify_weather()` function with flags: hot, very_hot, humid, cold, windy, rain_risk (see §17 thresholds)
- [ ] Weather flag → plan adjustment mapping (see §17)

### Phase 5 — Food / Places Integration
- [ ] Places API client (Google Places or Yelp — engineering decision)
- [ ] `GET /tournaments/{id}/food-options`
- [ ] Food option storage
- [ ] Restaurant category templates with recommended orders (see §16 `RESTAURANT_TEMPLATES`)
- [ ] Place categorization logic (see §16 categories)
- [ ] Distance / estimated drive time display
- [ ] Bag-food fallback when no nearby options found

### Phase 6 — LLM Explanation Layer
- [ ] LLM API client
- [ ] System prompt (see §8.7 example prompt)
- [ ] Structured plan JSON → parent-friendly text
- [ ] LLM summary stored in `tournament_plans.llm_summary`
- [ ] Safety guardrails: LLM must not invent restaurant facts, medical advice, or schedule logic
- [ ] Structured output / schema enforcement where provider supports it (see §8.7)

---

## Out of Scope (Do Not Build in MVP)

Explicitly deferred. Building any of these in Phase 0–6 is a scope violation.

### AI / ML
- ❌ Fine-tuning any model
- ❌ On-device LLM inference
- ❌ Video analysis of match play
- ❌ LLM as primary source of hydration quantities, medical advice, injury guidance, or food safety claims

### Data Acquisition
- ❌ Full menu scraping (fragile, legal risk — see §8.6 rationale)
- ❌ Automatic USTA tournament schedule scraping
- ❌ Complex tournament draw ingestion
- ❌ Approved menu APIs or user-submitted order history (future enhancement)

### Features
- ❌ Advanced injury recommendations
- ❌ Coach dashboard or coach-sharing (future Phase 3-month roadmap item)
- ❌ Recruiting features
- ❌ Social network / community features
- ❌ Player rankings
- ❌ Local / push notifications (noted as useful future feature in §26 but not required in prototype)
- ❌ Widgets
- ❌ Wearable integrations (Apple Watch, Garmin, etc.)
- ❌ Rain delay real-time alerting
- ❌ Multi-player coach tier

### Auth / Accounts
- ❌ Child-owned accounts (parent account owns all data in MVP — see §27)
- ❌ Email/password authentication
- ❌ Social login other than Sign in with Apple

### Analytics / Personalization
- ❌ Player preference learning from plan history
- ❌ Performance pattern tracking
- ❌ Tournament history analytics dashboard

### Monetization
- ❌ Paywall, subscription, or payment flow (design for it; don't build it — see §29)

### External Integrations
- ❌ Map integration / turn-by-turn directions
- ❌ Calendar integration
- ❌ Wearable / health kit sync

---

## Explicit Deferrals (From Spec)

Items the spec mentions as future enhancements but explicitly defers:

| Item | Spec Reference | Earliest Phase |
|---|---|---|
| Local / push notifications | §26 | Month 2 beta |
| Coach-sharing prototype | §25 Month 3 | Post-MVP |
| Paid beta exploration | §25 Month 3 | Post-MVP |
| Player preference learning | §25 Month 3, §29 | Post-MVP |
| Menu intelligence via approved APIs | §8.6 | Post-MVP |
| User-submitted successful orders | §8.6 | Post-MVP |
| Scenario duration configuration by age/format/surface | §14 | Post-MVP |
| Tactical wind / mental notes | §17 wind adjustments | Post-MVP |

---

## Open Questions

1. **Feedback screen scope**: `POST /plans/{plan_id}/feedback` and the `plan_feedback` table are in the spec (§10, §12) but §23 assigns feedback to "Phase 7." The API endpoint is listed in §12 as an MVP endpoint. Clarify whether Phase 6 delivery includes the feedback UI or just the endpoint.
2. **Scenario duration configurability**: Are the 75/120/180 minute defaults locked for MVP or exposed as player profile settings? Spec implies eventual configurability but does not assign it to a phase.
3. **Notifications**: §26 describes notifications as "not required in the first prototype, but could be very useful." Treat as explicitly out of MVP scope unless Planning Lead overrides.
