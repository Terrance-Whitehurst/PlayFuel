import SwiftUI

/// Phase 6 / Task #9 — Plan Summary Card.
///
/// Renders the LLM- or TemplateProvider-generated parent-friendly plan summary
/// at the top of the TournamentDashboardView (below EmergencyBanner, above WeatherCard).
///
/// Safety: safetyNote always contains the §A disclaimer verbatim, prepended with
/// the §B emergency text verbatim when extreme_heat_risk was true at generation time.
/// No field in this card invents restaurants, weather facts, or schedule logic —
/// all content originates from the structured PlanExplanationInput (SAFETY_DISCLAIMERS §E).
struct PlanSummaryCard: View {

    let explanation: PlanExplanation

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {

            // Header row: label + provider badge
            HStack {
                Label("Plan Summary", systemImage: "sparkles")
                    .font(.headline)
                Spacer()
                Text(providerBadge)
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.15))
                    .clipShape(Capsule())
            }

            // Main 2–4 sentence parent-friendly intro
            Text(explanation.summary)
                .font(.body)

            // Weather note (nil when no weather data or provider error)
            if let weatherNote = explanation.weatherNote {
                Text(weatherNote)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // Food note (nil when bag_fallback_only)
            if let foodNote = explanation.foodNote {
                Text(foodNote)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            Divider()

            // Safety note — always present; §A verbatim; §B prepended when extreme_heat_risk.
            Text(explanation.safetyNote)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        #if os(iOS)
        .background(Color(.systemBackground))
        #else
        .background(Color.white)
        #endif
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal, 16)
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
    ScrollView {
        PlanSummaryCard(explanation: FakeData.dallasPlan.llmSummary!)
            .padding(.vertical)
    }
}

#Preview("Dark") {
    ScrollView {
        PlanSummaryCard(explanation: FakeData.dallasPlan.llmSummary!)
            .padding(.vertical)
    }
    .preferredColorScheme(.dark)
}
