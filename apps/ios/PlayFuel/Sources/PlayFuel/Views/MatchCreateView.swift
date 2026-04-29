import SwiftUI

/// US-04 extension — In-app match creation.
/// Phase 5b: shipped to replace the "create via Supabase Console" workaround.
/// Phase 7 (Doubles): added match-type and doubles-format pickers; duration labels
/// now reflect the selected format's short/normal/long values (DOUBLES_SPEC_V1.md §E.2).
///
/// On save: POSTs to /v1/tournaments/{tid}/matches via `Repository.createMatch`,
/// resets `appState.currentPlanEnvelope` to `.idle` (forces re-generation with the new match),
/// then dismisses.
///
/// Presented as a sheet from `TournamentDashboardView`.
struct MatchCreateView: View {

    let tournamentId: UUID
    /// Passed from the parent so display_order defaults to existingMatchCount + 1.
    let existingMatchCount: Int

    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - Form state

    @State private var scheduledStart: Date = {
        // Default to 9:00 AM today in the device's local calendar.
        var comps = Calendar.current.dateComponents([.year, .month, .day], from: Date())
        comps.hour = 9
        comps.minute = 0
        comps.second = 0
        return Calendar.current.date(from: comps) ?? Date()
    }()

    /// 0 = Short, 1 = Normal, 2 = Long. Default: Normal.
    /// Values reflect the selected (matchType, doublesFormat) combo from the §B table.
    @State private var durationIndex: Int = 1

    @State private var roundLabelText: String = ""
    @State private var opponentLabelText: String = ""
    @State private var courtLabelText: String = ""

    @State private var hasNextMatch: Bool = false
    @State private var nextMatchTime: Date = Date()

    // MARK: - Phase 7: Match type + doubles format

    /// Singles or doubles. Default: Singles.
    @State private var matchType: MatchType = .singles

    /// Doubles format. Only used (and shown) when matchType == .doubles. Default: Best of 3.
    @State private var doublesFormat: DoublesFormat = .bestOf3

    // MARK: - Player scouting state

    /// FK to the selected opponent in the player roster (nil = no player linked)
    @State private var opponentPlayerId: UUID? = nil
    /// Cached roster loaded on appear for the picker
    @State private var availablePlayers: [Player] = []
    @State private var showPlayerSearch: Bool = false
    @State private var showAddPlayerInline: Bool = false
    @State private var playerSearchText: String = ""

    // MARK: - Async state

    @State private var isSaving: Bool = false
    @State private var errorMessage: String? = nil

