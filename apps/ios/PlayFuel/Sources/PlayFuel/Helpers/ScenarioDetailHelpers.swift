import Foundation

/// Pure helper functions for ScenarioDetailSheetView.
/// No side effects. No SwiftUI imports. Directly unit-testable.
///
/// Three functions:
///   - summarySentence(kind:status:) → 12-cell lookup table (§C.2)
///   - parentActionBullets(scenario:) → 7-row lookup table (§C.3)
///   - filteredFoodOptions(scenario:all:) → bucket-policy filter + sort (§C.4)
///
/// SCENARIO_CARD_POPOUT_V1.md §F.4
/// food_options is TOP-LEVEL on Plan (OQ-POP-1): all filtering is client-side.
/// FoodOption has NO recommended_window / scenario_fit (OQ-POP-2): filter uses
/// driveTimeMin vs _BUCKET_POLICY thresholds from food.py (portable=5, quick_pickup=8, light_meal=15).
enum ScenarioDetailHelpers {

    // MARK: - §C.2 Summary Sentence

    /// Returns a deterministic one-sentence summary keyed on (scenario kind × gap status).
    /// Full 12-cell lookup — no cell is nil. See §C.2 table.
    ///
    /// - Parameters:
    ///   - kind: scenario.scenario — "short" | "normal" | "long"
    ///   - status: scenario.gapStatus
    /// - Returns: Parent-tone summary sentence. Falls back to a generic sentence for unknown inputs.
    static func summarySentence(kind: String, status: GapStatus) -> String {
        switch (kind, status) {
        // short × all statuses
        case ("short", .ok):
            return "Your player's match should wrap up in about 75 minutes, leaving solid time before the next one."
        case ("short", .tight):
            return "Your player's match should wrap up in about 75 minutes, but the window before the next match is short \u{2014} act quickly."
        case ("short", .overrun):
            return "Even with a short match, the schedule is too tight \u{2014} the next match may start before this one finishes."
        case ("short", .no_next_match):
            return "Your player's match should wrap up in about 75 minutes \u{2014} this is the last match today, so focus on recovery."
        // normal × all statuses
        case ("normal", .ok):
            return "Your player's match is expected to take about 2 hours, leaving a reasonable gap to eat and regroup."
        case ("normal", .tight):
            return "Your player's match is expected to take about 2 hours \u{2014} the gap before the next match is short, so plan your food run early."
        case ("normal", .overrun):
            return "With a 2-hour match, the schedule is very tight \u{2014} the next match may start before this one ends."
        case ("normal", .no_next_match):
            return "Your player's match is expected to take about 2 hours \u{2014} this is the last match today, so focus on recovery after."
        // long × all statuses
        case ("long", .ok):
            return "Your player's match could run up to 3 hours \u{2014} start planning food and a rest window as early as possible."
        case ("long", .tight):
            return "Your player's match could run up to 3 hours, with very little time before the next one \u{2014} have bag food ready now."
        case ("long", .overrun):
            return "A 3-hour match will almost certainly overlap the next match's start time \u{2014} alert the tournament desk and prepare bag food only."
        case ("long", .no_next_match):
            return "Your player's match could run up to 3 hours \u{2014} this is the last match today, so plan for a proper recovery meal after."
        // Defensive fallback — should not be reached with valid rules-engine output.
        default:
            return "Review your plan and have food ready for your player after this match."
        }
    }

    // MARK: - §C.3 Parent Action Bullets

