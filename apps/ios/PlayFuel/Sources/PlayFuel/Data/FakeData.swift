// ──────────────────────────────────────────────────────────────────────────
// FakeData (Preview-only as of Task #6 — iOS ↔ API wiring)
//
// Production data flow (Task #6+):
//   SignInView → AuthService → APIClient → Repository → AppState → Views
//
// This file remains the single source of truth for SwiftUI #Preview blocks
// because previews cannot make network calls. It is also spliced into the
// hybrid Plan envelope by Repository.assembleHybridPlan for `weather`,
// `foodOptions`, and `timeline` until Phase 4 (Task #7 weather) and Phase 5
// (Task #8 food/places) replace those splices with real API data.
//
// Keep the shape in sync with the API response (camelCase fields, mirrors
// backend §G ScenarioPlan). Do not change any verbatim disclaimer or
// heat-emergency text without updating HardCodedStrings.swift first.
// ──────────────────────────────────────────────────────────────────────────
import Foundation

// MARK: - FakeData
//
// Single source of all prototype data. All structs mirror the exact API response
// shapes defined in RULES_CONSTANTS_V1 (§G ScenarioPlan) and spec §13.
//
// Phase 3 swap: replace the static `let` values below with decoded API responses
// from the FastAPI backend. No View code changes required.
//
// Dallas Canonical Demo: RULES_CONSTANTS_V1 §B.4
//   Match 1: 9:00 AM | Match 2 est: 1:00 PM | Weather: 88°F, 72% humidity
//   → flags: [.hot, .humid] → extremeHeatRisk = true

enum FakeData {

    // MARK: - Tournaments

    static let tournaments: [Tournament] = [
        dallasTournament,
        austinTournament,
        houstonTournament
    ]

    /// Primary demo tournament — Dallas §B.4
    static let dallasTournament = Tournament(
        id: UUID(uuidString: "11111111-0000-0000-0000-000000000001")!,
        name: "Dallas Spring Open",
        venue: "Samuell Grand Tennis Center",
        lat: 32.7767,
        lon: -96.7970,
        startDate: "2026-04-26",
        endDate: "2026-04-27"
    )

    /// Stub tournament — lighter-weight, no full plan
    static let austinTournament = Tournament(
        id: UUID(uuidString: "22222222-0000-0000-0000-000000000002")!,
        name: "Austin Junior Classic",
        venue: "Pharr Tennis Center",
        lat: 30.2672,
        lon: -97.7431,
        startDate: "2026-05-10",
        endDate: "2026-05-11"
    )

    /// Stub tournament — lighter-weight, no full plan
    static let houstonTournament = Tournament(
        id: UUID(uuidString: "33333333-0000-0000-0000-000000000003")!,
        name: "Houston Hardcourt Open",
        venue: "Memorial Park Tennis Center",
        lat: 29.7604,
        lon: -95.3698,
        startDate: "2026-06-07",
        endDate: "2026-06-08"
    )

    // MARK: - Match (Dallas)

    static let dallasMatch = Match(
        id: UUID(uuidString: "AAAA0000-0000-0000-0000-000000000001")!,
        tournamentId: dallasTournament.id,
        scheduledTime: "9:00 AM",
        estimatedNextMatchTime: "1:00 PM",
        round: "Round of 16",
        opponent: "T. Anderson",
        court: "Court 4"
    )

    // MARK: - Weather (Dallas)
    //
    // tempF = 88 → flag: .hot (≥85, <90 → NOT .very_hot)
    // humidity = 72 → flag: .humid (≥65)
    // extremeHeatRisk = hot AND humid = true (§E.2)

    static let dallasWeather = WeatherSnapshot(
        tempF: 88,
        humidity: 72,
        windMph: 8,
        precipProb: 10,
        uvIndex: 8,
        flags: [.hot, .humid]
    )

    // MARK: - Scenario Plans (Dallas §B.4)
    //
    // gap formula: gap = 13:00 − (9:00 + duration_min)
    //   short:  gap = 240 − 75  = 165 min → light_meal  | wait_until_end
    //   normal: gap = 240 − 120 = 120 min → quick_pickup | wait_until_end
    //   long:   gap = 240 − 180 = 60  min → portable     | pickup_during_match

