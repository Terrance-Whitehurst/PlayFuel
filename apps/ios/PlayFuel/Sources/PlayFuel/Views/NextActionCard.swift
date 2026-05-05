import SwiftUI

/// NEXT UP card — surfaces the most immediately actionable item for the parent.
///
/// Renders the `Plan.nextAction` value, derived deterministically by the backend
/// rules engine (`rules/next_action.py`). Never produced by the LLM.
///
/// When `nextAction` is nil, renders a compact "All set — enjoy the day" fallback.
///
/// Per NUTRITION_FIRST_IA_V1.md §D and §H.12.
struct NextActionCard: View {

    /// The next action for this plan. Nil → show fallback copy.
    let nextAction: NextAction?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            headerRow
            if let action = nextAction {
                actionContent(action)
            } else {
                fallbackContent
            }
        }
        .padding(16)
        .background(cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal, 16)
    }

    // MARK: - Header Row

    private var headerRow: some View {
        HStack {
            Image(systemName: "bolt.fill")
                .foregroundStyle(Color.accentColor)
            Text("NEXT UP")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
                .tracking(1.2)
            Spacer()
            if let mins = nextAction?.minsUntil, mins >= 0 {
                Text("In \(DurationFormatting.friendly(minutes: mins))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.accentColor)
                    .clipShape(Capsule())
            }
        }
    }

    // MARK: - Action Content

    @ViewBuilder
    private func actionContent(_ action: NextAction) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(action.title)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)

            Text(action.detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let scheduled = action.scheduledFor {
                Text(formattedTime(scheduled))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - Fallback Content

    private var fallbackContent: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
                .font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                Text("All set — enjoy the day")
                    .font(.headline)
                Text("No upcoming events in your plan window.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Helpers

    private func formattedTime(_ date: Date) -> String {
        DateFormatting.clockTime(date)
    }

    private var cardBackground: some View {
#if os(iOS)
        Color(.systemBackground)
#else
        Color.secondary.opacity(0.08)
#endif
    }
}

// MARK: - Preview

#Preview {
    ScrollView {
        VStack(spacing: 16) {
            NextActionCard(nextAction: FakeData.dallasSinglesPlan1.nextAction)
            NextActionCard(nextAction: nil)
        }
        .padding(.vertical, 16)
    }
}

#Preview("Dark") {
    ScrollView {
        VStack(spacing: 16) {
            NextActionCard(nextAction: FakeData.dallasSinglesPlan1.nextAction)
            NextActionCard(nextAction: nil)
        }
        .padding(.vertical, 16)
    }
    .preferredColorScheme(.dark)
}
