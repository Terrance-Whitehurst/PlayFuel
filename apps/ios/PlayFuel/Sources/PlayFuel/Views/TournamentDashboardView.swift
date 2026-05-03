import SwiftUI

/// US-05 — Tournament dashboard (plan hub).
///
/// Task #6: plan is generated on-demand via POST /v1/tournaments/{tid}/plans/generate.
/// Weather / food / timeline are FakeData splices until Phase 4 (Task #7) and
/// Phase 5 (Task #8) replace them with real API data.
///
/// Layout (when plan is loaded — HEADER_BUBBLES_V1.md §D locked order):
///   0. EmergencyStrip        — when extreme_heat_risk == true (IMMOVABLE per §A.3)
///                              Rendered in envelopeContent(), ABOVE the Picker (fixes QA-IA-1)
///   1. Singles|Doubles Picker— only when envelope.hasBothTypes
///   2. HeaderBubbleRow       — [Plan Summary bubble] [Weather bubble] (always when plan loaded)
///   3. ScheduleStripView     — always (empty-CTA when no plans)
///   4. NextActionCard        — always (fallback copy when nextAction nil)
///   5. FoodOptionDeck         — always (handles bag-fallback state internally)
///   6. Scenario cards        — horizontal scroll
///   7. Full Day Timeline btn — when timeline non-empty
///   8. Footer disclaimer link
///
/// Bubble pattern rationale (user steer 2026-04-27, HEADER_BUBBLES_V1.md):
/// PlanSummaryCard and WeatherCard are moved one tap deep into sheets opened
/// by HeaderBubbleRow bubbles. Dashboard scroll above ScheduleStrip contains
/// only the safety strip, type picker, and 2 small icon buttons.
///
/// Safety logic is UNCHANGED — extreme_heat_risk still fires EmergencyStrip at #0.
/// EmergencyBanner.swift is preserved untouched (used in other contexts + previews).
struct TournamentDashboardView: View {

    let tournament: Tournament

    @EnvironmentObject var appState: AppState
    @State private var showingDisclaimer = false
    @State private var showingCreateMatch = false
    @State private var showProfile = false
    @State private var showMatchDetail = false
    @State private var showFeedbackSheet = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch appState.currentPlanEnvelope {
                case .idle, .loading:
                    ProgressView("Preparing your plan…")
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
                // Phase 5b: Add match — always visible on dashboard.
                // TODO: hide when matchCount >= 2 once match fetching is wired on dashboard load.
                Button {
                    showingCreateMatch = true
                } label: {
                    Label("Add Match", systemImage: "plus")
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
        }
        .sheet(isPresented: $showingDisclaimer) {
            DisclaimerView()
        }
        .sheet(isPresented: $showProfile) {
            ProfileMenuSheet()
                .presentationDetents([.height(280), .medium])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showMatchDetail) {
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
                existingMatchCount: 0
            )
            .environmentObject(appState)
        }
        // Phase 7 — post-tournament feedback sheet
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

    // MARK: - Envelope Content (Phase 8.1 — bubble header pattern)
    //
    // Resolves the active Plan from the PlanEnvelope:
    //   - EmergencyStrip rendered FIRST (above Picker) — fixes QA-IA-1.
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
        // #0 IMMOVABLE — EmergencyStrip rendered ABOVE the Picker (fixes QA-IA-1).
        // Hoisting here ensures the strip is at visual position #0 even when
        // hasBothTypes == true and the Picker is visible.
        // SAFETY_DISCLAIMERS.md §B · HEADER_BUBBLES_V1.md §C (option b) · §F.7
        if let plan = resolveActivePlan(from: envelope), plan.weather.extremeHeatRisk {
            EmergencyStrip()
        }

        // #1 Segmented picker — only when both plan types are present.
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

        // #2 Bubble header row — Plan Summary + Weather + Map bubbles.
        // Only rendered when a plan is available (envelope non-empty).
        // HEADER_BUBBLES_V1.md §D position 2 · §F.7
        // FOOD_DECK_AND_MAP_V1.md §I-6: `tournament` added for Map bubble.
        if let plan = resolveActivePlan(from: envelope) {
            HeaderBubbleRow(plan: plan, tournament: tournament)
        }

        // #3–8 Plan content (ScheduleStrip, NextActionCard, FoodCard, Scenarios,
        // Timeline button, Disclaimer footer — stripped of EmergencyBanner,
        // PlanSummaryCard, WeatherCardView per HEADER_BUBBLES_V1.md §D).
        if let plan = resolveActivePlan(from: envelope) {
            planContent(plan: plan, envelope: envelope)
        } else {
            // No matches added yet — envelope is empty (OQ-IA-9: 200 with empty arrays).
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
    // envelopeContent() — they are NOT in this builder.
    //
    // Order (top → bottom, positions 3–8):
    //   3. ScheduleStripView (multi-match schedule strip)
    //   4. NextActionCard    (next actionable item)
    //   5. FoodOptionDeck    (food deck — bag fallback handled inside)
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
        // #3 — Schedule strip (primary navigation control)
        ScheduleStripView(
            allPlans: envelope.allPlans,
            selectedMatchId: selectedMatchIdBinding,
            onAddMatch: { showingCreateMatch = true }
        )

        // POST_MATCH_EVAL_V1.md §E.1 — "View match details" link below the strip.
        // The strip remains a quick switcher; this link provides deliberate drill-in
        // access to the MatchDetailView (post-match write-up + metadata).
        // Only shown when there is a resolvable active plan.
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

        // #4 — Next action card (glance-test: parent knows "what's next" in 2 sec)
        NextActionCard(nextAction: plan.nextAction)

        // #5 — Food option deck (replaces FoodCardView inline per FOOD_DECK_AND_MAP_V1.md §E)
        // FoodOptionDeck handles its own empty/bag-fallback state — always rendered.
        FoodOptionDeck(foodOptions: plan.foodOptions, bagFallbackOnly: plan.bagFallbackOnly)

        // #6 — Scenario cards (horizontal scroll)
        scenariosSection(plan: plan)

        // #7 — Full Timeline button
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
            .buttonStyle(.borderedProminent)
            .padding(.horizontal, 16)
        }

        // #8 — Feedback CTA (only when all matches are in the past)
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

        // #9 — §A Footer disclaimer link
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
                        ScenarioCardView(plan: scenario)
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
