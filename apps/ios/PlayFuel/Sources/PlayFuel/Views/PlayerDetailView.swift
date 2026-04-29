import SwiftUI

/// Detailed view of a scouted player — shows metadata + running notes log.
/// Pushed onto the NavigationStack from PlayerListView.
struct PlayerDetailView: View {

    let player: Player

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var notes: [PlayerNote] = []
    @State private var isLoadingNotes = false
    @State private var errorMessage: String? = nil
    @State private var showAddNote = false
    @State private var deletingNote: PlayerNote? = nil
    @State private var showDeleteNoteConfirm = false

    var body: some View {
        List {
            // MARK: Header Section
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(player.displayName)
                        .font(.title2.bold())
                    if let subtitle = player.locationSubtitle {
                        Text(subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    HStack(spacing: 8) {
                        Label("\(player.noteCount) \(player.noteCount == 1 ? "note" : "notes")",
                              systemImage: "note.text")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if let summary = player.notesSummary, !summary.isEmpty {
                            Text("·")
                                .foregroundStyle(.tertiary)
                            Text(summary)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
                .padding(.vertical, 4)
            }

            // MARK: Notes Section
            Section {
                if isLoadingNotes && notes.isEmpty {
                    HStack {
                        Spacer()
                        ProgressView("Loading notes…")
                        Spacer()
                    }
                    .padding()
                } else if notes.isEmpty {
                    Text("No notes yet — tap + to add observations.")
                        .font(.subheadline)
                        .foregroundStyle(.tertiary)
                        .italic()
                        .padding(.vertical, 4)
                } else {
                    ForEach(notes) { note in
                        NoteRowView(note: note)
                            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                Button(role: .destructive) {
                                    deletingNote = note
                                    showDeleteNoteConfirm = true
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                    }
                }
            } header: {
                HStack {
                    Text("Notes")
                    Spacer()
                    Button {
                        showAddNote = true
                    } label: {
                        Label("Add Note", systemImage: "plus")
                            .font(.caption.weight(.semibold))
                    }
                }
            }

            // MARK: Linked Matches (DRAFT — post-MVP per OQ-SCOUT-UX-1)
            // Section {
            //     Text("Coming soon — matches where this player was the opponent.")
            //         .font(.caption)
            //         .foregroundStyle(.tertiary)
            // } header: {
            //     Text("Linked Matches (Coming Soon)")
            // }

            if let error = errorMessage {
                Section {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.red)
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                    Button("Retry") {
                        Task { await loadNotes() }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(player.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadNotes()
        }
        .sheet(isPresented: $showAddNote, onDismiss: {
            Task { await loadNotes() }
        }) {
            AddPlayerNoteSheet(playerId: player.id) { source, body in
                await addNote(source: source, body: body)
            }
        }
        .alert("Delete Note?", isPresented: $showDeleteNoteConfirm, presenting: deletingNote) { note in
            Button("Delete", role: .destructive) {
                Task { await deleteNote(note) }
            }
            Button("Cancel", role: .cancel) {}
        } message: { _ in
            Text("This note will be permanently deleted.")
        }
    }

    // MARK: - Actions

    private func loadNotes() async {
        isLoadingNotes = true
        errorMessage = nil
        do {
            notes = try await appState.repository.listPlayerNotes(playerId: player.id)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoadingNotes = false
    }

    private func addNote(source: PlayerNoteSource, body: String) async {
        _ = try? await appState.repository.addPlayerNote(
            playerId: player.id,
            source: source,
            body: body
        )
    }

    private func deleteNote(_ note: PlayerNote) async {
        try? await appState.repository.deletePlayerNote(playerId: player.id, noteId: note.id)
        notes.removeAll { $0.id == note.id }
    }
}

// MARK: - Note Row

private struct NoteRowView: View {
    let note: PlayerNote

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                sourcePill
                Text(note.relativeDate)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Text(note.body)
                .font(.subheadline)
                .foregroundStyle(.primary)
        }
        .padding(.vertical, 2)
    }

    private var sourcePill: some View {
        Text(note.source.displayName)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(pillColor.opacity(0.15))
            .foregroundStyle(pillColor)
            .clipShape(Capsule())
    }

    private var pillColor: Color {
        switch note.source {
        case .secondhand: return .blue
        case .observed:   return .orange
        case .post_match: return .green
        }
    }
}

// MARK: - Previews

#Preview {
    let auth = AuthService()
    let repo = Repository(api: APIClient(authService: auth))
    let state = AppState(repository: repo, authService: auth)
    return NavigationStack {
        PlayerDetailView(player: FakeData.fakePlayers[0])
    }
    .environmentObject(state)
}

#Preview("Dark") {
    let auth = AuthService()
    let repo = Repository(api: APIClient(authService: auth))
    let state = AppState(repository: repo, authService: auth)
    return NavigationStack {
        PlayerDetailView(player: FakeData.fakePlayers[0])
    }
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
