import SwiftUI

/// US-05 — Tournament dashboard (plan hub).
///
/// Task #6: plan is generated on-demand via POST /v1/tournaments/{tid}/plans/generate.
/// Weather / food / timeline are FakeData splices until Phase 4 (Task #7) and
/// Phase 5 (Task #8) replace them with real API data.
///
/// Layout (when plan is loaded):
///   1. EmergencyBanner (if weather.extremeHeatRisk)
///   2. WeatherCardView
///   3. Horizontal scroll of ScenarioCardViews (short / normal / long)
///   4. FoodCardView (if foodOptions is non-empty)
///   5. "Full Timeline" button (if timeline is non-empty)
///   6. Footer disclaimer link (§A placement)
///
/// MatchInfoStrip is removed in Task #6 — Match data is not fetched in the read-
/// only wiring task. It will return when the match-create flow ships.
struct TournamentDashboardView: View {

    let tournament: Tournament

    @EnvironmentObject var appState: AppState
    @State private var showingDisclaimer = false
    @State private var showingCreateMatch = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch appState.currentPlan {
                case .idle:
                    generateButton

                case .loading:
                    ProgressView("Generating plan…")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)

                case .failed(let message):
                    errorView(message)

                case .loaded(let plan):
                    planContent(plan: plan)
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
            // Reset plan state on each dashboard appearance so a stale plan from a
            // different tournament is never shown. User taps "Generate Plan" to load.
            appState.currentPlan = .idle
        }
    }

    // MARK: - Plan Content

    @ViewBuilder
    private func planContent(plan: Plan) -> some View {
        // §B Emergency banner — renders when extreme_heat_risk = true
        if plan.weather.extremeHeatRisk {
            EmergencyBanner()
        }

        // Phase 6: LLM/template plan summary — below EmergencyBanner, above WeatherCard
        if let llmSummary = plan.llmSummary {
            PlanSummaryCard(explanation: llmSummary)
        }

        // US-07 Weather card
        WeatherCardView(weather: plan.weather)

        // US-06 Scenario cards — horizontal scroll
        scenariosSection(plan: plan)

        // US-08 Food card (only when food options are available)
        if !plan.foodOptions.isEmpty {
            FoodCardView(foodOptions: plan.foodOptions)
        }

        // Full Timeline navigation (only when timeline is available)
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

        // §A Footer disclaimer link
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
    state.currentPlan = .loaded(FakeData.dallasPlan)
    return NavigationStack {
        TournamentDashboardView(tournament: FakeData.dallasTournament)
    }
    .environmentObject(state)
}
