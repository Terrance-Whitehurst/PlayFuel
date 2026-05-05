import XCTest
@testable import PlayFuel

/// Unit tests for ScenarioDetailHelpers pure functions.
///
/// These tests are the QA hook for SCENARIO_CARD_POPOUT_V1.md §G.1.
/// All functions under test are pure Swift (no SwiftUI) — runnable via `swift test`.
///
/// Test coverage:
///   - summarySentence(kind:status:)  — all 12 cells (3 scenarios × 4 gap statuses)
///   - parentActionBullets(scenario:) — all 7 rows + default fallback
///   - filteredFoodOptions(scenario:all:) — 7 filter + sort cases
final class ScenarioDetailHelpersTests: XCTestCase {

    // MARK: - Fixtures

    /// Minimal FoodOption fixture factory.
    private func makeFoodOption(
        name: String = "Test Restaurant",
        category: String = "fast_casual_bowl",
        driveTimeMin: Int? = nil,
        distanceMeters: Int? = nil
    ) -> FoodOption {
        FoodOption(
            id: UUID(),
            name: name,
            category: category,
            driveTimeMin: driveTimeMin,
            recommendedOrder: "Test order",
            isDraft: false,
            distanceMeters: distanceMeters,
            placeId: nil,
            provider: "test",
            suggestions: nil,
            lat: nil,
            lng: nil,
            chainMatched: false,
            chainAsOf: nil
        )
    }

    /// Minimal ScenarioPlan fixture factory.
    private func makeScenario(
        kind: String = "normal",
        gapStatus: GapStatus = .ok,
        foodBucket: FoodBucket? = .quick_pickup,
        pickupBucket: PickupBucket? = .wait_until_end,
        hasRewarm: Bool = true
    ) -> ScenarioPlan {
        ScenarioPlan(
            id: UUID(),
            scenario: kind,
            durationMin: 120,
            estimatedEnd: "11:00 AM",
            gapMinutes: gapStatus == .no_next_match ? nil : (gapStatus == .overrun ? -15 : 120),
            gapStatus: gapStatus,
            foodStrategy: foodBucket.map { FoodStrategy(bucket: $0, text: "Test food strategy") },
            pickupStrategy: PickupStrategy(
                bucket: pickupBucket,
                text: "Test pickup strategy"
            ),
            rewarmUp: hasRewarm ? RewarmUp(startOffsetMin: -30, durationMin: 20) : nil,
            overrunWarning: gapStatus == .overrun ? OverrunWarning(
                code: "MATCH_OVERRUN",
                severity: "high",
                minutesOver: 15,
                message: "Overrun"
            ) : nil,
            warnings: gapStatus == .overrun ? ["MATCH_OVERRUN"] : []
        )
    }

    // MARK: - §C.2 summarySentence — all 12 cells

    func test_summarySentence_short_ok() {
        XCTAssertEqual(
            ScenarioDetailHelpers.summarySentence(kind: "short", status: .ok),
            "Your player's match should wrap up in about 75 minutes, leaving solid time before the next one."
        )
    }