    /// Returns 3\u{2013}5 imperative action bullets keyed on
    /// (food_bucket \u{00d7} pickup_bucket \u{00d7} rewarmUp present).
    ///
    /// Row 1: no_next_match (handled before the switch — recovery framing).
    /// Rows 2\u{2013}7: all valid (food_bucket, pickup_bucket, hasRewarm) combinations
    ///            from the rules engine. See \u{00a7}C.3 lookup table.
    ///
    /// - Parameter scenario: The ScenarioPlan to generate bullets for.
    /// - Returns: Array of imperative present-tense bullet strings.
    static func parentActionBullets(scenario: ScenarioPlan) -> [String] {
        // Row 1: no_next_match \u{2014} recovery framing (before the tuple switch)
        if scenario.gapStatus == .no_next_match {
            return [
                "This is your player's last match of the day.",
                "Offer food within 30 minutes of the final point \u{2014} lean protein and carbs (chicken with rice, sandwich, or a recovery shake).",
                "Keep water and an electrolyte drink on hand for the ride home.",
                "No re-warm-up needed \u{2014} focus on cooling down and stretching."
            ]
        }

        let bucket  = scenario.foodStrategy?.bucket   // FoodBucket?
        let pickup  = scenario.pickupStrategy.bucket  // PickupBucket?
        let hasRewarm = scenario.rewarmUp != nil

        // Tuple switch on (FoodBucket?, PickupBucket?, Bool).
        // Not a closed set \u{2014} default: is required (spec \u{00a7}F.4).
        // Inner per-enum values use the ? suffix to match Optional.some(case).
        switch (bucket, pickup, hasRewarm) {

        // Row 2: bag_only + bring_portable + no rewarm
        // Covers: gapStatus == .overrun AND gap \u{2208} [0, 45 min).
        case (.bag_only?, .bring_portable?, false):
            return [
                "Pack a bag with banana, pretzels, applesauce pouch, electrolyte drink, and a simple sandwich if tolerated.",
                "Keep the bag with you \u{2014} there is no time for a restaurant run.",
                "Have food ready BEFORE the match ends so your player can eat the moment they come off the court.",
                "No warm-up window available \u{2014} head to the next court as soon as possible."
            ]

        // Row 3: portable + bring_portable + no rewarm
        // Covers: gap \u{2208} [45, 60 min). max_drive = 5 min.
        case (.portable?, .bring_portable?, false):
            return [
                "Buy portable food before the match starts \u{2014} no time to wait in line later.",
                "Good grab-and-go options nearby (within 5 min drive): turkey sandwich, pre-packaged rice bowl, bento box.",
                "Have food waiting when your player comes off the court \u{2014} you have about 45\u{2013}60 minutes total.",
                "Eat immediately after the match; skip sitting down at a restaurant."
            ]

        // Row 4: portable + pickup_during_match + rewarm=true
        // Covers: gap \u{2208} [60, 90 min). max_drive = 5 min.
        case (.portable?, .pickup_during_match?, true):
            return [
                "Pick up portable food during the final portion of the match, if another trusted adult can stay courtside.",
                "Good nearby options (within 5 min drive): turkey sandwich, rice bowl, grocery grab-and-go.",
                "Eat within 20\u{2013}30 min of match end to leave time for the re-warm-up.",
                "Allow 30 min before Match 2 for your player to do a dynamic warm-up."
            ]

        // Row 5: quick_pickup + pickup_during_match + rewarm=true
        // Covers: gap \u{2208} [90, 120 min). max_drive = 8 min.
        case (.quick_pickup?, .pickup_during_match?, true):
            return [
                "Order ahead at a quick-pickup spot \u{2014} drive-through or grab-and-go, within about 8 min from the venue.",
                "Good options: fast-casual bowl (Chipotle/CAVA), turkey sandwich, rotisserie chicken from a grocery.",
                "Start the pickup run during the final set if another trusted adult is watching.",
                "Eat within 30 min of match end, then allow 30 min for your player to warm up before Match 2."
            ]

        // Row 6: quick_pickup + wait_until_end + rewarm=true
        // Covers: gap \u{2208} [120, 150 min). max_drive = 8 min.
        case (.quick_pickup?, .wait_until_end?, true):
            return [
                "Wait until the match ends before leaving for food \u{2014} you have enough time.",
                "Head to a quick-pickup spot (within ~8 min): fast-casual bowl, turkey sandwich, or grocery prepared meal.",
                "Aim to pick up food within 30 min of match end and eat on the way back.",
                "Allow 30 min before Match 2 for your player's dynamic warm-up.",
                "If you order ahead online, you can likely do this without leaving your player unattended."
            ]

        // Row 7: light_meal + wait_until_end + rewarm=true
        // Covers: gap \u{2265} 150 min. max_drive = 15 min.
        case (.light_meal?, .wait_until_end?, true):
            return [
                "You have time for a light sit-down meal \u{2014} avoid heavy, greasy, or fried foods.",
                "Good options (within ~15 min drive): grilled chicken with rice, pasta with marinara, a lean sandwich, or a grain bowl.",
                "Wait until the match ends before leaving \u{2014} you have over 2.5 hours before Match 2.",
                "Finish eating at least 90 min before the next match start.",
                "Allow 30 min before Match 2 for your player's dynamic warm-up."
            ]

        // Defensive fallback \u{2014} should not be reached with valid rules-engine output.
        // Triggered by unexpected (bucket, pickup, hasRewarm) combos.
        default:
            return [
                "Have food ready for your player after this match.",
                "Check the plan for timing details."
            ]
        }
    }

