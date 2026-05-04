import SwiftUI

/// Multi-match schedule strip — the primary navigation control on the dashboard.
///
/// Renders a horizontally-scrollable strip of MatchChip views, one per plan,
/// ordered by scheduledStart ASC (the API delivers them pre-sorted).
/// Tapping a chip sets `selectedMatchId`, which drives the plan content below.
///
/// Empty state (no plans): renders a full-width CTA card with an "Add match" button.
///
/// Per NUTRITION_FIRST_IA_V1.md §C and §H.11.
struct ScheduleStripView: View {

    /// All plans from the envelope (singlesPlans + doublesPlans, pre-sorted by API).
    let allPlans: [Plan]

    /// Drives AppState.selectedMatchId — tapping a chip writes here.
    @Binding var selectedMatchId: UUID?

    /// Called when the empty-state CTA button is tapped.
    let onAddMatch: () -> Void

    var body: some View {
        if allPlans.isEmpty {
            emptyState
        } else {
            stripContent
        }
    }

    // MARK: - Strip

    private var stripContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Schedule", systemImage: "calendar")
                    .font(.headline)
                Spacer()
                Text("Tap to switch")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 12) {
                    ForEach(Array(allPlans.enumerated()), id: \.element.matchId) { index, plan in
                        MatchChip(
                            plan: plan,
                            displayIndex: index + 1,
                            isSelected: plan.matchId == selectedMatchId
                        )
                        .onTapGesture {
                            withAnimation(.easeInOut(duration: 0.15)) {
                                selectedMatchId = plan.matchId
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 4)
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 36))
                .foregroundStyle(Color.accentColor)

            Text("Add your first match")
                .font(.headline)

            Text("Tap below to add a match time so PlayFuel can build your fuel plan.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button("Add Match", action: onAddMatch)
                .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .padding(.horizontal, 16)
    }
}

// MARK: - MatchChip

/// A single chip in the schedule strip representing one match's plan.
private struct MatchChip: View {

    let plan: Plan
    let displayIndex: Int
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Row 1: Round label + time
            HStack(spacing: 6) {
                Text(roundLabel)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer(minLength: 8)
                Text(timeString)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Row 2: Status
            statusView

            // Row 3: Type pill
            typePill
        }
        .padding(12)
        .frame(width: 180, alignment: .leading)
        .background(chipBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
        )
    }

    // MARK: - Round Label

    private var roundLabel: String {
        // Prefer API roundLabel (e.g. "R16", "QF") then fall back to "Match N"
        // Plan doesn't directly carry roundLabel — it's on Match, not Plan.
        // Use "Match N" as the reliable fallback for the strip.
        "Match \(displayIndex)"
    }

    // MARK: - Time String
    //
    // Uses the canonical asClockTimeFromISO extension (DateFormatting.swift) —
    // same approach as ScenarioCardView after the fix/scenario-card-end-time hotfix.
    // Backend emits ISO 8601 UTC (e.g. "2026-04-26T14:00:00Z"); the extension
    // parses and reformats in the device's local timezone (e.g. "9:00 AM" in CDT).
    // Non-ISO strings (FakeData human-readable) pass through unchanged.
    // Nil scheduledStart → "—" (defensive for legacy plans pre-feat/match-card-time).

    private var timeString: String {
        if let iso = plan.scheduledStart, !iso.isEmpty {
            return iso.asClockTimeFromISO
        }
        // Defensive fallback: derive from the timeline's `.match` event.
        // Safe-guards against backend versions that pre-date commit d17b308
        // (feat/match-card-time) and don't emit `scheduledStart` on the Plan
        // envelope. The `.match` TimelineEvent has been emitted since Phase 4
        // with `time = match.scheduled_start.isoformat()`.
        if let matchEvent = plan.timeline.first(where: { $0.kind == .match }) {
            return matchEvent.time.asClockTimeFromISO
        }
        return "—"
    }

    // MARK: - Status

    private var matchStatus: ChipStatus {
        guard let iso = plan.scheduledStart,
              let start = ISO8601DateFormatter().date(from: iso) else { return .upcoming }
        let now = Date()
        let normalDuration = plan.scenarioPlans.first(where: { $0.scenario == "normal" })
        let durationMin = normalDuration?.durationMin ?? 120
        let estimatedEnd = start.addingTimeInterval(Double(durationMin) * 60)
        if now < start { return .upcoming }
        if now < estimatedEnd { return .inProgress }
        return .done
    }

    private enum ChipStatus { case upcoming, inProgress, done }

    @ViewBuilder
    private var statusView: some View {
        switch matchStatus {
        case .upcoming:
            Label(timeString, systemImage: "clock")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case .inProgress:
            Label("In Progress", systemImage: "circle.fill")
                .font(.caption2)
                .foregroundStyle(.orange)
        case .done:
            Label("Done", systemImage: "checkmark.circle.fill")
                .font(.caption2)
                .foregroundStyle(.green)
        }
    }

    // MARK: - Type Pill

    private var typePillLabel: String {
        switch plan.matchType {
        case .singles:
            return "Singles"
        case .doubles:
            // We don't have doublesFormat on Plan directly; use scenarioDuration to infer
            // (pro_set_8 has short=45; best_of_3 has short=60)
            let shortDuration = plan.scenarioPlans.first(where: { $0.scenario == "short" })?.durationMin ?? 60
            if shortDuration <= 45 {
                return "Doubles · Pro Set 8"
            }
            return "Doubles · BO3"
        }
    }

    private var typePill: some View {
        Text(typePillLabel)
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(typePillBackground.opacity(0.15))
            .foregroundStyle(typePillBackground)
            .clipShape(Capsule())
    }

    private var typePillBackground: Color {
        plan.matchType == .singles ? .accentColor : .purple
    }

    // MARK: - Background

    private var chipBackground: some View {
        Group {
            if isSelected {
                Color.accentColor.opacity(0.15)
            } else {
#if os(iOS)
                Color(.secondarySystemBackground)
#else
                Color.secondary.opacity(0.1)
#endif
            }
        }
    }
}

// MARK: - Preview

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return ScrollView {
        VStack(spacing: 16) {
            ScheduleStripView(
                allPlans: FakeData.dallasPlanEnvelope.allPlans,
                selectedMatchId: .constant(FakeData.dallasPlanEnvelope.allPlans.first?.matchId),
                onAddMatch: {}
            )
            Divider()
            ScheduleStripView(
                allPlans: [],
                selectedMatchId: .constant(nil),
                onAddMatch: {}
            )
        }
        .padding(.vertical, 16)
    }
    .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return ScrollView {
        VStack(spacing: 16) {
            ScheduleStripView(
                allPlans: FakeData.dallasPlanEnvelope.allPlans,
                selectedMatchId: .constant(FakeData.dallasPlanEnvelope.allPlans.first?.matchId),
                onAddMatch: {}
            )
        }
        .padding(.vertical, 16)
    }
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
