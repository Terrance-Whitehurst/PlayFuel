import SwiftUI

/// US-03 — Tournament list, live data via Repository.
///
/// Task #6: loads from GET /v1/tournaments (RLS-filtered, user's own tournaments).
/// Renders based on LoadState — idle/loading → ProgressView, failed → error + retry,
/// loaded → list of rows. Empty state explains that tournaments must exist server-side.
struct TournamentListView: View {

    @EnvironmentObject var appState: AppState
    @State private var showingCreateTournament = false

    var body: some View {
        Group {
            switch appState.tournaments {
            case .idle, .loading:
                ProgressView("Loading tournaments…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .failed(let message):
                errorView(message)

            case .loaded(let tournaments):
                if tournaments.isEmpty {
                    emptyView
                } else {
                    list(tournaments: tournaments)
                }
            }
        }
        .navigationTitle("My Tournaments")
        .navigationBarTitleDisplayMode(.large)
        .navigationDestination(for: Tournament.self) { tournament in
            TournamentDashboardView(tournament: tournament)
        }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("Sign Out", role: .destructive) {
                    appState.signOut()
                }
                .font(.caption)
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showingCreateTournament = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showingCreateTournament) {
            TournamentCreateView()
                .environmentObject(appState)
        }
        .task {
            // Load on first appear only — .loaded state is cached for the session.
            if case .idle = appState.tournaments {
                await appState.loadTournaments()
            }
        }
    }

    // MARK: - Subviews

    private func list(tournaments: [Tournament]) -> some View {
        List(tournaments) { tournament in
            NavigationLink(value: tournament) {
                TournamentRowView(tournament: tournament)
            }
        }
    }

    private var emptyView: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)

            Text("No tournaments yet")
                .font(.headline)

            Text("Tap + to add your first tournament.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 40))
                .foregroundStyle(.orange)

            Text("Couldn't load tournaments")
                .font(.headline)

            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Button("Retry") {
                Task { await appState.loadTournaments() }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
    // Preview uses FakeData via a stub AppState; previews don't hit the network.
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    state.tournaments = .loaded(FakeData.tournaments)
    return NavigationStack {
        TournamentListView()
    }
    .environmentObject(state)
}
