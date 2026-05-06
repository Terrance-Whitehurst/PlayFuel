import SwiftUI
import os

/// US-03 — Tournament list, live data via Repository.
///
/// Task #6: loads from GET /v1/tournaments (RLS-filtered, user's own tournaments).
/// Renders based on LoadState — idle/loading → ProgressView, failed → error + retry,
/// loaded → list of rows. Empty state explains that tournaments must exist server-side.
struct TournamentListView: View {

    @EnvironmentObject var appState: AppState
    @State private var showingCreateTournament = false
    @State private var showProfile = false
    // Delete state
    @State private var tournamentToDelete: Tournament? = nil
    @State private var showDeleteConfirmation = false
    @State private var showDeleteErrorToast = false

    private static let deleteLogger = Logger(subsystem: "com.playfuel.ios", category: "delete")

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
        .sheet(isPresented: $showingCreateTournament) {
            TournamentCreateView()
                .environmentObject(appState)
        }
        .sheet(isPresented: $showProfile) {
            ProfileMenuSheet()
                .presentationDetents([.height(280), .medium])
                .presentationDragIndicator(.visible)
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
            // Trailing swipe → red Delete button (spec §D.1)
            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                Button(role: .destructive) {
                    tournamentToDelete = tournament
                    showDeleteConfirmation = true
                } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
        // Confirmation dialog drives off the outer state (AC#1)
        .confirmationDialog(
            "Delete tournament?",
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) {
                if let t = tournamentToDelete {
                    Task { await performDeleteTournament(t) }
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            if let t = tournamentToDelete {
                Text(deleteMessage(for: t))
            }
        }
        .overlay(alignment: .bottom) {
            if showDeleteErrorToast {
                deleteErrorToastView
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.easeInOut(duration: 0.25), value: showDeleteErrorToast)
            }
        }
    }

    // MARK: - Delete Helpers

    /// Returns the dynamic confirmation message for a tournament delete.
    /// Spec §D.2: prepend "This tournament is today. " when start_date == today.
    private func deleteMessage(for tournament: Tournament) -> String {
        let isTodayTournament: Bool
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        if let date = fmt.date(from: tournament.startDate) {
            isTodayTournament = Calendar.current.isDateInToday(date)
        } else {
            isTodayTournament = false
        }
        let todayPrefix = isTodayTournament ? "This tournament is today. " : ""

        let matchCount = appState.cachedPlanEnvelope(for: tournament.id)?.allPlans.count ?? 0
        if matchCount > 0 {
            let matchWord = matchCount == 1 ? "match" : "matches"
            let planWord  = matchCount == 1 ? "plan"  : "plans"
            return "\(todayPrefix)This will also delete \(matchCount) \(matchWord), \(matchCount) \(planWord), and any feedback. This can't be undone."
        } else {
            return "\(todayPrefix)This can't be undone."
        }
    }

    /// Executes the tournament delete: optimistic remove → API call → error recovery.
    /// Spec §D.4: optimistic UI + 3-second error toast on failure.
    private func performDeleteTournament(_ tournament: Tournament) async {
        let matchCount = appState.cachedPlanEnvelope(for: tournament.id)?.allPlans.count ?? 0
        // Optimistic: remove from list before API call fires
        let removed = appState.optimisticRemoveTournament(id: tournament.id)
        let success = await appState.deleteTournamentViaAPI(id: tournament.id)
        if success {
            // Telemetry — fire-and-forget Logger call (spec §E, no third-party)
            Self.deleteLogger.info("tournament_deleted tournament_id=\(tournament.id.uuidString) match_count=\(matchCount) plan_count=\(matchCount) had_feedback=false")
        } else {
            // Restore optimistic state + show inline toast for 3 s (spec §D.4)
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

    private var deleteErrorToastView: some View {
        Text("Couldn’t delete — please try again.")
            .font(.subheadline)
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.red.opacity(0.9), in: RoundedRectangle(cornerRadius: 10))
            .padding(.bottom, 24)
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
        // Parse the ISO "yyyy-MM-dd" wire format using POSIX locale (deterministic parse),
        // then format for display using Date.FormatStyle (locale-aware). A Mexican device
        // set to es-MX renders "15 abr. 2026"; a US device renders "Apr 15, 2026".
        func formatISO(_ iso: String) -> String {
            let fmt = DateFormatter()
            fmt.locale = Locale(identifier: "en_US_POSIX")
            fmt.dateFormat = "yyyy-MM-dd"
            guard let date = fmt.date(from: iso) else { return iso }
            return date.formatted(.dateTime.month(.abbreviated).day().year())
        }
        if let end = tournament.endDate {
            return "\(formatISO(tournament.startDate)) – \(formatISO(end))"
        }
        return formatISO(tournament.startDate)
    }
}

#Preview {
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

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    state.tournaments = .loaded(FakeData.tournaments)
    return NavigationStack {
        TournamentListView()
    }
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