    // MARK: - Computed duration options
    //
    // Returns the correct short/normal/long minute values for the current
    // (matchType, doublesFormat) selection, per DOUBLES_SPEC_V1.md §B.1.
    //   singles:              75 / 120 / 180 (RULES_CONSTANTS_V1 §A.1 — frozen)
    //   doubles best_of_3:    60 /  90 / 135 [DRAFT — OQ-DBL-1]
    //   doubles pro_set_8:    45 /  70 / 100 [DRAFT — OQ-DBL-1]
    private var durationOptions: [(label: String, minutes: Int)] {
        let values: [Int]
        switch (matchType, doublesFormat) {
        case (.doubles, .proSet8):  values = [45, 70, 100]
        case (.doubles, .bestOf3):  values = [60, 90, 135]
        default:                    values = [75, 120, 180]  // .singles
        }
        let names = ["Short", "Normal", "Long"]
        return zip(names, values).map { name, min in
            (label: "\(name) (\(DurationFormatting.friendly(minutes: min)))", minutes: min)
        }
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Form {
                Section("Schedule") {
                    DatePicker(
                        "Match start",
                        selection: $scheduledStart,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                }

                // Phase 7 — Match type picker (always visible, default Singles)
                Section(header: Text("Match Type")) {
                    Picker("Type", selection: $matchType) {
                        ForEach(MatchType.allCases, id: \.self) { type in
                            Text(type.displayName).tag(type)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }

                // Phase 7 — Doubles format picker (only visible when Doubles is selected)
                if matchType == .doubles {
                    Section(header: Text("Doubles Format")) {
                        Picker("Format", selection: $doublesFormat) {
                            ForEach(DoublesFormat.allCases, id: \.self) { format in
                                Text(format.displayName).tag(format)
                            }
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                    }
                }

                Section(
                    header: Text("Estimated Duration"),
                    footer: Text("Used by the rules engine to calculate gap and food window.")
                ) {
                    Picker("Duration", selection: $durationIndex) {
                        ForEach(durationOptions.indices, id: \.self) { i in
                            Text(durationOptions[i].label).tag(i)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }

                Section(
                    header: Text("Labels"),
                    footer: Text("All optional. Displayed on the match card.")
                ) {
                    TextField("Round (e.g. R16, QF, SF, F)", text: $roundLabelText)
                        .autocorrectionDisabled()

                    Button {
                        showPlayerSearch = true
                    } label: {
                        HStack {
                            Text(opponentLabelText.isEmpty ? "Opponent (optional)" : opponentLabelText)
                                .foregroundStyle(opponentLabelText.isEmpty ? .tertiary : .primary)
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.tertiary)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    TextField("Court (e.g. Court 7)", text: $courtLabelText)
                        .autocorrectionDisabled()
                }

                Section(
                    header: Text("Next Match"),
                    footer: Text("If you know your next match time, the rules engine uses it to compute the gap.")
                ) {
                    Toggle("I have a next match", isOn: $hasNextMatch.animation())

                    if hasNextMatch {
                        DatePicker(
                            "Next match time",
                            selection: $nextMatchTime,
                            displayedComponents: [.date, .hourAndMinute]
                        )
                    }
                }

                if let error = errorMessage {
                    Section {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.red)
                            Text(error)
                                .foregroundStyle(.red)
                                .font(.caption)
                        }
                        Button("Retry") {
                            Task { await save() }
                        }
                    }
                }
            }
            .navigationTitle("Add Match")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .disabled(isSaving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if isSaving {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Button("Save") {
                            Task { await save() }
                        }
                    }
                }
            }
            // Keep nextMatchTime pre-filled at scheduledStart + 4 hours when start changes.
            .onChange(of: scheduledStart) { _, newStart in
                nextMatchTime = newStart.addingTimeInterval(4 * 3600)
            }
            // Phase 7: reset to Normal (index 1) when match type or doubles format changes
            // so the user always sees a sensible default for the new duration table.
            .onChange(of: matchType) { _, _ in
                durationIndex = 1
            }
            .onChange(of: doublesFormat) { _, _ in
                durationIndex = 1
            }
            .onAppear {
                nextMatchTime = scheduledStart.addingTimeInterval(4 * 3600)
            }
            // Player Scouting — present player search picker
            .sheet(isPresented: $showPlayerSearch, onDismiss: {
                playerSearchText = ""
            }) {
                PlayerSearchSheet(
                    players: availablePlayers,
                    searchText: $playerSearchText
                ) { player in
                    opponentPlayerId  = player.id
                    opponentLabelText = player.displayName
                    showPlayerSearch  = false
                } onAddNew: { typedName in
                    opponentLabelText = typedName
                    opponentPlayerId  = nil
                    showPlayerSearch  = false
                }
            }
            .sheet(isPresented: $showAddPlayerInline, onDismiss: {
                // Re-fetch players after inline creation
                Task {
                    availablePlayers = (try? await appState.repository.listPlayers()) ?? []
                }
            }) {
                AddPlayerSheet(existingPlayer: nil) { name, _, _ in
                    // Create inline and select
                    if let created = try? await appState.repository.createPlayer(displayName: name) {
                        opponentPlayerId  = created.id
                        opponentLabelText = created.displayName
                        availablePlayers.insert(created, at: 0)
                    }
                }
            }
            .task {
                // Pre-load player roster so picker is ready
                if availablePlayers.isEmpty {
                    availablePlayers = (try? await appState.repository.listPlayers()) ?? []
                }
            }
        }
    }

    // MARK: - Save

    private func save() async {
        guard !isSaving else { return }
        isSaving = true
        errorMessage = nil

        // Trim optional label fields; send nil (not empty string) when blank.
        let roundLabel    = trimmedOrNil(roundLabelText)
        let opponentLabel = trimmedOrNil(opponentLabelText)
        let courtLabel    = trimmedOrNil(courtLabelText)
        let nextMatch     = hasNextMatch ? nextMatchTime : nil

        do {
            _ = try await appState.repository.createMatch(
                tournamentId: tournamentId,
                scheduledStart: scheduledStart,
                estimatedDurationMinutes: durationOptions[durationIndex].minutes,
                roundLabel: roundLabel,
                opponentLabel: opponentLabel,
                courtLabel: courtLabel,
                estimatedNextMatchTime: nextMatch,
                displayOrder: existingMatchCount + 1,
                matchType: matchType,
                doublesFormat: matchType == .doubles ? doublesFormat : nil,
                opponentPlayerId: opponentPlayerId
            )
            // Reset plan envelope to idle so the dashboard prompts re-generation
            // with the new match (Phase 7: envelope replaces single Plan).
            appState.currentPlanEnvelope = .idle
            dismiss()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? error.localizedDescription
            isSaving = false
        }
    }

    // MARK: - Helpers

    private func trimmedOrNil(_ text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? nil : t
    }
}

// MARK: - Player Search Sheet
//
// Inline search-and-select for opponent players when creating a match.
// Displayed as a .medium sheet from MatchCreateView via $showPlayerSearch.
// Per PLAYER_SCOUTING_V1.md §E.4.

private struct PlayerSearchSheet: View {
    let players: [Player]
    @Binding var searchText: String
    let onSelect: (Player) -> Void
    let onAddNew: (String) -> Void

    @Environment(\.dismiss) private var dismiss

    private var filtered: [Player] {
        guard !searchText.trimmingCharacters(in: .whitespaces).isEmpty else { return players }
        let q = searchText.lowercased()
        return players.filter { $0.displayName.lowercased().contains(q) }
    }

    private var showAddNewRow: Bool {
        let t = searchText.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return false }
        return !players.contains { $0.displayName.lowercased() == t.lowercased() }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(filtered) { player in
                    Button {
                        onSelect(player)
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(player.displayName)
                                    .foregroundStyle(.primary)
                                if let sub = player.locationSubtitle {
                                    Text(sub)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                }

                if showAddNewRow {
                    Button {
                        onAddNew(searchText.trimmingCharacters(in: .whitespaces))
                    } label: {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .foregroundStyle(Color.accentColor)
                            Text("Add \"\(searchText.trimmingCharacters(in: .whitespaces))\" as new player")
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .listStyle(.insetGrouped)
            .overlay {
                if filtered.isEmpty && !showAddNewRow {
                    Text("No players found.")
                        .foregroundStyle(.secondary)
                        .font(.subheadline)
                }
            }
            .searchable(text: $searchText, placement: .navigationBarDrawer(displayMode: .always))
            .navigationTitle("Select Opponent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}

// MARK: - Preview

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return MatchCreateView(
        tournamentId: UUID(uuidString: "11111111-0000-0000-0000-000000000001")!,
        existingMatchCount: 0
    )
    .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return MatchCreateView(
        tournamentId: UUID(uuidString: "11111111-0000-0000-0000-000000000001")!,
        existingMatchCount: 0
    )
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
