import SwiftUI

/// Tappable scenario card detail sheet.
///
/// Opened by tapping any of the 3 match scenario cards (Short / Normal / Long)
/// in `ScenarioCardView`. Renders 5 content blocks per SCENARIO_CARD_POPOUT_V1.md §C:
///   §C.1 Header (scenario label, gap minutes, gap-status pill)
///   §C.2 One-sentence summary (12-cell lookup, deterministic)
///   §C.3 Parent-action checklist (7-row lookup, imperative bullets)
///   §C.4 Food suggestions (filtered from plan-level foodOptions) or bag-only panel
///   §C.5 Footer disclaimer (HardCodedStrings.userDisclaimer verbatim)
///
/// Degraded states (§D):
///   no_next_match → food block hidden, recovery bullets (Row 1)
///   overrun       → amber strip + forced bag-only panel
///   empty options → bag-only fallback panel with sub-label
///
/// Architecture note (OQ-POP-1): food_options is TOP-LEVEL on Plan, not per-scenario.
/// This view receives both the scenario and the plan-level food list. Filtering is
/// done client-side via ScenarioDetailHelpers.filteredFoodOptions(scenario:all:).
///
/// SCENARIO_CARD_POPOUT_V1.md §F.2
struct ScenarioDetailSheetView: View {

    let scenario: ScenarioPlan
    let foodOptions: [FoodOption]
    /// Passed from caller as plan.weather.extremeHeatRisk (WeatherSnapshot computed var).
    /// Used by cooldownPlan block to prepend the heat overlay step when true.
    let extremeHeatRisk: Bool

    // MARK: - Computed State

    private var filteredOptions: [FoodOption] {
        ScenarioDetailHelpers.filteredFoodOptions(scenario: scenario, all: foodOptions)
    }

    private var bullets: [String] {
        ScenarioDetailHelpers.parentActionBullets(scenario: scenario)
    }

    private var summary: String {
        ScenarioDetailHelpers.summarySentence(kind: scenario.scenario,
                                              status: scenario.gapStatus)
    }

    /// Show the restaurant suggestion block.
    private var showFoodBlock: Bool {
        scenario.gapStatus != .no_next_match &&
        scenario.foodStrategy?.bucket != .bag_only &&
        !filteredOptions.isEmpty
    }

    /// Ordered cool-down steps for this scenario (SCENARIO_COOLDOWN_V1 §F.2).
    private var cooldownSteps: [ScenarioDetailHelpers.CooldownStep] {
        ScenarioDetailHelpers.cooldownPlan(scenario: scenario, extremeHeatRisk: extremeHeatRisk)
    }

    private var showBagOnlyPanel: Bool {
        scenario.foodStrategy?.bucket == .bag_only ||
        scenario.gapStatus == .overrun ||
        (scenario.gapStatus != .no_next_match &&
         filteredOptions.isEmpty &&
         scenario.foodStrategy != nil)
    }

