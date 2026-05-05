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

    /// Tournament draw size — used to derive the per-plan round number for the chip badge.
    /// singlesPlans[0] → drawSize, [1] → drawSize/2, etc.
    /// Defaults to 32 for backward-compat call sites (preview blocks, etc.).
    /// round-progression-and-formats spec §J.
    var drawSize: Int = 32

    /// Drives AppState.selectedMatchId — tapping a chip writes here.
    @Binding var selectedMatchId: UUID?

    /// Called when the empty-state CTA button is tapped.
    let onAddMatch: () -> Void

    /// Called when the Done toggle is tapped on a chip. Receives the tapped plan's matchId.
    /// match-done-state-cards spec §E.6 — routes to AppState.toggleMatchDone.
    let onToggleDone: (UUID) -> Void

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
                            roundNumeric: roundNumericFor(plan),
                            isSelected: plan.matchId == selectedMatchId,
                            onToggleDone: { onToggleDone(plan.matchId) }
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

    // MARK: - Round Badge Helper

    /// Derives the numeric round for a plan from its stream position.
    ///
    /// stream[0] → drawSize (R64, R32, etc.)
    /// stream[1] → drawSize/2
    /// stream[2] → drawSize/4 … clamped to ≥2 (Final).
    ///
    /// Plans are ordered by scheduledStart ASC so earlier matches come first,
    /// matching the typical R64→R32→QF→SF→F progression.
    ///
    /// round-progression-and-formats spec §J
    private func roundNumericFor(_ plan: Plan) -> Int {
        let streamPlans = allPlans.filter { $0.matchType == plan.matchType }
        let streamIdx   = streamPlans.firstIndex(where: { $0.matchId == plan.matchId }) ?? 0
        var divisor = 1
        for _ in 0..<streamIdx { divisor *= 2 }
        return max(drawSize / divisor, 2)
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
    /// Numeric round for the compact badge (e.g. 32 → "R32", 8 → "QF").
    /// Derived by ScheduleStripView.roundNumericFor(_:) from stream position.
    /// round-progression-and-formats spec §J
    let roundNumeric: Int
    let isSelected: Bool
    /// Routed to AppState.toggleMatchDone via ScheduleStripView.onToggleDone.
    /// match-done-state-cards spec §E.6
    let onToggleDone: () -> Void

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

            // Row 2: Status + Done toggle (spec §E.6)
            // DoneToggleButton is declared in MatchStateDeckView.swift (internal, same module).
            // SwiftUI routes Button taps to the Button action, NOT to chip's .onTapGesture.
            HStack {
                statusView
                Spacer()
                DoneToggleButton(isDone: plan.isDone, onToggle: onToggleDone)
            }

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
        // round-progression-and-formats spec §J: compact badge "R32 · S" / "QF · D".
        // roundNumeric is derived from stream position by ScheduleStripView.roundNumericFor(_:).
        let abbr   = RoundVocab.abbreviation(for: roundNumeric)
        let letter = plan.matchType == .singles ? "S" : "D"
        return "\(abbr) · \(letter)"
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
        // spec V-3 + match-done-state-cards spec §C: check isDone FIRST, before time arithmetic.
        // Manual done overrides auto-derived .inProgress.
        if plan.isDone { return .done }
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
                onAddMatch: {},
                onToggleDone: { _ in }
            )
            Divider()
            ScheduleStripView(
                allPlans: [],
                selectedMatchId: .constant(nil),
                onAddMatch: {},
                onToggleDone: { _ in }
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
                onAddMatch: {},
                onToggleDone: { _ in }
            )
        }
        .padding(.vertical, 16)
    }
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