    func test_summarySentence_short_tight() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "short", status: .tight)
        XCTAssertTrue(result.hasPrefix("Your player's match should wrap up in about 75 minutes, but the window"))
    }

    func test_summarySentence_short_overrun() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "short", status: .overrun)
        XCTAssertTrue(result.hasPrefix("Even with a short match, the schedule is too tight"))
    }

    func test_summarySentence_short_noNextMatch() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "short", status: .no_next_match)
        XCTAssertTrue(result.contains("last match today"))
    }

    func test_summarySentence_normal_ok() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "normal", status: .ok)
        XCTAssertTrue(result.hasPrefix("Your player's match is expected to take about 2 hours, leaving"))
    }

    func test_summarySentence_normal_tight() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "normal", status: .tight)
        XCTAssertTrue(result.contains("gap before the next match is short"))
    }

    func test_summarySentence_normal_overrun() {
        XCTAssertEqual(
            ScenarioDetailHelpers.summarySentence(kind: "normal", status: .overrun),
            "With a 2-hour match, the schedule is very tight \u{2014} the next match may start before this one ends."
        )
    }

    func test_summarySentence_normal_noNextMatch() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "normal", status: .no_next_match)
        XCTAssertTrue(result.contains("focus on recovery after"))
    }

    func test_summarySentence_long_ok() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "long", status: .ok)
        XCTAssertTrue(result.hasPrefix("Your player's match could run up to 3 hours"))
    }

    func test_summarySentence_long_tight() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "long", status: .tight)
        XCTAssertTrue(result.contains("have bag food ready now"))
    }

    func test_summarySentence_long_overrun() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "long", status: .overrun)
        XCTAssertTrue(result.contains("alert the tournament desk"))
    }

    func test_summarySentence_long_noNextMatch() {
        XCTAssertEqual(
            ScenarioDetailHelpers.summarySentence(kind: "long", status: .no_next_match),
            "Your player's match could run up to 3 hours \u{2014} this is the last match today, so plan for a proper recovery meal after."
        )
    }

    func test_summarySentence_unknownKind_returnsGenericFallback() {
        let result = ScenarioDetailHelpers.summarySentence(kind: "unknown_kind", status: .ok)
        // Default fallback — must not be empty and must not crash.
        XCTAssertFalse(result.isEmpty)
        XCTAssertTrue(result.contains("food ready for your player"))
    }

    // MARK: - §C.3 parentActionBullets — all 7 rows

    // Row 1: no_next_match → recovery framing, 4 bullets
    func test_bullets_row1_noNextMatch() {
        let scenario = makeScenario(gapStatus: .no_next_match, foodBucket: nil, pickupBucket: nil, hasRewarm: false)
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 4)
        XCTAssertTrue(bullets[0].hasPrefix("This is your player's last match of the day."))
        XCTAssertTrue(bullets[1].contains("lean protein and carbs"))
        XCTAssertTrue(bullets[2].contains("electrolyte drink"))
        XCTAssertTrue(bullets[3].contains("cooling down and stretching"))
    }

    // Row 2: bag_only + bring_portable + no rewarm → 4 bullets
    func test_bullets_row2_bagOnly_bringPortable_noRewarm() {
        let scenario = makeScenario(
            gapStatus: .overrun,
            foodBucket: .bag_only,
            pickupBucket: .bring_portable,
            hasRewarm: false
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 4)
        XCTAssertTrue(bullets[0].hasPrefix("Pack a bag with banana"))
        XCTAssertTrue(bullets[1].contains("no time for a restaurant run"))
        XCTAssertTrue(bullets[3].contains("head to the next court"))
    }

    // Row 3: portable + bring_portable + no rewarm → 4 bullets
    func test_bullets_row3_portable_bringPortable_noRewarm() {
        let scenario = makeScenario(
            foodBucket: .portable,
            pickupBucket: .bring_portable,
            hasRewarm: false
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 4)
        XCTAssertTrue(bullets[0].contains("before the match starts"))
        XCTAssertTrue(bullets[1].contains("within 5 min drive"))
        XCTAssertTrue(bullets[3].contains("skip sitting down"))
    }

    // Row 4: portable + pickup_during_match + rewarm → 4 bullets
    func test_bullets_row4_portable_pickupDuringMatch_rewarm() {
        let scenario = makeScenario(
            foodBucket: .portable,
            pickupBucket: .pickup_during_match,
            hasRewarm: true
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 4)
        XCTAssertTrue(bullets[0].contains("trusted adult can stay courtside"))
        XCTAssertTrue(bullets[3].contains("dynamic warm-up"))
    }

    // Row 5: quick_pickup + pickup_during_match + rewarm → 4 bullets
    func test_bullets_row5_quickPickup_pickupDuringMatch_rewarm() {
        let scenario = makeScenario(
            foodBucket: .quick_pickup,
            pickupBucket: .pickup_during_match,
            hasRewarm: true
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 4)
        XCTAssertTrue(bullets[0].contains("Order ahead at a quick-pickup spot"))
        XCTAssertTrue(bullets[0].contains("8 min"))
        XCTAssertTrue(bullets[2].contains("final set"))
    }

    // Row 6: quick_pickup + wait_until_end + rewarm → 5 bullets
    func test_bullets_row6_quickPickup_waitUntilEnd_rewarm() {
        let scenario = makeScenario(
            foodBucket: .quick_pickup,
            pickupBucket: .wait_until_end,
            hasRewarm: true
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 5)
        XCTAssertTrue(bullets[0].contains("Wait until the match ends"))
        XCTAssertTrue(bullets[4].contains("order ahead online"))
    }

    // Row 7: light_meal + wait_until_end + rewarm → 5 bullets
    func test_bullets_row7_lightMeal_waitUntilEnd_rewarm() {
        let scenario = makeScenario(
            foodBucket: .light_meal,
            pickupBucket: .wait_until_end,
            hasRewarm: true
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertEqual(bullets.count, 5)
        XCTAssertTrue(bullets[0].contains("light sit-down meal"))
        XCTAssertTrue(bullets[1].contains("grilled chicken"))
        XCTAssertTrue(bullets[3].contains("90 min before the next match"))
    }

    // Default fallback — artificial combo not produced by rules engine
    func test_bullets_defaultFallback_returnsMinimalBullets() {
        // Construct an impossible combo: light_meal + bring_portable (not engine-produced)
        let scenario = makeScenario(
            foodBucket: .light_meal,
            pickupBucket: .bring_portable,
            hasRewarm: false
        )
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        // Defensive fallback: at least 1 bullet, not empty.
        XCTAssertFalse(bullets.isEmpty)
        XCTAssertTrue(bullets[0].contains("food ready for your player"))
    }

    // MARK: - §C.4 filteredFoodOptions — 7 filter + sort cases

    // Case 1: bag_only scenario → [] regardless of food_options content
    func test_filter_bagOnly_returnsEmpty() {
        let scenario = makeScenario(gapStatus: .ok, foodBucket: .bag_only, hasRewarm: false)
        let options = [makeFoodOption(driveTimeMin: 3), makeFoodOption(driveTimeMin: 5)]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 0)
    }

    // Case 2: overrun scenario → [] (gapStatus guard)
    func test_filter_overrun_returnsEmpty() {
        let scenario = makeScenario(gapStatus: .overrun, foodBucket: .portable, hasRewarm: false)
        let options = [makeFoodOption(driveTimeMin: 2), makeFoodOption(driveTimeMin: 4)]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 0)
    }

    // Case 3: portable (max=5) — drives [3, 6, 10] → only [3] included
    func test_filter_portable_maxDrive5_filtersCorrectly() {
        let scenario = makeScenario(foodBucket: .portable, pickupBucket: .bring_portable, hasRewarm: false)
        let options = [
            makeFoodOption(name: "A", driveTimeMin: 3, distanceMeters: 300),
            makeFoodOption(name: "B", driveTimeMin: 6, distanceMeters: 200),
            makeFoodOption(name: "C", driveTimeMin: 10, distanceMeters: 100)
        ]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result[0].name, "A")
    }

    // Case 4: quick_pickup (max=8) — drives [5, 8, 12] → [5, 8] included
    func test_filter_quickPickup_maxDrive8_filtersCorrectly() {
        let scenario = makeScenario(foodBucket: .quick_pickup, pickupBucket: .wait_until_end, hasRewarm: true)
        let options = [
            makeFoodOption(name: "A", driveTimeMin: 8, distanceMeters: 800),
            makeFoodOption(name: "B", driveTimeMin: 5, distanceMeters: 500),
            makeFoodOption(name: "C", driveTimeMin: 12, distanceMeters: 400)
        ]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 2)
        // Sorted by driveTimeMin asc: B (5), A (8)
        XCTAssertEqual(result[0].name, "B")
        XCTAssertEqual(result[1].name, "A")
    }

    // Case 5: light_meal (max=15) — drives [nil, 10, 15, 20] → [nil, 10, 15] returned, max 3
    func test_filter_lightMeal_maxDrive15_returnsUpTo3_nilIncluded() {
        let scenario = makeScenario(foodBucket: .light_meal, pickupBucket: .wait_until_end, hasRewarm: true)
        let options = [
            makeFoodOption(name: "A", driveTimeMin: nil, distanceMeters: 1000),
            makeFoodOption(name: "B", driveTimeMin: 10, distanceMeters: 600),
            makeFoodOption(name: "C", driveTimeMin: 15, distanceMeters: 800),
            makeFoodOption(name: "D", driveTimeMin: 20, distanceMeters: 300)
        ]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        // D excluded (20 > 15). nil included. Max 3 returned.
        XCTAssertEqual(result.count, 3)
        // Sort: B(10), C(15), A(nil→9999) — nil sorts LAST
        XCTAssertEqual(result[0].name, "B")
        XCTAssertEqual(result[1].name, "C")
        XCTAssertEqual(result[2].name, "A")
    }

    // Case 6: all nil drive times → all included, sorted by distanceMeters asc
    func test_filter_allNilDrives_sortsByDistance() {
        let scenario = makeScenario(foodBucket: .quick_pickup, pickupBucket: .wait_until_end, hasRewarm: true)
        let options = [
            makeFoodOption(name: "Far",    driveTimeMin: nil, distanceMeters: 2000),
            makeFoodOption(name: "Near",   driveTimeMin: nil, distanceMeters: 400),
            makeFoodOption(name: "Middle", driveTimeMin: nil, distanceMeters: 900)
        ]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 3)
        XCTAssertEqual(result[0].name, "Near")
        XCTAssertEqual(result[1].name, "Middle")
        XCTAssertEqual(result[2].name, "Far")
    }

    // Case 7: no_next_match → [] (gapStatus guard)
    func test_filter_noNextMatch_returnsEmpty() {
        let scenario = makeScenario(gapStatus: .no_next_match, foodBucket: nil, pickupBucket: nil, hasRewarm: false)
        let options = [makeFoodOption(driveTimeMin: 3), makeFoodOption(driveTimeMin: 8)]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 0)
    }

    // Case 8: nil foodStrategy → [] (cannot determine bucket)
    func test_filter_nilFoodStrategy_returnsEmpty() {
        let scenario = makeScenario(foodBucket: nil, pickupBucket: nil, hasRewarm: false)
        let options = [makeFoodOption(driveTimeMin: 3)]
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 0)
    }

    // Case 9: returns at most 3 even if more pass the filter
    func test_filter_returnsAtMost3() {
        let scenario = makeScenario(foodBucket: .light_meal, pickupBucket: .wait_until_end, hasRewarm: true)
        let options = (1...6).map { makeFoodOption(name: "R\($0)", driveTimeMin: $0, distanceMeters: $0 * 100) }
        let result = ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: options)
        XCTAssertEqual(result.count, 3)
        // Should return the 3 closest: R1, R2, R3
        XCTAssertEqual(result[0].name, "R1")
        XCTAssertEqual(result[1].name, "R2")
        XCTAssertEqual(result[2].name, "R3")
    }

    // MARK: - §G.3 Dallas Demo Acceptance Cases (AC-POP-1, AC-POP-2, AC-POP-3)

    // AC-POP-1: Short + ok (gap=165 → light_meal)
    // Expected summary first 8 words: "Your player's match should wrap up in"
    // Expected first bullet first 6 words: "You have time for a light"
    func test_acceptance_ACPOP1_short_ok_lightMeal() {
        let summary = ScenarioDetailHelpers.summarySentence(kind: "short", status: .ok)
        XCTAssertTrue(summary.hasPrefix("Your player's match should wrap up in"))

        let scenario = makeScenario(kind: "short", foodBucket: .light_meal, pickupBucket: .wait_until_end, hasRewarm: true)
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertTrue(bullets[0].hasPrefix("You have time for a light"))
    }

    // AC-POP-2: Normal + ok (gap=120 → quick_pickup + wait_until_end)
    // Expected summary first words: "Your player's match is expected to take"
    // Expected first bullet: "Wait until the match ends before"
    func test_acceptance_ACPOP2_normal_ok_quickPickup() {
        let summary = ScenarioDetailHelpers.summarySentence(kind: "normal", status: .ok)
        XCTAssertTrue(summary.hasPrefix("Your player's match is expected to take"))

        let scenario = makeScenario(kind: "normal", foodBucket: .quick_pickup, pickupBucket: .wait_until_end, hasRewarm: true)
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertTrue(bullets[0].hasPrefix("Wait until the match ends before"))
    }

    // AC-POP-3: Long + ok (gap=60 → portable + pickup_during_match)
    // Expected summary first words: "Your player's match could run up to"
    // Expected first bullet: "Pick up portable food during the"
    func test_acceptance_ACPOP3_long_ok_portable() {
        let summary = ScenarioDetailHelpers.summarySentence(kind: "long", status: .ok)
        XCTAssertTrue(summary.hasPrefix("Your player's match could run up to"))

        let scenario = makeScenario(kind: "long", foodBucket: .portable, pickupBucket: .pickup_during_match, hasRewarm: true)
        let bullets = ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
        XCTAssertTrue(bullets[0].hasPrefix("Pick up portable food during the"))
    }

    // MARK: - SCENARIO_COOLDOWN_V1 §G.2 — 24 Matrix Cell Tests

    // Helper: build a ScenarioPlan keyed only on kind + gapStatus for cooldown tests.
    // cooldownPlan only reads scenario.scenario and scenario.gapStatus.
    private func cooldownScenario(kind: String, gapStatus: GapStatus) -> ScenarioPlan {
        makeScenario(
            kind: kind,
            gapStatus: gapStatus,
            foodBucket: gapStatus == .no_next_match ? nil : .quick_pickup,
            pickupBucket: gapStatus == .no_next_match ? nil : .wait_until_end,
            hasRewarm: gapStatus == .ok
        )
    }

    // Helper: extract the max integer in a timeWindow string (e.g. "25–30 min" → 30, "Now" → 0).
    // Used in fits-in-gap math tests to verify the last step's endpoint.
    private func parseDuration(_ timeWindow: String) -> Int {
        let numbers = timeWindow
            .components(separatedBy: CharacterSet.decimalDigits.inverted)
            .compactMap { Int($0) }
            .filter { $0 > 0 }
        return numbers.max() ?? 0
    }

    // ─── SHORT × OK ───

    func testCooldown_short_ok_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortScenario, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Hydrate now")
        XCTAssertEqual(steps[0].priority, .hydrate)
        XCTAssertFalse(steps[0].isHeatStep)
    }

    func testCooldown_short_ok_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortScenario, extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop needed — ≤ 5)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
        XCTAssertEqual(steps[0].title, "Shade and cool water first")
    }

    // ─── SHORT × TIGHT ───

    func testCooldown_short_tight_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "short", gapStatus: .tight), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Sip water now")
        XCTAssertEqual(steps[0].priority, .hydrate)
    }

    func testCooldown_short_tight_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "short", gapStatus: .tight), extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── SHORT × OVERRUN ───

    func testCooldown_short_overrun_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "short"), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 2)
        XCTAssertEqual(steps[0].title, "Sip water")
        XCTAssertEqual(steps[0].priority, .hydrate)
    }

    func testCooldown_short_overrun_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "short"), extremeHeatRisk: true)
        // 2 base + 1 heat = 3 (no drop)
        XCTAssertEqual(steps.count, 3)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── SHORT × NO_NEXT_MATCH ───

    func testCooldown_short_noNextMatch_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortNoNextMatch, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 4)
        XCTAssertEqual(steps[0].title, "Hydrate")
        XCTAssertEqual(steps[3].priority, .reset)
    }

    func testCooldown_short_noNextMatch_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortNoNextMatch, extremeHeatRisk: true)
        // 4 base + 1 heat = 5 (no drop needed — exactly 5)
        XCTAssertEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── NORMAL × OK ───

    func testCooldown_normal_ok_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasNormalScenario, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 4)
        XCTAssertEqual(steps[0].title, "Hydrate now")
        XCTAssertEqual(steps[0].priority, .hydrate)
    }

    func testCooldown_normal_ok_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasNormalScenario, extremeHeatRisk: true)
        // 4 base + 1 heat = 5 (no drop — exactly 5)
        XCTAssertEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
        XCTAssertEqual(steps[0].title, "Shade and cool water first")
    }

    // ─── NORMAL × TIGHT ───

    func testCooldown_normal_tight_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "normal", gapStatus: .tight), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Sip water now")
        XCTAssertEqual(steps[2].priority, .move)
    }

    func testCooldown_normal_tight_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "normal", gapStatus: .tight), extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── NORMAL × OVERRUN ───

    func testCooldown_normal_overrun_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "normal"), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Sip water")
        XCTAssertEqual(steps[2].title, "Alert tournament desk")
    }

    func testCooldown_normal_overrun_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "normal"), extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── NORMAL × NO_NEXT_MATCH ───

    func testCooldown_normal_noNextMatch_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "normal", gapStatus: .no_next_match), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 5)
        XCTAssertEqual(steps[0].title, "Hydrate now")
        XCTAssertEqual(steps[4].priority, .reset)
    }

    func testCooldown_normal_noNextMatch_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "normal", gapStatus: .no_next_match), extremeHeatRisk: true)
        // 5 base + 1 heat = 6 → drop .move → 5
        XCTAssertEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
        XCTAssertFalse(steps.contains(where: { $0.priority == .move && !$0.isHeatStep }))
    }

    // ─── LONG × OK (canonical 3-hour case) ───

    func testCooldown_long_ok_noHeat() {
        // OQ-CD-5: dallasLongScenario.gapStatus=.ok, gapMinutes=60 (confirmed)
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongScenario, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 5)
        XCTAssertEqual(steps[0].title, "Hydrate immediately")
        XCTAssertEqual(steps[0].priority, .hydrate)
        XCTAssertEqual(steps[4].priority, .reset)
    }

    func testCooldown_long_ok_heat() {
        // 5 base (includes .move) + 1 heat = 6 → drop .move → 5
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongScenario, extremeHeatRisk: true)
        XCTAssertEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
        XCTAssertEqual(steps[0].title, "Shade and cool water first")
        XCTAssertEqual(steps[0].priority, .cooling)
        XCTAssertFalse(steps.contains(where: { $0.priority == .move && !$0.isHeatStep }))
    }

    // ─── LONG × TIGHT ───

    func testCooldown_long_tight_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "long", gapStatus: .tight), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Hydrate immediately")
        XCTAssertEqual(steps[0].priority, .hydrate)
    }

    func testCooldown_long_tight_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: cooldownScenario(kind: "long", gapStatus: .tight), extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── LONG × OVERRUN ───

    func testCooldown_long_overrun_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "long"), extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 3)
        XCTAssertEqual(steps[0].title, "Sip water immediately")
        XCTAssertEqual(steps[2].title, "Alert the tournament desk")
    }

    func testCooldown_long_overrun_heat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "long"), extremeHeatRisk: true)
        // 3 base + 1 heat = 4 (no drop)
        XCTAssertEqual(steps.count, 4)
        XCTAssertTrue(steps[0].isHeatStep)
    }

    // ─── LONG × NO_NEXT_MATCH ───

    func testCooldown_long_noNextMatch_noHeat() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongNoNextMatch, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 5)
        XCTAssertEqual(steps[0].title, "Hydrate now")
        XCTAssertEqual(steps[4].priority, .reset)
    }

    func testCooldown_long_noNextMatch_heat() {
        // 5 base (includes .move) + 1 heat = 6 → drop .move → 5
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongNoNextMatch, extremeHeatRisk: true)
        XCTAssertLessThanOrEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
        XCTAssertFalse(steps.contains(where: { $0.priority == .move && !$0.isHeatStep }))
    }

    // MARK: - SCENARIO_COOLDOWN_V1 §G.3 — Fits-in-Gap Math Tests

    // Long + ok: gap=60, warm-up=30, available=30. Last step endpoint must be ≤ 30 min.
    func testCooldown_fitsInGap_longOk() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongScenario, extremeHeatRisk: false)
        let lastEndpoint = steps.map { parseDuration($0.timeWindow) }.max() ?? 0
        XCTAssertLessThanOrEqual(lastEndpoint, 60 - 30)  // ≤ 30 min
    }

    // Any overrun scenario: step count ≤ 3 (tight logistics budget per §C.3)
    func testCooldown_fitsInGap_overrun() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.makeOverrunScenario(kind: "long"), extremeHeatRisk: false)
        XCTAssertLessThanOrEqual(steps.count, 3)
    }

    // Short + no_next_match: 4 steps, last step is .reset (check-in)
    func testCooldown_fitsInGap_noNextMatch_short() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortNoNextMatch, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 4)
        XCTAssertEqual(steps.last?.priority, .reset)
    }

    // Long + no_next_match: 5 steps, last step is .reset (talk it through)
    func testCooldown_fitsInGap_noNextMatch_long() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongNoNextMatch, extremeHeatRisk: false)
        XCTAssertEqual(steps.count, 5)
        XCTAssertEqual(steps.last?.priority, .reset)
    }

    // MARK: - SCENARIO_COOLDOWN_V1 §G.4 — Heat Overlay Tests

    // Test 1: for any scenario, heat flag prepends exactly 1 heat step at index 0.
    func testCooldown_heatOverlay_alwaysPrepended() {
        let plan = FakeData.dallasShortScenario   // short + ok: 3 base steps
        let noHeat = ScenarioDetailHelpers.cooldownPlan(scenario: plan, extremeHeatRisk: false)
        let withHeat = ScenarioDetailHelpers.cooldownPlan(scenario: plan, extremeHeatRisk: true)

        // Exactly one heat step in the result
        XCTAssertEqual(withHeat.filter { $0.isHeatStep }.count, 1)
        // It is at index 0
        XCTAssertTrue(withHeat[0].isHeatStep)
        // short+ok base=3 → 3+1=4 (no drop)
        XCTAssertEqual(withHeat.count, noHeat.count + 1)
    }

    // Test 2: heat step detail == HardCodedStrings.heatCooldownStep (constant, not literal).
    // This test guards against verbatim drift — future copy edits propagate automatically.
    func testCooldown_heatStep_usesHardCodedString() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasShortScenario, extremeHeatRisk: true)
        XCTAssertEqual(steps[0].detail, HardCodedStrings.heatCooldownStep)
    }

    // Test 3: heat merge rule for long + no_next_match (5-step cap, .move dropped).
    func testCooldown_heatMerge_longNoNextMatch() {
        let steps = ScenarioDetailHelpers.cooldownPlan(scenario: FakeData.dallasLongNoNextMatch, extremeHeatRisk: true)
        XCTAssertLessThanOrEqual(steps.count, 5)
        XCTAssertTrue(steps[0].isHeatStep)
        // No non-heat .move steps remain after heat merge rule
        XCTAssertFalse(steps.contains(where: { $0.priority == .move && !$0.isHeatStep }))
    }
}