    /// True when the bag panel shows because no restaurant options passed the filter
    /// (vs. bag_only or overrun). Used to show the "No nearby restaurants found" sub-label.
    private var bagFoodNoOptionsFound: Bool {
        scenario.foodStrategy?.bucket != .bag_only &&
        scenario.gapStatus != .overrun &&
        filteredOptions.isEmpty &&
        scenario.foodStrategy != nil
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // §D overrun amber strip (immovable, above header)
                    if scenario.gapStatus == .overrun {
                        overrunStrip
                    }

                    // §C.1 Header
                    headerBlock

                    Divider()

                    // §C.2 One-sentence summary
                    summaryBlock

                    // §C.3 Parent-action checklist
                    actionChecklistBlock

                    // SCENARIO_COOLDOWN_V1 §E.1 — Cool-down plan block (between checklist and food)
                    cooldownPlanBlock

                    // §C.4 Food block (restaurant cards OR bag-only panel)
                    if showFoodBlock {
                        foodSuggestionsBlock
                    } else if showBagOnlyPanel {
                        bagOnlyPanel
                    }
                    // no_next_match → neither block rendered

                    // §C.5 Footer disclaimer
                    footerDisclaimerBlock
                }
                .padding(16)
            }
            .navigationTitle("\(scenario.scenarioLabel) match")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    // MARK: - §D Overrun Strip

    private var overrunStrip: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text("Tight turnaround \u{2014} packed food only")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.orange)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - §C.1 Header

    private var headerBlock: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Scenario title
            Text("\(scenario.scenarioLabel) match")
                .font(.title2.weight(.bold))

            // Duration + gap line
            Text(durationGapLine)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            // Gap-status pill
            Text(gapPillText)
                .font(.caption.weight(.bold))
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(gapPillColor.opacity(0.15))
                .foregroundStyle(gapPillColor)
                .clipShape(Capsule())
        }
    }

    private var durationGapLine: String {
        let matchDuration = DurationFormatting.friendly(minutes: scenario.durationMin)
        let gapDisplay: String
        if scenario.gapStatus == .no_next_match {
            gapDisplay = "last match today"
        } else if let gap = scenario.gapMinutes {
            gapDisplay = "\(DurationFormatting.friendly(minutes: abs(gap))) gap"
        } else {
            gapDisplay = "gap unknown"
        }
        return "\(matchDuration) match \u{00b7} \(gapDisplay)"
    }

    private var gapPillText: String {
        switch scenario.gapStatus {
        case .ok:           return "On track"
        case .tight:        return "Tight"
        case .overrun:      return "\u{26a0} Overrun"
        case .no_next_match: return "Last match"
        }
    }

    /// Mirrors gapPillColor from ScenarioCardView for visual consistency (§H decisions table).
    private var gapPillColor: Color {
        switch scenario.gapStatus {
        case .ok:           return .green
        case .tight:        return .yellow
        case .overrun:      return .orange
        case .no_next_match: return .secondary
        }
    }

    // MARK: - §C.2 Summary

    private var summaryBlock: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(summary)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - §C.3 Checklist

    private var actionChecklistBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("What You Can Do", systemImage: "checklist")
                .font(.headline)

            VStack(alignment: .leading, spacing: 8) {
                ForEach(bullets, id: \.self) { bullet in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\u{2022}")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Text(bullet)
                            .font(.subheadline)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("What you can do: \(bullets.joined(separator: ". "))")
        }
    }

    // MARK: - §C.4 Food Suggestions

    private var foodSuggestionsBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Food Suggestions", systemImage: "fork.knife.circle")
                .font(.headline)

            VStack(spacing: 10) {
                ForEach(filteredOptions) { option in
                    foodSuggestionCard(option: option)
                }
            }
        }
    }

    private func foodSuggestionCard(option: FoodOption) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            // Restaurant name
            HStack {
                Text(option.name)
                    .font(.headline)
                Spacer()
                // Drive time
                HStack(spacing: 3) {
                    Image(systemName: "car")
                        .font(.caption)
                    Text(driveTimeText(option.driveTimeMin))
                        .font(.caption)
                }
                .foregroundStyle(.secondary)
            }

            // Category label
            Text(categoryLabel(for: option.category))
                .font(.subheadline)
                .foregroundStyle(.secondary)

            // DRAFT badge
            if option.isDraft {
                Text("(DRAFT \u{2014} confirm with your athlete)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Divider()

            // Top 1–2 order lines from suggestions.mainOptions; fallback to recommendedOrder
            let orderLines = orderLines(for: option)
            VStack(alignment: .leading, spacing: 3) {
                ForEach(orderLines, id: \.self) { line in
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(option.name), \(categoryLabel(for: option.category)), \(option.driveTimeMin.map { "\($0) minutes away" } ?? "distance unknown")")
    }

    // MARK: - §C.4 Bag-Only Panel

    private var bagOnlyPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "bag.fill")
                    .foregroundStyle(.secondary)
                Text("Eat from your bag")
                    .font(.headline)
            }

            // Sub-label: contextual based on why we're showing bag-only
            if bagFoodNoOptionsFound {
                Text("No nearby restaurants found \u{2014} see bag food items below.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("No restaurant stop \u{2014} use what you've packed.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Bag food item list (RULES_CONSTANTS_V1 §H.3)
            VStack(alignment: .leading, spacing: 4) {
                ForEach(bagFoodItems, id: \.self) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\u{2022}").foregroundStyle(.secondary)
                        Text(item).font(.subheadline)
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .accessibilityLabel("Eat from your bag: \(bagFoodItems.joined(separator: ", "))")
    }

    // MARK: - SCENARIO_COOLDOWN_V1 Cool-down Plan Block

    /// Section header: "Recovery" for no_next_match (last-match framing), "Cool-down" otherwise.
    /// §E.2: no colon after the title.
    private var cooldownPlanBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            let sectionTitle = scenario.gapStatus == .no_next_match ? "Recovery" : "Cool-down"
            Label(sectionTitle, systemImage: "clock.arrow.circlepath")
                .font(.headline)

            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(cooldownSteps.enumerated()), id: \.offset) { _, step in
                    cooldownStepRow(step)
                }
            }
        }
    }

    /// §E.3 single step row: priority icon + time-window pill + bold title + detail line.
    /// Heat step: orange icon tint + orange pill background. Reuses existing .orange palette.
    private func cooldownStepRow(_ step: ScenarioDetailHelpers.CooldownStep) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: prioritySymbol(step.priority))
                .font(.subheadline)
                .foregroundStyle(step.isHeatStep ? Color.orange : Color.secondary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(step.timeWindow)
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2)
                        .background(step.isHeatStep
                            ? Color.orange.opacity(0.15)
                            : Color(.systemGray5))
                        .clipShape(Capsule())
                    Text(step.title)
                        .font(.subheadline.weight(.semibold))
                }
                Text(step.detail)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            step.isHeatStep
                ? "Heat alert, \(step.timeWindow): \(step.title). \(step.detail)"
                : "\(step.timeWindow): \(step.title). \(step.detail)"
        )
    }

    /// §E.4 Priority → SF Symbol mapping.
    /// Closed enum — no default: (compiler enforces exhaustiveness).
    /// All symbols are iOS 16+ (safe on iOS 17 deployment target per OQ-CD-2 resolution).
    private func prioritySymbol(_ priority: ScenarioDetailHelpers.Priority) -> String {
        switch priority {
        case .cooling: return "thermometer.snowflake"   // iOS 16+
        case .hydrate: return "drop.fill"
        case .refuel:  return "fork.knife"
        case .move:    return "figure.walk"
        case .reset:   return "brain.head.profile"      // iOS 16+
        }
    }

    // MARK: - §C.5 Footer Disclaimer

    private var footerDisclaimerBlock: some View {
        // Verbatim HardCodedStrings.userDisclaimer per SAFETY_DISCLAIMERS.md §A.
        // DO NOT re-type this text. Always access via HardCodedStrings.
        Text(HardCodedStrings.userDisclaimer)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 12)
    }

    // MARK: - Private Helpers

    /// Category label matching FoodCardView and FoodOptionDetailSheet conventions.
    private func categoryLabel(for category: String) -> String {
        switch category {
        case "fast_casual_bowl":  return "Fast casual bowl"
        case "sandwich_shop":     return "Sandwich shop"
        case "grocery_prepared":  return "Grocery prepared"
        case "breakfast_cafe":    return "Breakfast caf\u{00e9}"
        default:                  return category.replacingOccurrences(of: "_", with: " ")
        }
    }

    private func driveTimeText(_ driveTimeMin: Int?) -> String {
        guard let dt = driveTimeMin else { return "Distance unknown" }
        return "\(dt) min"
    }

    /// Returns top 1–2 order lines from suggestions.mainOptions (if present and non-empty),
    /// falling back to recommendedOrder as a single line.
    private func orderLines(for option: FoodOption) -> [String] {
        if let main = option.suggestions?.mainOptions, !main.isEmpty {
            return Array(main.prefix(2))
        }
        return [option.recommendedOrder]
    }

    /// Canonical bag food items from RULES_CONSTANTS_V1 §H.3.
    private let bagFoodItems: [String] = [
        "Banana",
        "Pretzels",
        "Applesauce pouch",
        "Electrolyte drink",
        "Simple sandwich if tolerated"
    ]
}

