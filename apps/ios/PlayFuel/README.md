# PlayFuel — iOS Static Prototype (Phase 1)

> **Status:** Phase 1 complete — static SwiftUI prototype, fake data only.  
> **Stack:** SwiftUI + AuthenticationServices, iOS 17+, zero external dependencies, zero networking.  
> **Task:** PLAN.md Task #3 (rerouted from Engineering2 → Engineering3/Frontend Dev 3).

---

## Path Deviation

`specs/PLAN.md` and EL2's brief target `ios/PlayFuel/`. This package lives at `apps/ios/PlayFuel/` because the Frontend Dev 3 write domain is restricted to `apps/`. The path deviation is semantic only — file structure, import paths, and Phase 3 wiring are identical.

---

## How to Open in Xcode

1. `File → Open` → select `apps/ios/PlayFuel/` (Xcode will detect `Package.swift`).
2. Set the run target to an iPhone 17 simulator (iOS 17+).
3. Build and run. No API keys, no environment variables, no Supabase config needed for Phase 1.

> **Note:** `SignInWithAppleButton` requires a real bundle ID signed with an Apple Developer account to function on device. In the simulator, the tap gesture fake-auth works without signing.

---

## Phase 3 Swap (One-File Replacement)

All fake data lives in `Sources/PlayFuel/Data/FakeData.swift`. To wire Phase 3:

1. Delete `FakeData.swift`.
2. Replace `FakeData.plan(for:)` and `FakeData.match(for:)` with calls to your FastAPI client.
3. Replace `FakeData.tournaments` with `GET /tournaments` response.
4. No View files require changes — they consume the same model types.

---

## File Structure

```
apps/ios/PlayFuel/
├── README.md                              ← this file
├── Package.swift                          ← SwiftUI package, iOS 17+
└── Sources/PlayFuel/
    ├── PlayFuelApp.swift                  ← @main App, AppState env object, root nav
    ├── State/
    │   └── AppState.swift                 ← isAuthenticated, selectedTournamentId
    ├── Models/
    │   ├── Tournament.swift               ← id, name, venue, lat, lon, dates
    │   ├── Match.swift                    ← id, tournamentId, times, round, opponent, court
    │   ├── WeatherSnapshot.swift          ← tempF, humidity, flags, extremeHeatRisk (derived)
    │   ├── ScenarioPlan.swift             ← mirrors RULES_CONSTANTS_V1 §G exactly
    │   ├── Plan.swift                     ← full plan envelope (scenarios + weather + food + timeline)
    │   ├── FoodOption.swift               ← name, category, driveTime, recommendedOrder
    │   └── TimelineEvent.swift            ← id, time, title, detail, kind
    ├── Data/
    │   ├── FakeData.swift                 ← single source of all fake data (Dallas + 2 stubs)
    │   └── HardCodedStrings.swift         ← verbatim §A disclaimer + §B heat emergency text
    └── Views/
        ├── SignInView.swift               ← US-01: fake auth, disclaimer link
        ├── TournamentListView.swift       ← US-03: 3 tournaments, plan-status badge
        ├── TournamentDashboardView.swift  ← US-05: hub with all cards
        ├── TimelineView.swift             ← US-06: chronological day timeline
        ├── ScenarioCardView.swift         ← US-06: one card per scenario (short/normal/long)
        ├── FoodCardView.swift             ← US-08: food options + bag fallback
        ├── WeatherCardView.swift          ← US-07: temp + flags + adjustments
        ├── DisclaimerView.swift           ← §A verbatim; settings + sign-in + plan footer
        └── EmergencyBanner.swift          ← §B verbatim; shows on dashboard when extreme_heat_risk
```

---

## Screen Tour

