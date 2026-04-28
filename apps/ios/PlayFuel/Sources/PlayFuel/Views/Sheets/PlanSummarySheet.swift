import SwiftUI

/// Sheet presenting the full LLM/template plan summary.
/// Opened by tapping the "Today's Plan" bubble in `HeaderBubbleRow`.
///
/// Renders only fields that exist on `PlanExplanation`:
///   `summary`, `weatherNote?`, `foodNote?`, `safetyNote`, `provider` (DEBUG only).
///
/// `scenarioExplanations` is intentionally NOT rendered here —
/// `ScenarioCardView` is the correct surface for per-scenario breakdowns.
///
/// Safety: `safetyNote` always contains the §A disclaimer verbatim (and §B
/// emergency text when extreme_heat_risk was true at generation time).
/// This content originates from the backend and is never modified by this view.
///
/// HEADER_BUBBLES_V1.md §B (Plan Summary Sheet) + §F.3
/// ⚠️ OQ-11: Pending attorney review — do not treat as legally cleared.
struct PlanSummarySheet: View {

    let explanation: PlanExplanation

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // MARK: Summary — 2–4 sentence coach voice intro
                    Text(explanation.summary)
                        .font(.body)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    // MARK: Weather Note (nil when no weather data available)
                    if let weatherNote = explanation.weatherNote {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Conditions")
                                .font(.subheadline.weight(.semibold))
                            Text(weatherNote)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }

                    // MARK: Food Note (nil when bag_fallback_only)
                    if let foodNote = explanation.foodNote {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Food")
                                .font(.subheadline.weight(.semibold))
                            Text(foodNote)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }

                    Divider()

                    // MARK: Safety Note — always present
                    // §A disclaimer verbatim; §B prepended when extreme_heat_risk.
                    // Content is server-generated from hard_coded_strings; never re-typed here.
                    Text(explanation.safetyNote)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    // MARK: Provider badge — DEBUG only
                    #if DEBUG
                    Text("via: \(providerBadge)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    #endif
                }
                .padding(20)
            }
            .navigationTitle("Today's Plan")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Helpers

    private var providerBadge: String {
        switch explanation.provider {
        case "anthropic": return "Claude"
        case "openai":    return "GPT"
        default:          return "Template"
        }
    }
}

#Preview {
    PlanSummarySheet(explanation: FakeData.dallasPlan.llmSummary!)
}

#Preview("Dark") {
    PlanSummarySheet(explanation: FakeData.dallasPlan.llmSummary!)
        .preferredColorScheme(.dark)
}