    // MARK: - §C.4 Food Filter + Rank

    /// Filter and rank food options client-side for a specific scenario.
    ///
    /// **Architecture note (OQ-POP-1):** food_options is TOP-LEVEL on Plan, not
    /// per-scenario. This function receives all plan-level options and narrows them
    /// using the scenario's food_bucket as the filter key.
    ///
    /// **Filter rule:** uses _BUCKET_POLICY max_drive_min thresholds from food.py.
    ///   portable     \u{2192} max 5 min drive
    ///   quick_pickup \u{2192} max 8 min drive
    ///   light_meal   \u{2192} max 15 min drive
    ///   bag_only     \u{2192} [] (no restaurant suggestions)
    ///
    /// **Rank:** driveTimeMin asc (nil last as 9999), then distanceMeters asc (nil last as 9,999,999).
    ///
    /// **Returns:** first min(3, count) results.
    ///
    /// - Parameters:
    ///   - scenario: The specific ScenarioPlan to filter for.
    ///   - all: All plan-level food options (Plan.foodOptions).
    /// - Returns: Up to 3 filtered, sorted FoodOption instances.
    static func filteredFoodOptions(scenario: ScenarioPlan, all: [FoodOption]) -> [FoodOption] {
        // Guard: overrun or bag_only \u{2192} no restaurant suggestions
        guard
            scenario.gapStatus != .overrun,
            let bucket = scenario.foodStrategy?.bucket,
            bucket != .bag_only
        else {
            return []
        }

        // _BUCKET_POLICY max_drive_min from food.py (§C.4).
        // All FoodBucket cases enumerated explicitly \u{2014} no default: (per spec hard constraint).
        let maxDrive: Int
        switch bucket {
        case .portable:     maxDrive = 5
        case .quick_pickup: maxDrive = 8
        case .light_meal:   maxDrive = 15
        case .bag_only:     return []   // guard above handles this; belt-and-suspenders exhaustiveness
        }

        // Filter: include when driveTimeMin is nil (unknown) or within policy threshold.
        let filtered = all.filter { option in
            guard let drive = option.driveTimeMin else { return true }  // nil \u{2192} include
            return drive <= maxDrive
        }

        // Sort: driveTimeMin asc (nil \u{2192} 9999), then distanceMeters asc (nil \u{2192} 9,999,999).
        // Mirrors assemble_food_options() sort key from food.py.
        let sorted = filtered.sorted { a, b in
            let aDrive = a.driveTimeMin  ?? 9_999
            let bDrive = b.driveTimeMin  ?? 9_999
            if aDrive != bDrive { return aDrive < bDrive }
            let aDist  = a.distanceMeters ?? 9_999_999
            let bDist  = b.distanceMeters ?? 9_999_999
            return aDist < bDist
        }

        return Array(sorted.prefix(3))
    }