| Screen | File | One-line description |
|---|---|---|
| **SignIn** | `SignInView.swift` | Centered `SignInWithAppleButton` (native look, fake auth); "usage guidelines" link → DisclaimerView |
| **Tournament List** | `TournamentListView.swift` | 3 tournament cards (Dallas / Austin / Houston); "Plan Ready" badge on Dallas; tap → Dashboard |
| **Tournament Dashboard** | `TournamentDashboardView.swift` | Hub (Phase 8 order): EmergencyBanner → PlanSummaryCard → ScheduleStrip → NextActionCard → FoodCard → Scenarios → Timeline btn → WeatherPill (compact, demoted) → §A footer |
| **Weather Card** | `WeatherCardView.swift` | 88°F / 72% humidity, "EXTREME HEAT" pill, hot+humid flag pills, §E.3 adjustment bullets |
| **Scenario Cards** | `ScenarioCardView.swift` | Short (75m/165m gap/light_meal), Normal (120m/120m gap/quick_pickup), Long (180m/60m gap/portable), gap pill color-coded by status |
| **Food Card** | `FoodCardView.swift` | 3 Dallas options: Chipotle (confirmed §F.3 order), Jimmy John's [DRAFT], Central Market [DRAFT]; empty-state shows bag fallback |
| **Timeline** | `TimelineView.swift` | 12 events 6:00 AM → recovery, icon+color per kind, vertical connector line |
| **Disclaimer** | `DisclaimerView.swift` | §A verbatim, §B verbatim (OQ-11 draft note), "What this app does NOT do" prohibited-claims list |
| **Emergency Banner** | `EmergencyBanner.swift` | Persistent red banner at dashboard top when `extremeHeatRisk`; §B text verbatim; OQ-11 draft caveat |

---

## Dallas Demo Walkthrough

1. Launch → SignInView → tap "Sign in with Apple" → fake auth → TournamentList.
2. Tap "Dallas Spring Open" → Dashboard.
3. **Red EmergencyBanner** appears immediately (88°F + 72% humidity → hot AND humid → `extremeHeatRisk = true`).
4. **WeatherCard**: 88°F / 72% / 8mph / 10% rain / UV 8. Flags: `hot`, `humid`. Adjustments list from §E.3.
5. **Scenario cards** (scroll horizontal):
   - Short: 75min / end 10:15 AM / 165min gap → light_meal + wait_until_end / rewarm 12:30 PM
   - Normal: 120min / end 11:00 AM / 120min gap → quick_pickup + wait_until_end / rewarm 12:30 PM
   - Long: 180min / end 12:00 PM / 60min gap → portable + pickup_during_match / rewarm 12:30 PM
6. **FoodCard**: Chipotle (§F.3 verbatim), Jimmy John's, Central Market.
7. Tap "Full Day Timeline" → 12 chronological events from 6:00 AM wake-up to recovery.
8. Footer "usage guidelines" → DisclaimerView with §A + §B.

---

## Deviations from PRD / USER_STORIES

| Deviation | Rationale |
|---|---|
| `apps/ios/PlayFuel/` instead of `ios/PlayFuel/` | Write domain restriction — see Path Deviation section above |
| Austin + Houston are stubs with no plan | Spec asks for 1–3 tournaments in list (US-03 AC); "no plan yet" state is correct for prototype, avoids inventing data for non-demo tournaments |
| `UnevenRoundedRectangle` for scenario card header | iOS 17 API — cleaner than clipping with a mask; no functional impact |
| Timeline event times are display strings not `Date` | Prototype simplification. Phase 3: parse ISO 8601 timestamps from API |
| `[DRAFT — OQ-C]` labels on timeline offset values | PRD §D warns offsets are Engineering1 proposals pending confirmation — flagged in UI to avoid treating as authoritative |
| `SignInWithAppleButton` tap gesture intercept | Phase 1 fake auth per spec. Real button `.onCompletion` handler is wired to a no-op; `onTapGesture` fires first to flip auth state. Removes cleanly in Phase 2. |
| No player profile creation screen (US-02) | US-02 is a Phase 2 concern (Supabase schema, RLS). Phase 1 static prototype per MVP_SCOPE doesn't require it. |
| No plan generation button (US-05) | Plan is pre-generated in FakeData; "Generate Plan" button is Phase 3 (needs FastAPI). Dashboard renders the plan directly. |

