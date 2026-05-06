import SwiftUI
import os

/// US-05 - Tournament dashboard (plan hub).
///
/// Task #6: plan is generated on-demand via POST /v1/tournaments/{tid}/plans/generate.
/// Weather / food / timeline are FakeData splices until Phase 4 (Task #7) and
/// Phase 5 (Task #8) replace them with real API data.
///
/// Layout (when plan is loaded - HEADER_BUBBLES_V1.md §D locked order):
///   0. EmergencyStrip        - when extreme_heat_risk == true (IMMOVABLE per §A.3)
///                              Rendered in envelopeContent(), ABOVE the Picker (fixes QA-IA-1)
///   1. Singles|Doubles Picker- only when envelope.hasBothTypes
///   2. HeaderBubbleRow       - [Plan Summary bubble] [Weather bubble] (always when plan loaded)
///   3. ScheduleStripView     - always (empty-CTA when no plans)
///   4. NextActionCard        - always (fallback copy when nextAction nil)
///   5. FoodOptionDeck         - always (handles bag-fallback state internally)
///   6. Scenario cards        - horizontal scroll
///   7. Full Day Timeline btn - when timeline non-empty
///   8. Footer disclaimer link
///
/// Bubble pattern rationale (user steer 2026-04-27, HEADER_BUBBLES_V1.md):
/// PlanSummaryCard and WeatherCard are moved one tap deep into sheets opened
/// by HeaderBubbleRow bubbles. Dashboard scroll above ScheduleStrip contains
/// only the safety strip, type picker, and 2 small icon buttons.
///
/// Safety logic is UNCHANGED - extreme_heat_risk still fires EmergencyStrip at #0.
/// EmergencyBanner.swift is preserved untouched (used in other contexts + previews).
struct TournamentDashboardView: View {

    let tournament: Tournament

    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var showingDisclaimer = false
    @State private var showingCreateMatch = false
    @State private var showProfile = false
    @State private var showMatchDetail = false
    @State private var showFeedbackSheet = false
    // Delete state
    @State private var showDeleteTournamentConfirm = false
    @State private var showDeleteErrorToast = false
    @State private var isDeletingTournament = false
    // match-done-state-cards spec §E.6 / §E.7
    @State private var showMarkDayDoneConfirm = false
    @State private var showDoneErrorToast = false

    private static let deleteLogger = Logger(subsystem: "com.playfuel.ios", category: "delete")

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch appState.currentPlanEnvelope {
                case .idle, .loading:
                    ProgressView("Preparing your plan...")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)

                case .failed(let message):
                    errorView(message)