    static let dallasShortScenario = ScenarioPlan(
        id: UUID(uuidString: "BBBB0001-0000-0000-0000-000000000001")!,
        scenario: "short",
        durationMin: 75,
        estimatedEnd: "10:15 AM",
        gapMinutes: 165,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .light_meal,
            // Verbatim §B.2 text for light_meal bucket
            text: "There is enough time for a light meal, but avoid heavy/greasy foods."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .wait_until_end,
            // Verbatim §B.3 text for wait_until_end bucket
            text: "Parent can likely wait until the match ends before getting food."
        ),
        rewarmUp: RewarmUp(
            startOffsetMin: -30,   // T-30 min before 1:00 PM = 12:30 PM (§D.2)
            durationMin: 20
        ),
        overrunWarning: nil,
        warnings: []
    )

    static let dallasNormalScenario = ScenarioPlan(
        id: UUID(uuidString: "BBBB0002-0000-0000-0000-000000000002")!,
        scenario: "normal",
        durationMin: 120,
        estimatedEnd: "11:00 AM",
        gapMinutes: 120,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .quick_pickup,
            // OQ-13 resolution: gap=120 → [90,150) → quick_pickup (NOT light_meal)
            text: "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .wait_until_end,
            // gap=120 → [120,∞) → wait_until_end (boundary case: 120 is exactly the threshold)
            text: "Parent can likely wait until the match ends before getting food."
        ),
        rewarmUp: RewarmUp(
            startOffsetMin: -30,
            durationMin: 20
        ),
        overrunWarning: nil,
        warnings: []
    )

    static let dallasLongScenario = ScenarioPlan(
        id: UUID(uuidString: "BBBB0003-0000-0000-0000-000000000003")!,
        scenario: "long",
        durationMin: 180,
        estimatedEnd: "12:00 PM",
        gapMinutes: 60,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .portable,
            // Verbatim §B.2 text for portable bucket
            text: "Use pre-bought portable food immediately after match. Avoid waiting in line."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .pickup_during_match,
            // gap=60 → [60,120) → pickup_during_match (§B.3)
            text: "If match is trending long, parent should pick up food during the final portion of the match if another trusted adult is present."
        ),
        rewarmUp: RewarmUp(
            startOffsetMin: -30,
            durationMin: 20
        ),
        overrunWarning: nil,
        warnings: []
    )

    // MARK: - Food Options (Dallas)
    //
    // §F.3: fast_casual_bowl text is CONFIRMED per USER_STORIES.md US-08.
    // sandwich_shop and grocery_prepared are [DRAFT — OQ-B].

    static let dallasFoodOptions: [FoodOption] = [
        FoodOption(
            id: UUID(uuidString: "CC000001-0000-0000-0000-000000000001")!,
            name: "Chipotle Mexican Grill",
            // §F.3 confirmed template
            category: "fast_casual_bowl",
            driveTimeMin: 5,
            // Verbatim §F.3 / USER_STORIES US-08
            recommendedOrder: "Chicken rice bowl with light beans, mild toppings, sauce on the side"
        ),
        FoodOption(
            id: UUID(uuidString: "CC000002-0000-0000-0000-000000000002")!,
            name: "Jimmy John's",
            category: "sandwich_shop",  // [DRAFT — OQ-B]
            driveTimeMin: 8,
            recommendedOrder: "Turkey sandwich on French bread, no heavy sauces, add avocado if tolerated"  // [DRAFT — OQ-B]
        ),
        FoodOption(
            id: UUID(uuidString: "CC000003-0000-0000-0000-000000000003")!,
            name: "Central Market",
            category: "grocery_prepared",  // [DRAFT — OQ-B]
            driveTimeMin: 12,
            recommendedOrder: "Prepared deli chicken, plain rice, fruit cup from deli section"  // [DRAFT — OQ-B]
        )
    ]

    // MARK: - Timeline Events (Dallas)
    //
    // Offsets based on 9:00 AM match start (§D.1 DRAFT values — OQ-C).
    // Re-warm-up at 12:30 PM = T-30 min before 1:00 PM Match 2 (§D.2).

    static let dallasTimeline: [TimelineEvent] = [
        TimelineEvent(
            id: UUID(uuidString: "DD000001-0000-0000-0000-000000000001")!,
            time: "6:00 AM",
            title: "Wake Up",
            detail: "T−3h before match start. Hydrate immediately. [DRAFT — OQ-C: offset pending confirmation]",
            kind: .wakeUp
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000002-0000-0000-0000-000000000002")!,
            time: "6:30 AM",
            title: "Pre-Match Meal",
            detail: "T−2.5h window. Light, familiar meal tolerated well. Avoid heavy/greasy foods. [DRAFT — OQ-C]",
            kind: .meal
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000003-0000-0000-0000-000000000003")!,
            time: "8:00 AM",
            title: "Arrive at Venue",
            detail: "T−1h. Light snack if tolerated. Begin hydration load. [DRAFT — OQ-C]",
            kind: .arrive
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000004-0000-0000-0000-000000000004")!,
            time: "8:30 AM",
            title: "Dynamic Warm-Up",
            detail: "T−30min, 20-minute active movement warm-up. [DRAFT — OQ-C]",
            kind: .warmUp
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000005-0000-0000-0000-000000000005")!,
            time: "8:50 AM",
            title: "Court Warm-Up",
            detail: "T−10min. On-court with opponent.",
            kind: .warmUp
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000006-0000-0000-0000-000000000006")!,
            time: "9:00 AM",
            title: "Match 1 Start",
            detail: "Round of 16 vs. T. Anderson — Court 4. 88°F / 72% humidity.",
            kind: .match
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000007-0000-0000-0000-000000000007")!,
            time: "During Match",
            title: "Hydration — Changeovers",
            detail: "Drink fluids every changeover. Electrolyte drink recommended given hot + humid conditions. [DRAFT — OQ-A: quantities pending]",
            kind: .hydration
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000008-0000-0000-0000-000000000008")!,
            time: "~11:00 AM",
            title: "Match 1 End (Normal Scenario)",
            detail: "Exit court. Cool down immediately — find shade, cool water, rest.",
            kind: .recovery
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000009-0000-0000-0000-000000000009")!,
            time: "11:30 AM",
            title: "Post-Match Lunch",
            detail: "Quick pickup window. Turkey sandwich or rice bowl. Avoid heavy/greasy foods.",
            kind: .meal
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000010-0000-0000-0000-000000000010")!,
            time: "12:30 PM",
            title: "Re-Warm-Up",
            detail: "T−30min before Match 2. 20-minute dynamic warm-up. [§D.2]",
            kind: .warmUp
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000011-0000-0000-0000-000000000011")!,
            time: "1:00 PM",
            title: "Match 2 Start (Estimated)",
            detail: "Estimated next match. Confirm with tournament desk.",
            kind: .match
        ),
        TimelineEvent(
            id: UUID(uuidString: "DD000012-0000-0000-0000-000000000012")!,
            time: "Post-Match",
            title: "Recovery",
            detail: "Shade, cool fluids, light recovery snack. Monitor for heat illness symptoms.",
            kind: .recovery
        )
    ]

    // MARK: - Full Dallas Plan

    static let dallasPlan = Plan(
        id: UUID(uuidString: "EEEE0001-0000-0000-0000-000000000001")!,
        planId: "dallas-2026-04-26-v1",
        tournamentId: dallasTournament.id,
        generatedAt: "2026-04-26T09:00:00Z",
        warnings: [],   // no overruns in Dallas demo
        scenarioPlans: [
            dallasShortScenario,
            dallasNormalScenario,
            dallasLongScenario
        ],
        weather: dallasWeather,
        foodOptions: dallasFoodOptions,
        timeline: dallasTimeline
    )

    // MARK: - Plan Lookup

    /// Returns the Plan for a given tournament ID, or nil if no plan exists.
    /// Phase 3: replace with `GET /tournaments/{id}/plans/latest` API call.
    static func plan(for tournamentId: UUID) -> Plan? {
        switch tournamentId {
        case dallasTournament.id:
            return dallasPlan
        default:
            return nil  // Austin + Houston are stubs with no plan yet
        }
    }

    /// Returns the Match for a given tournament ID, or nil.
    static func match(for tournamentId: UUID) -> Match? {
        switch tournamentId {
        case dallasTournament.id:
            return dallasMatch
        default:
            return nil
        }
    }
}