---

## Open Questions Surfaced

| ID | Question |
|---|---|
| OQ-11 | (Carried from RULES_CONSTANTS_V1) §B heat emergency text is DRAFT pending attorney review. Hard-coded in HardCodedStrings.swift with explicit [DRAFT — OQ-11] label visible in DisclaimerView and EmergencyBanner. |
| OQ-C | Timeline offset values (wake T-3h, meal T-2.5h, arrive T-1h, warm-up T-30m) are Engineering1 proposals — flagged in FakeData.swift event detail strings. |
| OQ-B | Restaurant order templates for `sandwich_shop`, `grocery_prepared`, `breakfast_cafe` are DRAFT per §F.3. Flagged in FakeData.swift comments. |
| NEW-1 | `SignInWithAppleButton` on iOS simulator with fake bundle ID: tap gesture intercepts correctly, but the button may show a system auth sheet briefly before dismissing. Consider wrapping in a plain `Button` for Phase 1 demos if the sheet flicker is distracting. |
| NEW-2 | Horizontal scenario card width is hardcoded at 300pt (`ScenarioCardView`). On iPad (future scope), this will need adaptive sizing. Not a Phase 1 concern. |

---

## Safety Compliance Checklist

| Requirement | Status |
|---|---|
| §A disclaimer on sign-in screen | ✅ "usage guidelines" link → DisclaimerView |
| §A disclaimer on plan footer | ✅ Footer button on TournamentDashboardView |
| §A text verbatim, never re-typed | ✅ All refs use `HardCodedStrings.userDisclaimer` |
| §B heat emergency text verbatim | ✅ All refs use `HardCodedStrings.heatEmergencyText` |
| §B banner when extreme_heat_risk | ✅ EmergencyBanner renders on Dallas dashboard |
| §C prohibited phrases absent | ✅ No "prevents cramps", "guarantees", "safe for every player" anywhere |
| OQ-11 draft caveat present | ✅ Visible in EmergencyBanner + DisclaimerView |

---

## Configuration (Task #6)

The app reads three values at launch via `Sources/PlayFuel/Configuration.swift`.
Set them as Xcode scheme environment variables (**Product → Scheme → Edit Scheme → Run → Arguments → Environment Variables**) for local dev.
For production, inject via `.xcconfig` per Apple's standard guidance.

| Constant | Env var | Phase 1 default | Notes |
|---|---|---|---|
| `apiBaseURL` | `PLAYFUEL_API_BASE_URL` | `http://localhost:8000` | FastAPI from `apps/api/` |
| `supabaseURL` | `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` | Supabase project URL |
| `supabaseAnonKey` | `SUPABASE_ANON_KEY` | `YOUR_ANON_KEY` | Publishable / anon key |

> **OQ-iOS-1:** Sign in with Apple on a real device requires the `Sign In with Apple` capability in an Xcode project (`.xcodeproj`). This Swift Package cannot declare entitlements. For device testing, wrap the package in an Xcode project with the capability enabled. Simulator runs work without it.

---

## Test Data (Task #6 → Phase 5b)

**Phase 5b (April 2026):** Tournament + match create flows shipped.
Tournaments can now be created in-app via the `+` button in `TournamentListView`
(`TournamentCreateView` sheet → `POST /v1/tournaments`).
Matches can be created in-app via the `+` button in `TournamentDashboardView`
(`MatchCreateView` sheet → `POST /v1/tournaments/{tid}/matches`).

The Dallas demo seed data in `db/supabase/seed/dallas_demo.sql` remains the
fastest path for the recorded demo. The Dallas demo tournament UUID
(`11111111-0000-0000-0000-000000000001`) is preserved in `FakeData.dallasTournament.id` for reference.

