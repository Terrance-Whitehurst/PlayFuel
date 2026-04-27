import SwiftUI

/// US-05 — Tournament dashboard (plan hub).
///
/// Top-to-bottom layout:
///   1. EmergencyBanner (if weather.extremeHeatRisk)
///   2. WeatherCardView
///   3. Match info strip
///   4. Horizontal scroll of ScenarioCardViews (short / normal / long)
///   5. FoodCardView
///   6. "Full Timeline" button → TimelineView
///   7. Footer: Disclaimer link (§A placement)
///
/// Stub state: tournaments without a plan show a "No plan available" message.
struct TournamentDashboardView: View {

    let tournament: Tournament

    @State private var showingDisclaimer = false
    @State private var showingTimeline = false

    private var plan: Plan? { FakeData.plan(for: tournament.id) }
    private var match: Match? { FakeData.match(for: tournament.id) }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {

                if let plan = plan {
                    // §B Emergency banner — renders when extreme_heat_risk = true
                    if plan.weather.extremeHeatRisk {
                        EmergencyBanner()
                    }

                    // Match info strip
                    if let match = match {
                        MatchInfoStrip(match: match)
                    }

                    // US-07 Weather card
                    WeatherCardView(weather: plan.weather)

                    // US-06 Scenario cards — horizontal scroll
                    scenariosSection(plan: plan)

                    // US-08 Food card
                    FoodCardView(foodOptions: plan.foodOptions)

                    // Full Timeline button
                    NavigationLink {
                        TimelineView(tournament: tournament, timeline: plan.timeline)
                    } label: {
                        Label("Full Day Timeline", systemImage: "calendar.badge.clock")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .padding(.horizontal, 16)

                    // §A Footer disclaimer link
                    footerDisclaimer

                } else {
                    stubNoPlan
                }
            }
            .padding(.vertical, 16)
        }
        .navigationTitle(tournament.name)
        .navigationBarTitleDisplayMode(.inline)
        .background(Color(.systemGroupedBackground))
        .sheet(isPresented: $showingDisclaimer) {
            DisclaimerView()
        }
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

    // MARK: - Stub state (Austin / Houston — no plan yet)

    private var stubNoPlan: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No plan generated yet")
                .font(.headline)
                .foregroundStyle(.secondary)

            Text("Add a match time to generate a tournament-day plan.\n(Stub tournament — Phase 3 will wire to FastAPI.)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }
}

// MARK: - Match Info Strip

private struct MatchInfoStrip: View {
    let match: Match

    var body: some View {
        HStack(spacing: 16) {
            infoItem(icon: "clock.fill", label: "Match 1", value: match.scheduledTime)

            Divider().frame(height: 36)

            if let next = match.estimatedNextMatchTime {
                infoItem(icon: "clock.arrow.circlepath", label: "Est. Match 2", value: next)
                Divider().frame(height: 36)
            }

            if let court = match.court {
                infoItem(icon: "mappin.circle.fill", label: "Court", value: court)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal, 16)
    }

    private func infoItem(icon: String, label: String, value: String) -> some View {
        VStack(spacing: 2) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.caption2)
                Text(label)
                    .font(.caption2)
            }
            .foregroundStyle(.secondary)

            Text(value)
                .font(.subheadline.weight(.semibold))
        }
    }
}

#Preview {
    NavigationStack {
        TournamentDashboardView(tournament: FakeData.dallasTournament)
    }
    .environmentObject(AppState())
}