    // MARK: - SCENARIO_COOLDOWN_V1 §C–1 Cool-down Step Model

    /// A single step in a post-match cool-down or recovery plan.
    /// Pure value type — no SwiftUI. Lives here for unit-testability.
    struct CooldownStep: Equatable {
        let timeWindow: String   // e.g. "0–5 min", "5–15 min", "Now", "First"
        let title: String        // bold, 2–5 words
        let detail: String       // 1 sentence, parent-tone
        let priority: Priority   // determines leading SF Symbol in the UI
        let isHeatStep: Bool     // true only for the prepended heat-overlay step
    }

    // MARK: - §C.2 Priority Enum

    /// Priority of a cool-down step. Maps to a leading SF Symbol in ScenarioDetailSheetView.
    /// Closed enum — no default: in any switch over this type.
    enum Priority: Equatable {
        case cooling   // thermometer.snowflake  (iOS 16+, safe on iOS 17 target)
        case hydrate   // drop.fill
        case refuel    // fork.knife
        case move      // figure.walk
        case reset     // brain.head.profile    (iOS 16+, safe on iOS 17 target)
    }

    // MARK: - §F.2 cooldownPlan — public entry point

    /// Returns a deterministic cool-down plan for a given scenario × gap_status × heat.
    ///
    /// Inputs:
    ///   - scenario.scenario: "short" | "normal" | "long" (String — OQ-CD-3: default: required)
    ///   - scenario.gapStatus: GapStatus (closed enum — exhaustive in baseCooldownSteps)
    ///   - extremeHeatRisk: Bool — caller passes plan.weather.extremeHeatRisk
    ///     (WeatherSnapshot.extremeHeatRisk is a computed var, not on ScenarioPlan)
    ///
    /// SCENARIO_COOLDOWN_V1.md §D content matrix — 24 cells (3 × 4 × 2).
    /// No SwiftUI. No side effects. Directly unit-testable.
    ///
    /// Heat merge rule: when heat step would push count > 5, drop all non-heat .move
    /// steps. .move is the lowest recovery-critical priority in heat (body should rest,
    /// not walk, in extreme heat). 5-step cap keeps the sheet scannable at .medium detent.
    static func cooldownPlan(scenario: ScenarioPlan, extremeHeatRisk: Bool) -> [CooldownStep] {
        let base = baseCooldownSteps(scenario: scenario)
        guard extremeHeatRisk else { return base }

        let heatStep = CooldownStep(
            timeWindow: "First",
            title: "Shade and cool water first",
            detail: HardCodedStrings.heatCooldownStep,   // OQ-CD-1 resolved
            priority: .cooling,
            isHeatStep: true
        )

        var result = [heatStep] + base
        if result.count > 5 {
            // Drop non-heat .move steps first (lowest recovery-critical priority in heat)
            result.removeAll { $0.priority == .move && !$0.isHeatStep }
            // Safety truncation: if still > 5 after move removal, trim from the end
            while result.count > 5 {
                result.removeLast()
            }
        }
        return result
    }

    // MARK: - §F.2 baseCooldownSteps — private inner helper

    /// Returns the non-heat base steps for (scenario.scenario × scenario.gapStatus).
    /// Full 12-cell matrix from SCENARIO_COOLDOWN_V1.md §D.
    ///
    /// Switch on (String, GapStatus): the String side requires default: because
    /// scenario.scenario is not a Swift enum (OQ-CD-3 / SEC-POP-2 carry-over).
    /// The GapStatus side is a closed enum — all 4 cases are covered per (kind, status) pair.
    private static func baseCooldownSteps(scenario: ScenarioPlan) -> [CooldownStep] {
        switch (scenario.scenario, scenario.gapStatus) {

        // ──────────── SHORT (75 min) ────────────

        case ("short", .ok):
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate now",
                             detail: "Water and electrolyte drink right off the court.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–10 min",  title: "Quick snack",
                             detail: "Grab a banana, bar, or applesauce pouch while you walk.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "10–15 min", title: "Loose movement",
                             detail: "Easy walk to settle muscles — no hard effort.",
                             priority: .move, isHeatStep: false),
            ]

