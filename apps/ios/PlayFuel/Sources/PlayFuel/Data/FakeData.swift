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
        court: "Court 4",
        format: nil,
        doublesFormat: nil
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
    // sandwich_shop, grocery_prepared, breakfast_cafe are [DRAFT — OQ-B].
    //
    // Phase 9: structured FoodSuggestions added per FOOD_DECK_AND_MAP_V1.md §A.3.
    // Coordinates are best-guess for Uptown Dallas demo area (OQ-FOOD-DECK-3).
    // Starbucks added per PM Verification Finding I-4 (user's literal example).

    static let dallasFoodOptions: [FoodOption] = [
        FoodOption(
            id: UUID(uuidString: "CC000001-0000-0000-0000-000000000001")!,
            name: "Chipotle Mexican Grill",
            // §F.3 confirmed template
            category: "fast_casual_bowl",
            driveTimeMin: 5,
            // Verbatim §F.3 / USER_STORIES US-08
            recommendedOrder: "Chicken rice bowl with light beans, mild toppings, sauce on the side",
            isDraft: false,
            distanceMeters: 600,
            placeId: nil,
            provider: "fake",
            suggestions: FoodSuggestions(
                mainOptions: [
                    "Rice bowl: brown or white rice base",
                    "Add black beans, grilled chicken or steak",
                    "Add fresh salsa and lettuce"
                ],
                addOns: [],
                drinks: ["16–20 oz water"],
                avoid: [
                    "Sour cream",
                    "Cheese",
                    "Guacamole — keep fat and fiber low before competition"
                ],
                notes: ["Eat 60–90 min before next match"]
            ),
            lat: 32.7825,
            lng: -96.7975
        ),
        FoodOption(
            id: UUID(uuidString: "CC000002-0000-0000-0000-000000000002")!,
            name: "Jimmy John's",
            category: "sandwich_shop",  // [DRAFT — OQ-B]
            driveTimeMin: 8,
            recommendedOrder: "Turkey sandwich on French bread, no heavy sauces",  // [DRAFT — OQ-B]
            isDraft: true,
            distanceMeters: 900,
            placeId: nil,
            provider: "fake",
            suggestions: FoodSuggestions(
                mainOptions: [
                    "Turkey or chicken on whole-grain bread",
                    "Add lettuce, tomato, mustard"
                ],
                addOns: ["Baked chips or pretzels if gap allows"],
                drinks: ["Water or diluted sports drink"],
                avoid: [
                    "Heavy sauces and extra cheese",
                    "Oil-based dressings"
                ],
                notes: ["Eat within 30 min of ordering. DRAFT — confirm with your athlete."]
            ),
            lat: 32.7820,
            lng: -96.8025
        ),
        FoodOption(
            id: UUID(uuidString: "CC000003-0000-0000-0000-000000000003")!,
            name: "Central Market",
            category: "grocery_prepared",  // [DRAFT — OQ-B]
            driveTimeMin: 12,
            recommendedOrder: "Prepared deli chicken, plain rice, fruit cup from deli section",  // [DRAFT — OQ-B]
            isDraft: true,
            distanceMeters: 1400,
            placeId: nil,
            provider: "fake",
            suggestions: FoodSuggestions(
                mainOptions: [
                    "Rotisserie chicken with rice",
                    "Prepared grain bowl — lean protein + complex carbs"
                ],
                addOns: ["Fresh fruit for post-match recovery"],
                drinks: ["Water or electrolyte drink"],
                avoid: ["Fried items", "Heavy cream-based dishes"],
                notes: ["Eat 60–90 min before play. DRAFT — confirm with your athlete."]
            ),
            lat: 32.7755,
            lng: -96.7920
        ),
        // PM Verification Finding I-4: Starbucks missing from FakeData despite being a
        // MockPlacesProvider fixture. User's literal example ("click into Starbucks and see oats").
        FoodOption(
            id: UUID(uuidString: "CC000004-0000-0000-0000-000000000004")!,
            name: "Starbucks",
            category: "breakfast_cafe",  // [DRAFT — OQ-B]
            driveTimeMin: 5,
            recommendedOrder: "Oatmeal with banana, water",  // [DRAFT — OQ-B]
            isDraft: true,
            distanceMeters: 480,
            placeId: nil,
            provider: "fake",
            suggestions: FoodSuggestions(
                mainOptions: [
                    "Oatmeal (plain or lightly sweetened)",
                    "Whole-grain item with eggs if available"
                ],
                addOns: ["Banana or fruit cup — easy carb bridge"],
                drinks: [
                    "Water (primary)",
                    "Small black coffee or tea if tolerated"
                ],
                avoid: [
                    "Pastries and muffins — high sugar spike",
                    "Large milk-based drinks close to match time",
                    "High-sugar syrups and flavored drinks"
                ],
                notes: ["Eat ≥45 min before play. DRAFT — confirm with your athlete."]
            ),
            lat: 32.7805,
            lng: -96.7990
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

    // MARK: - LLM Summary (Dallas — TemplateProvider output)
    //
    // Fake PlanExplanation mirroring what TemplateProvider would produce for the
    // Dallas demo input. `safetyNote` is §B emergency text (prepended, because
    // extremeHeatRisk=true) followed by \n\n then the verbatim §A disclaimer.
    // All content originates from the structured plan — no invented facts.

    static let dallasPlanExplanation = PlanExplanation(
        summary: "Saturday Round of 16 at Samuell Grand Tennis Center starts at 9:00 AM. Hot and humid conditions (88°F / 72% humidity) — plan extra hydration and shade between points. Most likely scenario: a normal-length match (~2 hrs) with a comfortable break before the next round at 1:00 PM.",
        scenarioExplanations: [
            "short": "If the match wraps in ~75 minutes, you'll have a long break (2 hrs 45 min) before the next round. Plenty of time for a light meal — avoid heavy or greasy foods. Banana, pretzels, and an electrolyte drink work well as a bridge snack right after the match.",
            "normal": "A typical ~2-hour match leaves a comfortable 2-hour break. A quick fast-casual pickup nearby is a solid choice — Chipotle's chicken rice bowl (light beans, mild toppings, sauce on the side) is a good option at ~5 min drive.",
            "long": "A longer match (~3 hours) leaves only a 1-hour gap before the next round. Pre-bought portable food is the priority — bring a turkey sandwich or rice bowl from home. If a trusted adult can leave during the final portion to pick up food, that's ideal."
        ],
        weatherNote: "Expect 88°F with 72% humidity — heat index will feel higher. Keep shade and cool water available between points and during changeovers.",
        foodNote: "Nearby options include Chipotle (~5 min, fast casual bowl) and Jimmy John's (~8 min, sandwich shop). Central Market (~12 min) is a good grocery backup for prepared items.",
        safetyNote: "If your player feels faint or confused, has chest pain, stops sweating in extreme heat, has severe cramps, vomits repeatedly, or shows signs of heat illness: stop play and seek medical help. Call 911 (or your local emergency number) in an emergency.\n\nThis app provides general tournament preparation guidance. It is not medical advice, nutrition therapy, or a substitute for a coach, physician, athletic trainer, or registered dietitian. For injuries, illness, heat symptoms, allergies, eating disorders, or medical conditions, consult a qualified professional.",
        provider: "template",
        model: nil,
        generatedAt: Date(timeIntervalSince1970: 1745661600) // 2026-04-26T09:00:00Z
    )

    // MARK: - Match IDs (Phase 8 — per-match plan anchoring)

    /// Fixed match UUIDs for preview determinism — mirrors server-side match rows.
    static let matchIdSingles1 = UUID(uuidString: "AAAA0001-0000-0000-0000-000000000001")!
    static let matchIdSingles2 = UUID(uuidString: "AAAA0002-0000-0000-0000-000000000002")!
    static let matchIdDoubles1 = UUID(uuidString: "AAAA0003-0000-0000-0000-000000000003")!

    // MARK: - Next Actions (Phase 8)

    /// Fake NextAction for Singles Plan 1 (R16, 9 AM — pre-match meal in window).
    static let dallasNextAction1 = NextAction(
        title: "Pre-match meal",
        detail: "Light, easy carbs — see food options below",
        scheduledFor: Date(timeIntervalSince1970: 1745647200),  // 6:30 AM CDT 2026-04-26
        kind: "pre_match_meal",
        minsUntil: 28
    )

    /// Fake NextAction for Singles Plan 2 (QF, 1 PM — match start in window).
    static let dallasNextAction2 = NextAction(
        title: "Match 2 Start",
        detail: "Head to court for warm-up",
        scheduledFor: Date(timeIntervalSince1970: 1745676000),  // 1:00 PM CDT 2026-04-26
        kind: "match_start",
        minsUntil: 45
    )

    /// Fake NextAction for Doubles Plan 1 (best_of_3, 3 PM).
    static let dallasNextActionDoubles = NextAction(
        title: "Confirm partner warm-up time",
        detail: "Confirm warm-up time with your player's partner",
        scheduledFor: Date(timeIntervalSince1970: 1745683200),  // 3:00 PM CDT 2026-04-26
        kind: "partner_coordination",
        minsUntil: 120
    )

    // MARK: - Full Dallas Plan (Singles — Match 1, R16 9 AM)
    //
    // Phase 8: now carries matchId + nextAction + scheduledStart.

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
        timeline: dallasTimeline,
        bagFallbackOnly: false,
        llmSummary: dallasPlanExplanation,
        matchType: .singles,
        matchId: matchIdSingles1,
        nextAction: dallasNextAction1,
        scheduledStart: "2026-04-26T09:00:00Z"
    )

    // MARK: - Dallas Singles Plan 2 (QF, 1:00 PM)
    //
    // The second singles match of the day. Uses the same scenarios/food/timeline
    // as Plan 1 for prototype purposes.

    static let dallasSinglesPlan2 = Plan(
        id: UUID(uuidString: "EEEE0003-0000-0000-0000-000000000003")!,
        planId: "dallas-2026-04-26-qf-v1",
        tournamentId: dallasTournament.id,
        generatedAt: "2026-04-26T09:00:00Z",
        warnings: [],
        scenarioPlans: [
            dallasShortScenario,
            dallasNormalScenario,
            dallasLongScenario
        ],
        weather: dallasWeather,
        foodOptions: dallasFoodOptions,
        timeline: dallasTimeline,
        bagFallbackOnly: false,
        llmSummary: dallasPlanExplanation,
        matchType: .singles,
        matchId: matchIdSingles2,
        nextAction: dallasNextAction2,
        scheduledStart: "2026-04-26T13:00:00Z"
    )

    /// Alias for ScheduleStripView preview (Plan 1 = first singles match).
    static var dallasSinglesPlan1: Plan { dallasPlan }

    // MARK: - Dallas Doubles Plan (best_of_3)
    //
    // Fake plan mirroring what the backend would produce for a doubles best_of_3 match.
    // Durations: short=60, normal=90, long=135 (DOUBLES_SPEC_V1.md §B.1 — [DRAFT OQ-DBL-1]).
    // Gap math (9:00 AM match, 1:00 PM next):
    //   short:  gap = 240−60  = 180 min → light_meal   + wait_until_end (≥120)
    //   normal: gap = 240−90  = 150 min → light_meal   + wait_until_end (≥120)
    //   long:   gap = 240−135 = 105 min → quick_pickup + pickup_during_match ([60,120))

    static let dallasDoublesShortScenario = ScenarioPlan(
        id: UUID(uuidString: "FFFF0001-0000-0000-0000-000000000001")!,
        scenario: "short",
        durationMin: 60,
        estimatedEnd: "10:00 AM",
        gapMinutes: 180,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .light_meal,
            text: "There is enough time for a light meal, but avoid heavy/greasy foods."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .wait_until_end,
            text: "Parent can likely wait until the match ends before getting food."
        ),
        rewarmUp: RewarmUp(startOffsetMin: -30, durationMin: 20),
        overrunWarning: nil,
        warnings: []
    )

    static let dallasDoublesNormalScenario = ScenarioPlan(
        id: UUID(uuidString: "FFFF0002-0000-0000-0000-000000000002")!,
        scenario: "normal",
        durationMin: 90,
        estimatedEnd: "10:30 AM",
        gapMinutes: 150,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .light_meal,
            text: "There is enough time for a light meal, but avoid heavy/greasy foods."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .wait_until_end,
            text: "Parent can likely wait until the match ends before getting food."
        ),
        rewarmUp: RewarmUp(startOffsetMin: -30, durationMin: 20),
        overrunWarning: nil,
        warnings: []
    )

    static let dallasDoublesLongScenario = ScenarioPlan(
        id: UUID(uuidString: "FFFF0003-0000-0000-0000-000000000003")!,
        scenario: "long",
        durationMin: 135,
        estimatedEnd: "11:15 AM",
        gapMinutes: 105,
        gapStatus: .ok,
        foodStrategy: FoodStrategy(
            bucket: .quick_pickup,
            text: "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal."
        ),
        pickupStrategy: PickupStrategy(
            bucket: .pickup_during_match,
            text: "If match is trending long, parent should pick up food during the final portion of the match if another trusted adult is present."
        ),
        rewarmUp: RewarmUp(startOffsetMin: -30, durationMin: 20),
        overrunWarning: nil,
        warnings: []
    )

    // LLM summary for the doubles plan — uses doubles-team voice per §C.2.
    static let dallasPlanExplanationDoubles = PlanExplanation(
        summary: "Saturday doubles at Samuell Grand Tennis Center starts at 9:00 AM. Hot and humid conditions (88°F / 72% humidity) — you and your partner should plan extra hydration and shade between points. Most likely scenario: a normal-length doubles match (~90 min, best of 3) with a comfortable break before the next round at 1:00 PM.",
        scenarioExplanations: [
            "short": "If your doubles team wraps in ~60 minutes, you’ll have a 3-hour break. Plenty of time for a light meal — avoid heavy or greasy foods. Agree with your partner on a quick lunch spot before the match.",
            "normal": "A typical ~90-minute doubles match leaves a comfortable 2.5-hour break. A fast-casual pickup is a solid choice for both you and your partner — Chipotle’s chicken rice bowl (~5 min drive) works well.",
            "long": "A longer match (~135 min) leaves under 2 hours before the next round. Pre-bought portable food is the priority for your doubles team — coordinate with your partner before the match."
        ],
        weatherNote: "Expect 88°F with 72% humidity — heat index will feel higher for both players. Keep shade and cool water available at the court changeovers.",
        foodNote: "Nearby options include Chipotle (~5 min) and Jimmy John’s (~8 min). Consider ordering for both players to save time.",
        safetyNote: "If your player feels faint or confused, has chest pain, stops sweating in extreme heat, has severe cramps, vomits repeatedly, or shows signs of heat illness: stop play and seek medical help. Call 911 (or your local emergency number) in an emergency.\n\nThis app provides general tournament preparation guidance. It is not medical advice, nutrition therapy, or a substitute for a coach, physician, athletic trainer, or registered dietitian. For injuries, illness, heat symptoms, allergies, eating disorders, or medical conditions, consult a qualified professional.",
        provider: "template",
        model: nil,
        generatedAt: Date(timeIntervalSince1970: 1745661600)
    )

    static let dallasDoublesPlan = Plan(
        id: UUID(uuidString: "EEEE0002-0000-0000-0000-000000000002")!,
        planId: "dallas-doubles-2026-04-26-v1",
        tournamentId: dallasTournament.id,
        generatedAt: "2026-04-26T09:00:00Z",
        warnings: [],
        scenarioPlans: [
            dallasDoublesShortScenario,
            dallasDoublesNormalScenario,
            dallasDoublesLongScenario
        ],
        weather: dallasWeather,
        foodOptions: dallasFoodOptions,
        timeline: dallasTimeline,
        bagFallbackOnly: false,
        llmSummary: dallasPlanExplanationDoubles,
        matchType: .doubles,
        matchId: matchIdDoubles1,
        nextAction: dallasNextActionDoubles,
        scheduledStart: "2026-04-26T15:00:00Z"
    )

    /// Alias for multi-match envelope (Doubles Match 1 = first doubles plan).
    static var dallasDoublesPlan1: Plan { dallasDoublesPlan }

    // MARK: - Plan Envelope (Phase 8 — arrays, one plan per match)
    //
    // Multi-match Dallas envelope for preview:
    //   singlesPlans: [R16 @ 9:00 AM, QF @ 1:00 PM]
    //   doublesPlans: [Doubles QF @ 3:00 PM, best_of_3]
    // Used by TournamentDashboardView #Preview to show the schedule strip + picker.

    static let dallasPlanEnvelope = PlanEnvelope(
        singlesPlans: [dallasSinglesPlan1, dallasSinglesPlan2],
        doublesPlans: [dallasDoublesPlan1]
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
