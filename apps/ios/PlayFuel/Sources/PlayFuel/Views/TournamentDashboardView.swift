import SwiftUI

/// US-05 — Tournament dashboard (plan hub).
///
/// Task #6: plan is generated on-demand via POST /v1/tournaments/{tid}/plans/generate.
/// Weather / food / timeline are FakeData splices until Phase 4 (Task #7) and
/// Phase 5 (Task #8) replace them with real API data.
///
/// Layout (when plan is loaded — NUTRITION_FIRST_IA_V1.md §B locked order):
///   0. EmergencyBanner       — when extreme_heat_risk == true (IMMOVABLE per §A.3)
///   1. Singles|Doubles Picker— only when envelope.hasBothTypes
///   2. PlanSummaryCard       — when llmSummary present
///   3. ScheduleStripView     — always (empty-CTA when no plans)
///   4. NextActionCard        — always (fallback copy when nextAction nil)
///   5. FoodCardView          — when foodOptions non-empty
///   6. Scenario cards        — horizontal scroll
///   7. Full Day Timeline btn — when timeline non-empty
///   8. WeatherCardView       — compact pill, collapsed by default (demoted)
///   9. Footer disclaimer link
///
/// Weather demotion rationale (user steer 2026-04-27): parents already feel the
/// heat. The weather card was the first thing parents saw but it is not actionable.
/// Safety logic is UNCHANGED — extreme_heat_risk still fires EmergencyBanner at #0.
struct TournamentDashboardView: View {

    let tournament: Tournament

    @EnvironmentObject var appState: AppState
    @State private var showingDisclaimer = false
    @State private var showingCreateMatch = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch appState.currentPlanEnvelope {
                case .idle:
                    generateButton

                case .loading:
                    ProgressView("Generating plan…")
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
        }
        .sheet(isPresented: $showingDisclaimer) {
            DisclaimerView()
        }
        .sheet(isPresented: $showingCreateMatch) {
            MatchCreateView(
                tournamentId: tournament.id,
                existingMatchCount: 0
            )
            .environmentObject(appState)
        }
        .task {
            // Reset plan envelope on each dashboard appearance so a stale plan from a
            // different tournament is never shown. User taps "Generate Plan" to load.
            // Phase 8: also resets selectedMatchId; re-anchored on envelope arrival.
            appState.currentPlanEnvelope = .idle
            appState.selectedMatchType = .singles
            appState.selectedMatchId = nil
        }
    }

    // MARK: - Envelope Content (Phase 8 — per-match plans + schedule strip)
    //
    // Resolves the active Plan from the PlanEnvelope:
    //   - Singles|Doubles segmented picker rendered only when hasBothTypes == true.
    //   - Active plan = plan matching appState.selectedMatchId (set by strip tap or
    //     defaulted on envelope arrival via AppState.defaultMatchId(from:)).
    //
    // See NUTRITION_FIRST_IA_V1.md §B and §H.14 for the full UX specification.
    //
    // NOTE on macOS toolchain: `@EnvironmentObject` projected-value binding
    // ($appState.xxx) is immutable. Use explicit Binding computed vars instead.

    @ViewBuilder
    private func envelopeContent(envelope: PlanEnvelope) -> some View {
        // Segmented picker — only when both plan types are present.
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
        // Resolve active plan via selectedMatchId first; fall back to anyPlan.
        // Uses resolveActivePlan() helper to avoid illegal `let` in @ViewBuilder bodies
        // on older macOS Swift toolchains (Session 5 lesson).
        if let plan = resolveActivePlan(from: envelope) {
            planContent(plan: plan, envelope: envelope)
        } else {
            // No plans at all — defensive guard (shouldn't happen in normal use)
            generateButton
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

    // MARK: - Plan Content (NUTRITION_FIRST_IA_V1.md §B locked order)
    //
    // Order (top → bottom):
    //   0. EmergencyBanner   (extreme_heat_risk — IMMOVABLE)
    //   2. PlanSummaryCard   (LLM coach voice)
    //   3. ScheduleStripView (multi-match schedule strip)
    //   4. NextActionCard    (next actionable item)
    //   5. FoodCardView      (food options)
    //   6. Scenario cards    (horizontal scroll)
    //   7. Timeline button
    //   8. WeatherCardView   (compact pill, demoted)
    //   9. Disclaimer footer
    //
    // The envelope is passed so ScheduleStripView gets allPlans for the strip.

    @ViewBuilder
    private func planContent(plan: Plan, envelope: PlanEnvelope) -> some View {
        // #0 — Emergency banner (IMMOVABLE: see SAFETY_DISCLAIMERS.md §B)
        if plan.weather.extremeHeatRisk {
            EmergencyBanner()
        }

        // #2 — LLM/template plan summary (coach voice)
        if let llmSummary = plan.llmSummary {
            PlanSummaryCard(explanation: llmSummary)
        }

        // #3 — Schedule strip (primary navigation control)
        ScheduleStripView(
            allPlans: envelope.allPlans,
            selectedMatchId: selectedMatchIdBinding,
            onAddMatch: { showingCreateMatch = true }
        )

        // #4 — Next action card (glance-test: parent knows "what's next" in 2 sec)
        NextActionCard(nextAction: plan.nextAction)

        // #5 — Food card (only when options available; bag fallback rendered inside)
        if !plan.foodOptions.isEmpty {
            FoodCardView(foodOptions: plan.foodOptions)
        }

        // #6 — Scenario cards (horizontal scroll)
        scenariosSection(plan: plan)

        // #7 — Full Timeline button
        if !plan.timeline.isEmpty {
            NavigationLink {
                TimelineView(tournament: tournament, timeline: plan.timeline)
            } label: {
                Label("Full Day Timeline", systemImage: "calendar.badge.clock")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .padding(.horizontal, 16)
        }

        // #8 — Weather card (compact pill, demoted — parents already feel the heat)
        // SAFETY NOTE: demotion of visual weight does NOT disable extreme_heat_risk
        // logic. The EmergencyBanner at #0 fires independently.
        WeatherCardView(weather: plan.weather, compact: true)

        // #9 — §A Footer disclaimer link
        footerDisclaimer
    }

    // MARK: - Idle State — Generate Button

    private var generateButton: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles")
                .font(.system(size: 48))
                .foregroundStyle(.green)

            Text("Generate today's plan")
                .font(.headline)

            Text("Add your matches with the + button, then generate a personalised fuel plan.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button("Generate Plan") {
                Task { await appState.generatePlan(for: tournament.id) }
            }
            .buttonStyle(.borderedProminent)
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
    // Phase 7: use the PlanEnvelope (both singles + doubles plans loaded for preview)
    state.currentPlanEnvelope = .loaded(FakeData.dallasPlanEnvelope)
    return NavigationStack {
        TournamentDashboardView(tournament: FakeData.dallasTournament)
    }
    .environmentObject(state)
}
