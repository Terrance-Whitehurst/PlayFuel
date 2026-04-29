import SwiftUI

/// US-PLAYER-1 / US-PLAYER-2 - parent's roster of scouted opponents.
///
/// Presented as a full-screen sheet from `ProfileMenuSheet` (3rd row "Players").
/// Wraps its own `NavigationStack` so pushes work inside the sheet.
struct PlayerListView: View {

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var players: [Player] = []
    @State private var isLoading = false
    @State private var errorMessage: String? = nil
    @State private var showAddPlayer = false
    @State private var editingPlayer: Player? = nil
    @State private var deletingPlayer: Player? = nil
    @State private var showDeleteConfirm = false

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && players.isEmpty {
                    ProgressView("Loading players...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = errorMessage {
                    errorView(message: error)
                } else if players.isEmpty {
                    emptyStateView
                } else {
                    playerList
                }
            }
            .navigationTitle("Players")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showAddPlayer = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Add player")
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                await loadPlayers()
            }
            .sheet(isPresented: $showAddPlayer, onDismiss: {
                Task { await loadPlayers() }
            }) {
                AddPlayerSheet(existingPlayer: nil) { name, club, city in
                    await createPlayer(name: name, club: club, city: city)
                }
            }
            .sheet(item: $editingPlayer, onDismiss: {
                Task { await loadPlayers() }
            }) { player in
                AddPlayerSheet(existingPlayer: player) { name, club, city in
                    await updatePlayer(id: player.id, name: name, club: club, city: city)
                }
            }
            .alert("Delete Player?", isPresented: $showDeleteConfirm, presenting: deletingPlayer) { player in
                Button("Delete", role: .destructive) {
                    Task { await deletePlayer(player) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { player in
                Text("This deletes '\(player.displayName)' and all \(player.noteCount) note\(player.noteCount == 1 ? "" : "s"). This cannot be undone.")
            }
        }
    }

    // MARK: - Subviews

    private var playerList: some View {
        List {
            ForEach(players) { player in
                NavigationLink {
                    PlayerDetailView(player: player)
                } label: {
                    PlayerRowView(player: player)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        deletingPlayer = player
                        showDeleteConfirm = true
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }

                    Button {
                        editingPlayer = player
                    } label: {
                        Label("Edit", systemImage: "pencil")
                    }
                    .tint(.blue)
                }
            }
        }
        .listStyle(.insetGrouped)
        .refreshable {
            await loadPlayers()
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: "person.2.fill")
                .font(.system(size: 52))
                .foregroundStyle(.tertiary)
            Text("No Players Yet")
                .font(.headline)
            Text("Add a player to start tracking opponents before and after matches.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Button("Add First Player") {
                showAddPlayer = true
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorView(message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
                .font(.title2)
            Text(message)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
            Button("Retry") {
                Task { await loadPlayers() }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Actions

    private func loadPlayers() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        do {
            players = try await appState.repository.listPlayers()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    private func createPlayer(name: String, club: String, city: String) async {
        _ = try? await appState.repository.createPlayer(
            displayName: name,
            club: club.isEmpty ? nil : club,
            city: city.isEmpty ? nil : city
        )
    }

    private func updatePlayer(id: UUID, name: String, club: String, city: String) async {
        _ = try? await appState.repository.updatePlayer(
            id: id,
            displayName: name,
            club: club.isEmpty ? nil : club,
            city: city.isEmpty ? nil : city
        )
    }

    private func deletePlayer(_ player: Player) async {
        try? await appState.repository.deletePlayer(id: player.id)
        players.removeAll { $0.id == player.id }
    }
}

// MARK: - Player Row

private struct PlayerRowView: View {
    let player: Player

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(player.displayName)
                .font(.body)
                .foregroundStyle(.primary)
            if let subtitle = player.locationSubtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Previews

#Preview {
    let auth = AuthService()
    let repo = Repository(api: APIClient(authService: auth))
    let state = AppState(repository: repo, authService: auth)
    return PlayerListView()
        .environmentObject(state)
}

#Preview("Dark") {
    let auth = AuthService()
    let repo = Repository(api: APIClient(authService: auth))
    let state = AppState(repository: repo, authService: auth)
    return PlayerListView()
        .environmentObject(state)
        .preferredColorScheme(.dark)
}