---

## Networking

**Phase 5 (April 2026):** Hybrid splice retired — `Repository` now consumes the real API response directly for weather, timeline, and food options. `FakeData` remains in the build target for SwiftUI `#Preview` blocks only.

---

## Running the Demo on Device

The app now supports on-device deployment via a proper Xcode project with the `Sign In with Apple` capability. `Package.swift` is preserved; it continues to serve as the source layer for `#Preview` blocks.

1. **Database:** `supabase start && supabase db reset`  
   Brings up Supabase locally and auto-applies the Dallas demo seed (via `supabase/config.toml` — BD-managed).

2. **API:** `cd apps/api && uvicorn playfuel_api.main:app --reload --port 8000`  
   Starts the FastAPI server. No environment variables required for the demo (mock Places provider is default).

3. **Xcode project:** `cd apps/ios/PlayFuel && brew install xcodegen && xcodegen`  
   Generates `PlayFuel.xcodeproj`. XcodeGen is already installed in the repo's dev environment — this step is only needed if `PlayFuel.xcodeproj` is absent (e.g. on a fresh clone).

4. **Xcode signing:** Open `PlayFuel.xcodeproj` in Xcode. In *Signing & Capabilities*, set your Development Team (requires a free or paid Apple Developer account). Bundle ID is locked to `com.playfuel.ios`.

5. **Run on iPhone:** Select your device in the Xcode toolbar and hit ▶. Tap **Sign in with Apple** — the real `AuthenticationServices` flow will trigger and the entitlement (`com.apple.developer.applesignin`) is baked into `Resources/PlayFuel.entitlements`.

> **App icon:** A placeholder 1024×1024 PNG (PlayFuel green `#227F52`) is at  
> `Resources/Assets.xcassets/AppIcon.appiconset/icon-1024.png`.  
> Replace with a production-quality icon before TestFlight / App Store submission.

---

## Doubles Support (Phase 7)

Doubles integration shipped in the doubles-spec build (DOUBLES_SPEC_V1.md).

### MatchCreateView

Two new form sections appear **above** Estimated Duration:

1. **Match Type** — segmented picker: `Singles | Doubles` (default: Singles).
2. **Doubles Format** — segmented picker: `Best of 3 | 8-Game Pro Set` (default: Best of 3). Visible **only** when Doubles is selected.

The Estimated Duration picker labels update dynamically to reflect the selected format’s short/normal/long minute values:

| Type | Format | Short | Normal | Long |
|---|---|---|---|---|
| Singles | — | 75 min | 120 min | 180 min |
| Doubles | Best of 3 | 60 min | 90 min | 135 min |
| Doubles | 8-game pro set | 45 min | 70 min | 100 min |

> All doubles values are `[DRAFT — OQ-DBL-1]`: derived from USTA junior tournament norms, not validated by a coach.

### TournamentDashboardView

The dashboard adapts based on which match types are present:

| Tournament state | Dashboard behaviour |
|---|---|
| Singles only | Existing layout — no tab picker |
| Doubles only | Existing layout showing the doubles plan — no tab picker |
| Both types | Segmented `Singles | Doubles` picker appears **above** the EmergencyBanner |

Selecting a segment switches all dashboard cards (scenarios, food, LLM summary, etc.) to show the corresponding plan. Selection persists for the session in `AppState.selectedMatchType`.

### New model types (Phase 7)

- `MatchType.swift` — `MatchType` + `DoublesFormat` enums
- `PlanEnvelope.swift` — wraps `singlesPlans: [Plan]` + `doublesPlans: [Plan]`; `AppState.currentPlanEnvelope` replaces the old `currentPlan`

---

## Nutrition-First IA (Phase 8)

