import SwiftUI

/// US-06 — A single match-duration scenario card.
///
/// Renders one ScenarioPlan (short / normal / long).
/// Shows: scenario label, duration, estimated end, gap pill (color by status),
/// food strategy, pickup strategy, re-warm-up time, and inline amber overrun band.
/// Phase 3: fed from Plan.scenarioPlans decoded from API.
struct ScenarioCardView: View {

    let plan: ScenarioPlan

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {

            // Header bar — scenario + duration
            headerBar

            VStack(alignment: .leading, spacing: 14) {

                // Overrun warning band (amber) — renders if overrunWarning != nil
                if let warning = plan.overrunWarning {
                    overrunBand(warning: warning)
                }

                // Gap pill row
                gapRow

                // Food strategy
                if let food = plan.foodStrategy {
                    strategyRow(
                        icon: "fork.knife",
                        label: "Food Strategy",
                        text: food.text,
                        color: .green
                    )
                }

                // Parent pickup strategy
                strategyRow(
                    icon: "car.fill",
                    label: "Parent Pickup",
                    text: plan.pickupStrategy.text,
                    color: .blue
                )

                // Re-warm-up
                if let rewarm = plan.rewarmUp {
                    strategyRow(
                        icon: "figure.walk",
                        label: "Re-Warm-Up",
                        text: rewarmText(rewarm),
                        color: .orange
                    )
                } else if plan.gapStatus == .overrun {
                    strategyRow(
                        icon: "figure.walk",
                        label: "Re-Warm-Up",
                        text: "Not available — match overrun leaves no warm-up window.",
                        color: .secondary
                    )
                }
            }
            .padding(16)
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        // Ensure min width for horizontal scroll
        .frame(width: 300)
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(plan.scenarioLabel)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                Text("\(DurationFormatting.friendly(minutes: plan.durationMin)) match")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.85))
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("Est. End")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.75))
                Text(plan.estimatedEnd)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(headerColor)
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 16, topTrailingRadius: 16))
    }

    private var headerColor: Color {
        switch plan.scenario {
        case "short":  return .green
        case "normal": return .blue
        case "long":   return .purple
        default:       return .gray
        }
    }

    // MARK: - Gap Row

    private var gapRow: some View {
        HStack(spacing: 10) {
            Label {
                Text("Gap to Next Match")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            } icon: {
                Image(systemName: "arrow.left.and.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            gapPill
        }
    }

    private var gapPill: some View {
        Group {
            if let gap = plan.gapMinutes {
                Text(gapLabel(gap))
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(gapPillColor.opacity(0.15))
                    .foregroundStyle(gapPillColor)
                    .clipShape(Capsule())
            } else {
                Text("No next match")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func gapLabel(_ gap: Int) -> String {
        switch plan.gapStatus {
        case .overrun:        return "⚠ \(DurationFormatting.friendly(minutes: abs(gap))) overrun"
        case .tight:          return "⚡ \(DurationFormatting.friendly(minutes: gap)) tight"
        case .ok:             return "✓ \(DurationFormatting.friendly(minutes: gap))"
        case .no_next_match:  return "No next match"
        }
    }

    private var gapPillColor: Color {
        switch plan.gapStatus {
        case .ok:            return .green
        case .tight:         return .yellow
        case .overrun:       return .orange
        case .no_next_match: return .gray
        }
    }

    // MARK: - Overrun Band

    private func overrunBand(warning: OverrunWarning) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            // Use HardCodedStrings.overrunMessage for the canonical text;
            // also show warning.message from the plan (same content, from server).
            Text(warning.message)
                .font(.caption.weight(.medium))
                .foregroundStyle(.orange)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Strategy Row

    private func strategyRow(icon: String, label: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(label, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(color)
            Text(text)
                .font(.caption)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Helpers

    private func rewarmText(_ rewarm: RewarmUp) -> String {
        let absOffset = abs(rewarm.startOffsetMin)
        return "Start \(DurationFormatting.friendly(minutes: absOffset)) before Match 2, \(DurationFormatting.friendly(minutes: rewarm.durationMin)) dynamic warm-up."
    }
}

#Preview {
    ScrollView(.horizontal) {
        HStack(spacing: 16) {
            ScenarioCardView(plan: FakeData.dallasShortScenario)
            ScenarioCardView(plan: FakeData.dallasNormalScenario)
            ScenarioCardView(plan: FakeData.dallasLongScenario)
        }
        .padding()
    }
}

#Preview("Dark") {
    ScrollView(.horizontal) {
        HStack(spacing: 16) {
            ScenarioCardView(plan: FakeData.dallasShortScenario)
            ScenarioCardView(plan: FakeData.dallasNormalScenario)
            ScenarioCardView(plan: FakeData.dallasLongScenario)
        }
        .padding()
    }
    .preferredColorScheme(.dark)
}
