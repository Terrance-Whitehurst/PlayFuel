import SwiftUI

/// US-03 — Tournament list.
///
/// Shows 1–3 hardcoded tournaments from FakeData. Tap → TournamentDashboardView.
/// Phase 2+: load from `GET /tournaments` (user's own tournaments via RLS).
struct TournamentListView: View {

    @EnvironmentObject var appState: AppState

    private let tournaments = FakeData.tournaments

    var body: some View {
        List(tournaments) { tournament in
            NavigationLink(value: tournament) {
                TournamentRowView(tournament: tournament)
            }
        }
        .navigationTitle("My Tournaments")
        .navigationBarTitleDisplayMode(.large)
        .navigationDestination(for: Tournament.self) { tournament in
            TournamentDashboardView(tournament: tournament)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Sign Out", role: .destructive) {
                    appState.signOut()
                }
                .font(.caption)
            }
        }
    }
}

// MARK: - Tournament Row

private struct TournamentRowView: View {
    let tournament: Tournament

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(tournament.name)
                .font(.headline)

            Text(tournament.venue)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            HStack(spacing: 6) {
                Image(systemName: "calendar")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Text(dateRangeText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Badge: "Plan Ready" if a plan exists; "No plan yet" for stubs
            let hasPlan = FakeData.plan(for: tournament.id) != nil
            HStack(spacing: 4) {
                Image(systemName: hasPlan ? "checkmark.circle.fill" : "clock.circle")
                    .font(.caption2)
                Text(hasPlan ? "Plan Ready" : "No plan yet")
                    .font(.caption2.weight(.medium))
            }
            .foregroundStyle(hasPlan ? .green : .secondary)
            .padding(.top, 2)
        }
        .padding(.vertical, 4)
    }

    private var dateRangeText: String {
        if let end = tournament.endDate {
            return "\(tournament.startDate) – \(end)"
        }
        return tournament.startDate
    }
}

#Preview {
    NavigationStack {
        TournamentListView()
    }
    .environmentObject(AppState())
}