Dashboard re-ordered per user feedback and `NUTRITION_FIRST_IA_V1.md`.
Nutrition and schedule are the hero surfaces; weather is demoted to a compact pill.

### Dashboard Card Order (locked)

| # | Card | Condition |
|---|---|---|
| 0 | `EmergencyBanner` (red) | `extreme_heat_risk == true` — **IMMOVABLE** |
| 1 | Singles / Doubles picker | `hasBothTypes == true` only |
| 2 | `PlanSummaryCard` (LLM coach voice) | `llmSummary != nil` |
| 3 | `ScheduleStripView` (multi-match strip) | always (empty-CTA when 0 matches) |
| 4 | `NextActionCard` (next thing to do) | always (fallback copy when no future events) |
| 5 | `FoodCardView` | `foodOptions` non-empty |
| 6 | Scenario cards (short/normal/long) | always |
| 7 | "Full Day Timeline" button | `timeline` non-empty |
| 8 | `WeatherCardView` (compact pill, demoted) | always |
| 9 | Disclaimer footer | always |

**Why:** Parents are already outside feeling the heat. The weather card was the
first thing they saw but isn't actionable. Nutrition timing and the match schedule
are the surfaces they actually use. Safety logic is **unchanged** — `extreme_heat_risk`
still fires `EmergencyBanner` at position #0 regardless of weather demotion.

### Multi-Match Schedule Strip (`ScheduleStripView`)

- Horizontally scrollable strip of `MatchChip` views, one per plan
- Each chip shows: match number, scheduled time, status (upcoming/in-progress/done), type pill
- Tap any chip → updates `AppState.selectedMatchId` → all cards below show that match's plan
- **Default selection:** next upcoming match by clock; fallback = most-recently-completed
- **Empty state:** full-width CTA card with "Add your first match" button

### Next Up Card (`NextActionCard`)

- Single hero card surfacing the most immediately actionable item
- Derived deterministically by the backend rules engine (`rules/next_action.py`) — never LLM
- Shows: event title, parent-friendly detail, "In N min" badge, scheduled time
- **Fallback** when `nextAction == nil`: "All set — enjoy the day"

### Weather Pill (WeatherCardView compact mode)

- Demoted from position #2 to position #8
- Renders as a 1-line pill: `🌡 88°F · humid, hot  ›`
- Tap to expand inline → existing full card body revealed
- Collapses on second tap; state is per-session, default collapsed
- `WeatherCardView(weather:, compact: true)` — `compact: false` (default) is unchanged

### New files (Phase 8)

| File | Description |
|---|---|
| `Models/NextAction.swift` | `Codable` struct for the next actionable timeline item |
| `Views/ScheduleStripView.swift` | Horizontal strip + `MatchChip` sub-view + empty-state CTA |
| `Views/NextActionCard.swift` | "NEXT UP" hero card with fallback copy |

### Changed files (Phase 8)

| File | Change |
|---|---|
| `Models/Plan.swift` | Added `matchId: UUID`, `nextAction: NextAction?`, `scheduledStart: String?` |
| `Models/PlanEnvelope.swift` | Arrays: `singlesPlans: [Plan]`, `doublesPlans: [Plan]`; new `plan(for matchId:)` + `nextUpcomingPlan(now:)` |
| `Networking/DTOs.swift` | `PlanEnvelopeDTO` → arrays; `PlanCoreDTO` + `matchId`/`nextAction`/`scheduledStart`; `NextActionDTO` |
| `State/AppState.swift` | Added `selectedMatchId: UUID?` + `defaultMatchId(from:now:)` helper |
| `Views/WeatherCardView.swift` | Added `compact: Bool = false` mode with expand-in-place toggle |
| `Views/TournamentDashboardView.swift` | Reordered per §B; wired strip + next-action card |
| `Data/FakeData.swift` | Multi-match envelope: 2 singles + 1 doubles plan; each Plan has `matchId`+`nextAction`+`scheduledStart` |