                case .loaded(let envelope):
                    envelopeContent(envelope: envelope)
                }
            }
            .padding(.vertical, 16)
        }
        .navigationTitle(tournament.name)
        .navigationBarTitleDisplayMode(.inline)
        .background(Color(.systemGroupedBackground))
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                // round-progression-and-formats spec §J: hide when both streams are terminal
                // (all rounds through the Final have been added).
                if canAddMoreMatches {
                    Button {
                        showingCreateMatch = true
                    } label: {
                        Label("Add Match", systemImage: "plus")
                    }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showProfile = true
                } label: {
                    Image(systemName: "person.crop.circle.fill")
                        .font(.title3)
                }
                .accessibilityLabel("Profile")
            }
            // ••• overflow menu - non-destructive actions first, destructive last (spec §D.1, I-16)
            // match-done-state-cards spec §E.7: "Mark day done" added above "Delete tournament".
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    // Non-destructive: Mark day done
                    Button {
                        if case .loaded(let envelope) = appState.currentPlanEnvelope {
                            let iso = ISO8601DateFormatter()
                            let now = Date()
                            let hasFutureUndone = envelope.allPlans.contains { plan in
                                guard !plan.isDone, let str = plan.scheduledStart else { return false }
                                return (iso.date(from: str) ?? .distantPast) > now
                            }
                            if hasFutureUndone {
                                showMarkDayDoneConfirm = true
                            } else {
                                Task { await markDayDone() }
                            }
                        }
                    } label: {
                        Label("Mark day done", systemImage: "checkmark.circle.fill")
                    }
                    // Destructive: Delete tournament
                    Button(role: .destructive) {
                        showDeleteTournamentConfirm = true
                    } label: {
                        Label("Delete tournament", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .accessibilityLabel("More options")
            }
        }
        .sheet(isPresented: $showingDisclaimer) {
            DisclaimerView()
        }
        .sheet(isPresented: $showProfile) {
            ProfileMenuSheet()
                .presentationDetents([.height(280), .medium])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showMatchDetail, onDismiss: {
            // Re-generate plan after MatchDetailView dismisses.
            // If a match was deleted, the cache was already invalidated in MatchDetailView
            // before dismiss, so this fetch returns a fresh plan without the deleted match.
            // If no match was deleted, the cache is hit instantly (no flicker). Safe per
            // AppState.generatePlan cache-first contract.
            Task { await appState.generatePlan(for: tournament.id) }
        }) {
            if case .loaded(let envelope) = appState.currentPlanEnvelope,
               let activePlan = resolveActivePlan(from: envelope) {
                let allPlans = envelope.allPlans
                let idx = (allPlans.firstIndex { $0.matchId == activePlan.matchId } ?? 0) + 1
                MatchDetailView(plan: activePlan, matchIndex: idx)
                    .environmentObject(appState)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
        }
        .sheet(isPresented: $showingCreateMatch) {
            MatchCreateView(
                tournamentId: tournament.id,
                drawSize: tournament.drawSize ?? 32,
                existingMatchCount: currentMatchCount,
                existingSinglesCount: singlesStreamCount,
                existingDoublesCount: doublesStreamCount,
                tournamentStartDate: tournamentStartAsDate,
                tournamentEndDate: tournamentEndAsDate
            )
            .environmentObject(appState)
        }
        // Delete tournament confirmation dialog (spec §D.2)
        .confirmationDialog(
            "Delete tournament?",
            isPresented: $showDeleteTournamentConfirm,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                Task { await performDeleteTournament() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(deleteTournamentMessage)
        }
        // Error toast overlay (spec §D.4 - shown when delete API call fails)
        .overlay(alignment: .bottom) {
            if showDeleteErrorToast {
                Text("Couldn't delete - please try again.")
                    .font(.subheadline)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.red.opacity(0.9), in: RoundedRectangle(cornerRadius: 10))
                    .padding(.bottom, 32)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.easeInOut(duration: 0.25), value: showDeleteErrorToast)
            }
        }
        // Done-state error toast (match-done-state-cards spec §E.6 / §E.7)
        .overlay(alignment: .bottom) {
            if showDoneErrorToast {
                Text("Couldn't update match - please try again.")
                    .font(.subheadline)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.red.opacity(0.9), in: RoundedRectangle(cornerRadius: 10))
                    .padding(.bottom, 88)  // above the delete toast slot
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.easeInOut(duration: 0.25), value: showDoneErrorToast)
            }
        }
        // Mark Day Done confirmation (spec §E.7: shown only when future-undone matches exist)
        .confirmationDialog(
            "Mark all matches done for today?",
            isPresented: $showMarkDayDoneConfirm,
            titleVisibility: .visible
        ) {
            Button("Mark Done") {
                Task { await markDayDone() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This will show end-of-day suggestions.")
        }
        // Phase 7 - post-tournament feedback sheet
        .sheet(isPresented: $showFeedbackSheet) {
            TournamentFeedbackView(tournament: tournament)
                .environmentObject(appState)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .task(id: tournament.id) {
            // Phase 8.6: Auto-generate plan on tournament selection.
            // .task(id:) re-fires when tournament.id changes (i.e. the user switches
            // to a different tournament), and on first appearance. generatePlan is
            // idempotent (OQ-IA-9 upsert) so re-generation is always safe.
            appState.selectedMatchType = .singles
            appState.selectedMatchId = nil
            await appState.generatePlan(for: tournament.id)
        }
    }

    // MARK: - Envelope Content (Phase 8.1 - bubble header pattern)
    //
    // Resolves the active Plan from the PlanEnvelope:
    //   - EmergencyStrip rendered FIRST (above Picker) - fixes QA-IA-1.
    //   - Singles|Doubles segmented picker rendered only when hasBothTypes == true.
    //   - HeaderBubbleRow rendered just below picker (Phase 8.1 bubble pattern).
    //   - Active plan = plan matching appState.selectedMatchId (set by strip tap or
    //     defaulted on envelope arrival via AppState.defaultMatchId(from:)).
    //
    // See HEADER_BUBBLES_V1.md §D and §F.7 for the full UX specification.
    //
    // NOTE: resolveActivePlan(from:) is called multiple times in this builder to
    // avoid illegal `let` bindings in @ViewBuilder on older macOS toolchains.
    // The function is trivial (property accesses only) so repeated calls are fine.
    //
    // NOTE on macOS toolchain: `@EnvironmentObject` projected-value binding
    // ($appState.xxx) is immutable. Use explicit Binding computed vars instead.

    @ViewBuilder
    private func envelopeContent(envelope: PlanEnvelope) -> some View {
        // #0 IMMOVABLE - EmergencyStrip rendered ABOVE the Picker (fixes QA-IA-1).
        // Hoisting here ensures the strip is at visual position #0 even when
        // hasBothTypes == true and the Picker is visible.
        // SAFETY_DISCLAIMERS.md §B · HEADER_BUBBLES_V1.md §C (option b) · §F.7
        if let plan = resolveActivePlan(from: envelope), plan.weather.extremeHeatRisk {
            EmergencyStrip()
        }

        // #1 Segmented picker - only when both plan types are present.
        // When user switches type, also reset selectedMatchId to that type's first match.
        if envelope.hasBothTypes {
            Picker("Match Type", selection: matchTypeBinding) {
                ForEach(MatchType.allCases, id: \.self) { type in
                    Text(type.displayName).tag(type)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .onChange(of: appState.selectedMatchType) { _, newType in
                // Re-anchor strip to the first match of the newly selected type.
                let firstPlan = newType == .singles
                    ? envelope.singlesPlans.first
                    : envelope.doublesPlans.first
                appState.selectedMatchId = firstPlan?.matchId
            }
        }

        // #2 Bubble header row - Plan Summary + Weather + Map bubbles.
        // Only rendered when a plan is available (envelope non-empty).
        // HEADER_BUBBLES_V1.md §D position 2 · §F.7
        // FOOD_DECK_AND_MAP_V1.md §I-6: `tournament` added for Map bubble.
        if let plan = resolveActivePlan(from: envelope) {
            HeaderBubbleRow(plan: plan, tournament: tournament)
        }

        // #3-8 Plan content (ScheduleStrip, NextActionCard, FoodCard, Scenarios,
        // Timeline button, Disclaimer footer - stripped of EmergencyBanner,
        // PlanSummaryCard, WeatherCardView per HEADER_BUBBLES_V1.md §D).
        if let plan = resolveActivePlan(from: envelope) {
            planContent(plan: plan, envelope: envelope)
        } else {
            // No matches added yet - envelope is empty (OQ-IA-9: 200 with empty arrays).
            emptyMatchesView
        }
    }

    /// Resolves the Plan to display:
    ///   1. Plan matching appState.selectedMatchId (strip selection)
    ///   2. First plan of selectedMatchType (type picker fall-through)
    ///   3. anyPlan (last resort)
    private func resolveActivePlan(from envelope: PlanEnvelope) -> Plan? {
        if let id = appState.selectedMatchId, let p = envelope.plan(for: id) { return p }
        return envelope.plan(for: appState.selectedMatchType) ?? envelope.anyPlan
    }

    /// Explicit Binding for `AppState.selectedMatchType`.
    /// Required because `$appState.selectedMatchType` is immutable on macOS toolchain.
    private var matchTypeBinding: Binding<MatchType> {
        Binding(
            get: { appState.selectedMatchType },
            set: { appState.selectedMatchType = $0 }
        )
    }

    /// Explicit Binding for `AppState.selectedMatchId`.
    private var selectedMatchIdBinding: Binding<UUID?> {
        Binding(
            get: { appState.selectedMatchId },
            set: { appState.selectedMatchId = $0 }
        )
    }

    // MARK: - Plan Content (HEADER_BUBBLES_V1.md §D locked order)
    //
    // EmergencyStrip, HeaderBubbleRow, and the Picker are rendered by
    // envelopeContent() - they are NOT in this builder.
    //
    // Order (top → bottom, positions 3-8):
    //   3. ScheduleStripView (multi-match schedule strip)
    //   4. NextActionCard    (next actionable item)
    //   5. FoodOptionDeck    (food deck - bag fallback handled inside)
    //   6. Scenario cards    (horizontal scroll)
    //   7. Timeline button
    //   8. Disclaimer footer
    //
    // Removed from this builder (moved to bubbles / strip):
    //   EmergencyBanner  → replaced by EmergencyStrip in envelopeContent()
    //   PlanSummaryCard  → accessible via HeaderBubbleRow "Today's Plan" bubble
    //   WeatherCardView  → accessible via HeaderBubbleRow weather bubble
    //
    // The envelope is passed so ScheduleStripView gets allPlans for the strip.

    @ViewBuilder
    private func planContent(plan: Plan, envelope: PlanEnvelope) -> some View {
        // #3 - Schedule strip (primary navigation control)
        // onToggleDone calls AppState.toggleMatchDone; failure triggers the done error toast.
        ScheduleStripView(
            allPlans: envelope.allPlans,
            drawSize: tournament.drawSize ?? 32,
            selectedMatchId: selectedMatchIdBinding,
            onAddMatch: { showingCreateMatch = true },
            onToggleDone: { matchId in
                Task {
                    let ok = await appState.toggleMatchDone(
                        matchId: matchId, tournamentId: tournament.id
                    )
                    if !ok {
                        withAnimation { showDoneErrorToast = true }
                        Task {
                            try? await Task.sleep(nanoseconds: 3_000_000_000)
                            withAnimation { showDoneErrorToast = false }
                        }
                    }
                }
            }
        )

        // POST_MATCH_EVAL_V1.md §E.1 - "View match details" link below the strip.
        Button {
            showMatchDetail = true
        } label: {
            HStack(spacing: 4) {
                Text("View match details")
                    .font(.subheadline)
                Image(systemName: "chevron.right")
                    .font(.caption)
            }
            .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .padding(.horizontal, 16)
        .padding(.top, -4)

        // #3.5 - State-aware card deck (match-done-state-cards spec §E.1)
        // Placed between the "View match details" link and NextActionCard per spec §E.1.
        // Uses nextActionablePlan as the active plan so the deck always has a plan
        // even when all matches are done (end-of-day deck path).
        MatchStateDeckView(
            activePlan: envelope.nextActionablePlan ?? plan,
            allPlans: envelope.allPlans
        )

        // #4 - Next action card (glance-test: parent knows "what's next" in 2 sec)
        NextActionCard(nextAction: plan.nextAction)

        // #5 - Food option deck (replaces FoodCardView inline per FOOD_DECK_AND_MAP_V1.md §E)
        // FoodOptionDeck handles its own empty/bag-fallback/unavailable state - always rendered.
        // OQ-FOOD-EMPTY-1: placesUnavailable drives the three-way conditional render.
        FoodOptionDeck(
            foodOptions: plan.foodOptions,
            bagFallbackOnly: plan.bagFallbackOnly,
            placesUnavailable: plan.placesUnavailable
        )

        // #6 - Scenario cards (horizontal scroll)
        scenariosSection(plan: plan)

        // #7 - Full Timeline button
        // Shows timeline events for ALL matches in the tournament (not just the
        // currently-selected match). envelope.allTimeline merges and sorts the
        // per-match timelines chronologically so new matches appear immediately
        // after plan re-generation. fix/full-day-timeline-multi-match.
        if !envelope.allTimeline.isEmpty {
            NavigationLink {
                TimelineView(tournament: tournament, timeline: envelope.allTimeline)
            } label: {
                Label("Full Day Timeline", systemImage: "calendar.badge.clock")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(GlassProminentButtonStyle())
            .padding(.horizontal, 16)
        }

        // #8 - Feedback CTA (only when all matches are in the past)
        // phase7-feedback-spec.md §E.1
        if envelope.allMatchesPast {
            Button {
                showFeedbackSheet = true
            } label: {
                Label("Rate This Tournament", systemImage: "star.bubble")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .padding(.horizontal, 16)
        }

        // #9 - §A Footer disclaimer link
        footerDisclaimer
    }

    // MARK: - Empty State (no matches added yet)

    private var emptyMatchesView: some View {
        VStack(spacing: 16) {
            Image(systemName: "tennisball.fill")
                .font(.system(size: 48))
                .foregroundStyle(Color.accentColor)

            Text("No matches yet")
                .font(.headline)

            Text("Tap + to add your first match. Your plan will generate automatically.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
        .padding(.vertical, 60)
    }

    // MARK: - Error State

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 40))
                .foregroundStyle(.orange)

            Text("Couldn't generate plan")
                .font(.headline)

            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Button("Retry") {
                Task { await appState.generatePlan(for: tournament.id) }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(.vertical, 60)
    }

    // MARK: - Scenarios Section

    private func scenariosSection(plan: Plan) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Match Scenarios", systemImage: "rectangle.stack.fill")
                    .font(.headline)
                Spacer()
                Text("Scroll →")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(plan.scenarioPlans) { scenario in
                        // §F.3 - pass plan-level foodOptions for client-side per-scenario
                        // filtering in ScenarioDetailSheetView (OQ-POP-1: food_options is
                        // top-level on Plan, not per-scenario).
                        ScenarioCardView(
                            plan: scenario,
                            foodOptions: plan.foodOptions,
                            extremeHeatRisk: plan.weather.extremeHeatRisk
                        )
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    // MARK: - Footer Disclaimer (§A placement)

    private var footerDisclaimer: some View {
        Button {
            showingDisclaimer = true
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "info.circle")
                    .font(.caption)
                Text("Usage guidelines & disclaimer")
                    .font(.caption)
            }
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }

    // MARK: - Match Count Helper

    /// Number of match plans currently loaded in the envelope.
    // MARK: - Tournament date helpers

    /// Parses `tournament.startDate` ("yyyy-MM-dd" String) to a `Date`.
    /// Falls back to today if the string is malformed.
    private var tournamentStartAsDate: Date {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        return fmt.date(from: tournament.startDate) ?? Date()
    }

    /// Parses `tournament.endDate` to a `Date`. Falls back to `tournamentStartAsDate`
    /// for single-day tournaments (nil endDate).
    private var tournamentEndAsDate: Date {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        let str = tournament.endDate ?? tournament.startDate
        return fmt.date(from: str) ?? tournamentStartAsDate
    }

    /// Used for `existingMatchCount` so display_order is correct for newly added matches.
    /// Falls back to 0 if the envelope isn't loaded yet (cache cold or first match).
    private var currentMatchCount: Int {
        if case .loaded(let envelope) = appState.currentPlanEnvelope {
            return envelope.allPlans.count
        }
        return 0
    }

    // MARK: - Round Progression Helpers (round-progression-and-formats spec §J)

    /// Number of singles plans currently loaded (for next-allowed-round computation).
    private var singlesStreamCount: Int {
        if case .loaded(let envelope) = appState.currentPlanEnvelope {
            return envelope.singlesPlans.count
        }
        return 0
    }

    /// Number of doubles plans currently loaded.
    private var doublesStreamCount: Int {
        if case .loaded(let envelope) = appState.currentPlanEnvelope {
            return envelope.doublesPlans.count
        }
        return 0
    }

    /// Returns true when a stream has no remaining rounds to play.
    /// Terminal = the Final has been added (drawSize / 2^count < 2).
    private func isStreamTerminal(drawSize: Int, count: Int) -> Bool {
        var divisor = 1
        for _ in 0..<count { divisor *= 2 }
        return drawSize / divisor < 2
    }

    /// True when at least one stream (singles or doubles) still has rounds available.
    /// Drives visibility of the "Add Match" toolbar button.
    private var canAddMoreMatches: Bool {
        let drawSz = tournament.drawSize ?? 32
        let singlesTerminal = isStreamTerminal(drawSize: drawSz, count: singlesStreamCount)
        let doublesTerminal = isStreamTerminal(drawSize: drawSz, count: doublesStreamCount)
        return !(singlesTerminal && doublesTerminal)
    }

    // MARK: - Mark Day Done (match-done-state-cards spec §E.7)

    /// Marks every undone plan in the current envelope done.
    /// Calls toggleMatchDone sequentially (avoids optimistic-update race conditions).
    /// Shows the done error toast if any individual toggle fails.
    private func markDayDone() async {
        guard case .loaded(let envelope) = appState.currentPlanEnvelope else { return }
        let undone = envelope.allPlans.filter { !$0.isDone }
        guard !undone.isEmpty else { return }

        var anyFailed = false
        for plan in undone {
            let ok = await appState.toggleMatchDone(
                matchId: plan.matchId, tournamentId: tournament.id
            )
            if !ok { anyFailed = true }
        }

        if anyFailed {
            withAnimation { showDoneErrorToast = true }
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                withAnimation { showDoneErrorToast = false }
            }
        }
    }

    // MARK: - Delete Tournament Helpers (spec §D.1 – §D.4)

    /// Dynamic message for the tournament delete confirmation dialog.
    /// Spec §D.2: today prefix + accurate match/plan count.
    private var deleteTournamentMessage: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        let isTodayTournament: Bool
        if let date = fmt.date(from: tournament.startDate) {
            isTodayTournament = Calendar.current.isDateInToday(date)
        } else {
            isTodayTournament = false
        }
        let todayPrefix = isTodayTournament ? "This tournament is today. " : ""

        // Use the currently-loaded envelope for accurate counts (we're on the dashboard,
        // so currentPlanEnvelope is guaranteed to be .loaded for this tournament).
        let matchCount: Int
        if case .loaded(let envelope) = appState.currentPlanEnvelope {
            matchCount = envelope.allPlans.count
        } else {
            matchCount = 0
        }

        if matchCount > 0 {
            let matchWord = matchCount == 1 ? "match" : "matches"
            let planWord  = matchCount == 1 ? "plan"  : "plans"
            return "\(todayPrefix)This will also delete \(matchCount) \(matchWord), \(matchCount) \(planWord), and any feedback. This can't be undone."
        } else {
            return "\(todayPrefix)This can't be undone."
        }
    }

    /// Executes the tournament delete from the detail screen.
    /// Strategy: optimistic remove from list → await API → dismiss on success;
    /// on failure restore list state + show inline toast (user is still on dashboard).
    private func performDeleteTournament() async {
        guard !isDeletingTournament else { return }
        isDeletingTournament = true
        defer { isDeletingTournament = false }

        let matchCount: Int
        if case .loaded(let envelope) = appState.currentPlanEnvelope {
            matchCount = envelope.allPlans.count
        } else {
            matchCount = 0
        }

        // Optimistic: remove from the shared tournament list before the API call.
        let removed = appState.optimisticRemoveTournament(id: tournament.id)

        let success = await appState.deleteTournamentViaAPI(id: tournament.id)
        if success {
            // Telemetry - fire-and-forget (spec §E)
            Self.deleteLogger.info("tournament_deleted tournament_id=\(tournament.id.uuidString) match_count=\(matchCount) plan_count=\(matchCount) had_feedback=false")
            // Pop back to TournamentListView (AC#5 - no stale row on detail screen)
            dismiss()
        } else {
            // Restore optimistic state - user is still on the dashboard.
            if let (t, idx) = removed {
                appState.restoreTournament(t, at: idx)
            }
            withAnimation { showDeleteErrorToast = true }
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                withAnimation { showDeleteErrorToast = false }
            }
        }
    }
}

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    state.currentPlanEnvelope = .loaded(FakeData.dallasPlanEnvelope)
    return NavigationStack {
        TournamentDashboardView(tournament: FakeData.dallasTournament)
    }
    .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    state.currentPlanEnvelope = .loaded(FakeData.dallasPlanEnvelope)
    return NavigationStack {
        TournamentDashboardView(tournament: FakeData.dallasTournament)
    }
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