// MARK: - Previews (§G.2 — 3 required states)

/// Preview 1: Short + ok + light_meal (full content — food suggestions shown)
/// Verifies: §C.1 green pill, §C.2 short/ok summary, §C.3 Row 7 bullets, §C.4 food cards.
#Preview("Short \u{00b7} ok \u{00b7} light_meal") {
    // Dallas 88°F + 72% humidity → extremeHeatRisk=true; shows heat-adjusted cool-down.
    ScenarioDetailSheetView(
        scenario: FakeData.dallasShortScenario,
        foodOptions: FakeData.dallasFoodOptions,
        extremeHeatRisk: true
    )
}

/// Preview 2: Normal + overrun (degraded — amber strip + bag-only panel, no heat)
/// Verifies: §D overrun strip, §C.3 Row 2 bullets, §C.4 bag-only panel.
#Preview("Normal \u{00b7} overrun") {
    ScenarioDetailSheetView(
        scenario: FakeData.makeOverrunScenario(kind: "normal"),
        foodOptions: FakeData.dallasFoodOptions,
        extremeHeatRisk: false
    )
}

/// Preview 3: Long + no_next_match (recovery framing — no food block, no heat)
/// Verifies: §D no_next_match (food block hidden), section header "Recovery", gray pill.
#Preview("Long \u{00b7} no_next_match") {
    ScenarioDetailSheetView(
        scenario: FakeData.dallasLongNoNextMatch,
        foodOptions: FakeData.dallasFoodOptions,
        extremeHeatRisk: false
    )
}

/// Preview 4 (NEW — SCENARIO_COOLDOWN_V1 §G.3): Long + ok + heat — canonical 3-hour Dallas case.
/// Verifies: 5-step heat-adjusted plan (move dropped), orange heat step at top.
/// FakeData.dallasLongScenario: gap=60, gapStatus=.ok (OQ-CD-5 confirmed).
#Preview("Long \u{00b7} ok \u{00b7} heat") {
    ScenarioDetailSheetView(
        scenario: FakeData.dallasLongScenario,
        foodOptions: FakeData.dallasFoodOptions,
        extremeHeatRisk: true
    )
}

#Preview("Dark") {
    ScenarioDetailSheetView(
        scenario: FakeData.dallasShortScenario,
        foodOptions: FakeData.dallasFoodOptions,
        extremeHeatRisk: true
    )
    .preferredColorScheme(.dark)
}