        case ("short", .tight):
            return [
                CooldownStep(timeWindow: "0–2 min",  title: "Sip water now",
                             detail: "Quick water or electrolyte sip right off the court.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "2–4 min",  title: "Bag snack on the go",
                             detail: "Hand them a banana or bar as you walk to the next court.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "4–5 min",  title: "Head over now",
                             detail: "No time for a rest break — walk directly to the next court.",
                             priority: .move, isHeatStep: false),
            ]

        case ("short", .overrun):
            return [
                CooldownStep(timeWindow: "Now",       title: "Sip water",
                             detail: "Quick water sip — even 30 seconds matters.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "On the way", title: "Eat from your bag as you walk",
                             detail: "Banana or applesauce pouch during the walk to the next court.",
                             priority: .refuel, isHeatStep: false),
            ]

        case ("short", .no_next_match):
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate",
                             detail: "Water and electrolyte drink.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–10 min",  title: "Light snack",
                             detail: "Banana, bar, or recovery snack within 30 min of the final point.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "10–20 min", title: "Loose movement",
                             detail: "Gentle walk or light movement to let muscles settle.",
                             priority: .move, isHeatStep: false),
                CooldownStep(timeWindow: "20–30 min", title: "Check in",
                             detail: "Ask how they feel and what went well today.",
                             priority: .reset, isHeatStep: false),
            ]

        // ──────────── NORMAL (120 min) ────────────

        case ("normal", .ok):
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate now",
                             detail: "Water and electrolyte drink right off the court.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–15 min",  title: "Change and cool down",
                             detail: "Change clothes if possible and find shade or A/C.",
                             priority: .cooling, isHeatStep: false),
                CooldownStep(timeWindow: "15–25 min", title: "Recovery snack",
                             detail: "Carb and protein within 20 min — chicken rice bowl, turkey sandwich, or a substantial bar.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "25–30 min", title: "Rest and reset",
                             detail: "Quiet sit or light walk — ask how they feel.",
                             priority: .reset, isHeatStep: false),
            ]

        case ("normal", .tight):
            return [
                CooldownStep(timeWindow: "0–3 min",  title: "Sip water now",
                             detail: "Water or electrolyte right off the court — don't skip this.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "3–5 min",  title: "Bag snack on the go",
                             detail: "Hand them a banana or bar while you walk.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "5–8 min",  title: "Move to next court",
                             detail: "Head over now — no time to sit down.",
                             priority: .move, isHeatStep: false),
            ]

        case ("normal", .overrun):
            return [
                CooldownStep(timeWindow: "Now",       title: "Sip water",
                             detail: "Water sip immediately — even a minute off the court helps.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "On the way", title: "Grab bag snack",
                             detail: "Banana or applesauce pouch as you walk to the next court.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "On the way", title: "Alert tournament desk",
                             detail: "Notify the desk of the schedule conflict as you move.",
                             priority: .move, isHeatStep: false),
            ]

        case ("normal", .no_next_match):
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate now",
                             detail: "Water and electrolyte drink.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–15 min",  title: "Change into dry clothes",
                             detail: "Fresh kit for the ride home — helps the body settle.",
                             priority: .cooling, isHeatStep: false),
                CooldownStep(timeWindow: "15–30 min", title: "Recovery meal",
                             detail: "Lean protein and carbs within 30 min — chicken with rice, sandwich, or recovery shake.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "30–40 min", title: "Loose walk or rest",
                             detail: "Light movement or quiet sit — whatever they prefer.",
                             priority: .move, isHeatStep: false),
                CooldownStep(timeWindow: "40–45 min", title: "Debrief",
                             detail: "Ask what went well today. What was tough? No performance pressure — just listening.",
                             priority: .reset, isHeatStep: false),
            ]

        // ──────────── LONG (180 min) — the canonical 3-hour case ────────────

        case ("long", .ok):
            // Dallas demo: gap=60 − 30 warm-up = 30 min available. 5 steps, total span 30 min.
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate immediately",
                             detail: "Water and electrolyte drink the moment they step off the court — after 3 hours this is the first priority.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–10 min",  title: "Change into dry clothes",
                             detail: "A fresh, dry kit helps the body reset after a long match — don't skip this step.",
                             priority: .cooling, isHeatStep: false),
                CooldownStep(timeWindow: "10–20 min", title: "Recovery snack now",
                             detail: "Within 20 min: banana, bar, or carb and protein snack. The body needs fuel quickly after a 3-hour effort.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "20–25 min", title: "Easy walk",
                             detail: "Gentle stroll — no hard movement, no sprints. Let the legs recover.",
                             priority: .move, isHeatStep: false),
                CooldownStep(timeWindow: "25–30 min", title: "Mental reset",
                             detail: "Quiet moment. Ask how they felt out there today.",
                             priority: .reset, isHeatStep: false),
            ]

        case ("long", .tight):
            return [
                CooldownStep(timeWindow: "0–3 min",  title: "Hydrate immediately",
                             detail: "Water and electrolyte — don't skip this even with no time. After 3 hours, the body needs it.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "3–7 min",  title: "Grab bag snack now",
                             detail: "Eat as you walk — banana, bar, or applesauce pouch.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "7–10 min", title: "Move to next court",
                             detail: "Head over now. No time for a sit-down. Keep the pace easy on the walk.",
                             priority: .move, isHeatStep: false),
            ]

        case ("long", .overrun):
            return [
                CooldownStep(timeWindow: "Now",       title: "Sip water immediately",
                             detail: "Even 1 minute of hydration matters after a 3-hour match.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "On the way", title: "Bag snack as you walk",
                             detail: "Banana or bar now — there is no stop.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "On the way", title: "Alert the tournament desk",
                             detail: "Notify the desk of the overrun as you head to the next court.",
                             priority: .move, isHeatStep: false),
            ]

        case ("long", .no_next_match):
            // Full recovery: last match of the day. Section header in sheet: "Recovery".
            return [
                CooldownStep(timeWindow: "0–5 min",   title: "Hydrate now",
                             detail: "Water and electrolyte drink right off the court — after 3 hours, this is urgent.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–15 min",  title: "Change into dry clothes",
                             detail: "Fresh, dry clothes for the drive home — helps the body settle after a long effort.",
                             priority: .cooling, isHeatStep: false),
                CooldownStep(timeWindow: "15–30 min", title: "Recovery meal when ready",
                             detail: "Lean protein and carbs within 30 min — chicken with rice, a turkey sandwich, or a recovery shake. No rush to a restaurant; bag food works.",
                             priority: .refuel, isHeatStep: false),
                CooldownStep(timeWindow: "30–45 min", title: "Easy movement or rest",
                             detail: "Gentle walk or a quiet sit — whatever they prefer. Let their body choose.",
                             priority: .move, isHeatStep: false),
                CooldownStep(timeWindow: "45–60 min", title: "Talk it through",
                             detail: "Ask how they felt on court. What went well? What was tough? Listen without pushing. Three hours is a lot.",
                             priority: .reset, isHeatStep: false),
            ]

        // Defensive fallback — required because scenario.scenario is a String, not a Swift enum.
        // Triggered by any server-side scenario kind not in {"short", "normal", "long"}.
        // See OQ-CD-3 / SEC-POP-2: model ScenarioPlan.scenario as ScenarioKind enum pre-TestFlight.
        default:
            return [
                CooldownStep(timeWindow: "0–5 min", title: "Hydrate",
                             detail: "Water and electrolyte drink after the match.",
                             priority: .hydrate, isHeatStep: false),
                CooldownStep(timeWindow: "5–10 min", title: "Rest",
                             detail: "Take a moment before moving on.",
                             priority: .reset, isHeatStep: false),
            ]
        }
    }
}
