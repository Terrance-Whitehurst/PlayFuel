import SwiftUI

/// US-06 — Full day timeline.
///
/// Chronological list of TimelineEvents from wake-up through recovery.
/// Navigated to via "Full Timeline" button on TournamentDashboardView.
/// Phase 3: fed from Plan.timeline decoded from API.
struct TimelineView: View {

    let tournament: Tournament
    let timeline: [TimelineEvent]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(timeline.enumerated()), id: \.element.id) { index, event in
                    TimelineEventRow(
                        event: event,
                        isLast: index == timeline.count - 1
                    )
                }
            }
            .padding(.vertical, 16)
        }
        .navigationTitle("Day Timeline")
        .navigationBarTitleDisplayMode(.inline)
        .background(Color(.systemGroupedBackground))
    }
}

// MARK: - Timeline Event Row

private struct TimelineEventRow: View {
    let event: TimelineEvent
    let isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 0) {

            // Time column
            Text(event.time)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .trailing)
                .padding(.top, 4)

            // Connector + Icon column
            VStack(spacing: 0) {
                // Icon circle
                ZStack {
                    Circle()
                        .fill(kindColor(event.kind).opacity(0.15))
                        .frame(width: 32, height: 32)
                    Image(systemName: kindIcon(event.kind))
                        .font(.caption.weight(.medium))
                        .foregroundStyle(kindColor(event.kind))
                }

                // Vertical connector line
                if !isLast {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.2))
                        .frame(width: 2)
                        .frame(maxHeight: .infinity)
                }
            }
            .padding(.horizontal, 12)

            // Content column
            VStack(alignment: .leading, spacing: 4) {
                Text(event.title)
                    .font(.subheadline.weight(.semibold))
                Text(event.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 6)
            .padding(.trailing, 16)
            .padding(.bottom, isLast ? 0 : 20)
        }
        .padding(.leading, 16)
    }

    // MARK: - Kind Mapping

    private func kindIcon(_ kind: TimelineEventKind) -> String {
        switch kind {
        case .wakeUp:    return "alarm.fill"
        case .meal:      return "fork.knife"
        case .arrive:    return "mappin.circle.fill"
        case .warmUp:    return "figure.walk"
        case .match:     return "tennis.racket"
        case .recovery:  return "heart.fill"
        case .hydration: return "drop.fill"
        case .gap:                   return "clock"
        case .foodWindow:            return "fork.knife"
        case .pickup:                return "figure.wave"
        case .matchEnd:              return "flag.checkered"
        // Phase 7: doubles partner coordination event (DOUBLES_SPEC_V1.md §C.1)
        case .partnerCoordination:   return "person.2.fill"
        }
    }

    private func kindColor(_ kind: TimelineEventKind) -> Color {
        switch kind {
        case .wakeUp:    return .indigo
        case .meal:      return .green
        case .arrive:    return .orange
        case .warmUp:    return .blue
        case .match:     return .yellow
        case .recovery:  return .red
        case .hydration: return .teal
        case .gap:                   return .secondary
        case .foodWindow:            return .green
        case .pickup:                return .purple
        case .matchEnd:              return .gray
        // Phase 7: doubles partner coordination event
        case .partnerCoordination:   return .cyan
        }
    }
}

#Preview {
    NavigationStack {
        TimelineView(
            tournament: FakeData.dallasTournament,
            timeline: FakeData.dallasTimeline
        )
    }
}
