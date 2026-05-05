import SwiftUI

/// US-04 extension — In-app match creation.
/// Phase 5b: shipped to replace the "create via Supabase Console" workaround.
/// Phase 7 (Doubles): added match-type and doubles-format pickers.
///
/// On save: POSTs to /v1/tournaments/{tid}/matches via `Repository.createMatch`,
/// invalidates the plan cache, sets `currentPlanEnvelope` to `.idle` so the dashboard
/// shows a spinner, dismisses, then fires a background Task that calls
/// `appState.generatePlan(for:)`. The Task outlives the sheet — dashboard observes
/// the @Published change via @EnvironmentObject and updates when the plan arrives.
///
/// Presented as a sheet from `TournamentDashboardView`.
struct MatchCreateView: View {

    let tournamentId: UUID
    /// Passed from the parent so display_order defaults to existingMatchCount + 1.
    let existingMatchCount: Int
    /// Tournament draw size — drives the round picker options (migration 0016).
    /// Passed from TournamentDashboardView; defaults to 32 for legacy callers.
    let drawSize: Int
    /// Number of existing singles plans in the loaded envelope.
    /// Used to compute the next allowed round for the singles stream.
    /// round-progression-and-formats spec §J
    let existingSinglesCount: Int
    /// Number of existing doubles plans in the loaded envelope.
    /// Used to compute the next allowed round for the doubles stream.
    /// round-progression-and-formats spec §J
    let existingDoublesCount: Int
    /// Tournament date range — constrains both DatePickers so the user can only
    /// pick days that fall within the tournament window.
    let tournamentStartDate: Date
    let tournamentEndDate: Date

    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - Form state

    // scheduledStart is set in the custom init (see below) so it can clamp
    // to the tournament window when today falls outside the range.
    @State private var scheduledStart: Date

    // migration 0016: numeric round replaces free-text roundLabelText.
    // Initialized to drawSize (earliest round = most likely first entry).
    // Using @State with property-wrapper init syntax so drawSize is accessible.
    @State private var selectedRound: Int
    @State private var opponentLabelText: String = ""
    @State private var courtLabelText: String = ""

    // MARK: - Round progression (round-progression-and-formats spec §J)

    /// True when the round picker is in backfill mode (shows all valid rounds).
    /// In normal mode only the next allowed round is shown (locked / read-only).
    @State private var isBackfillMode: Bool = false

    // MARK: - Phase 7: Match type + doubles format

    /// Singles or doubles. Default: Singles.
    @State private var matchType: MatchType = .singles

    /// Doubles format. Only used (and shown) when matchType == .doubles. Default: Best of 3.
    @State private var doublesFormat: DoublesFormat = .bestOf3

    // MARK: - Init (needed to set selectedRound from drawSize)

    init(
        tournamentId: UUID,
        drawSize: Int = 32,
        existingMatchCount: Int,
        existingSinglesCount: Int = 0,
        existingDoublesCount: Int = 0,
        tournamentStartDate: Date,
        tournamentEndDate: Date
    ) {
        self.tournamentId = tournamentId
        self.drawSize = drawSize
        self.existingMatchCount = existingMatchCount
        self.existingSinglesCount = existingSinglesCount
        self.existingDoublesCount = existingDoublesCount
        self.tournamentStartDate = tournamentStartDate
        self.tournamentEndDate = tournamentEndDate
        // Default selectedRound to the next allowed round for the default type (singles).
        // Formula: drawSize / 2^existingSinglesCount, clamped to ≥2 (Final).
        var singlesDivisor = 1
        for _ in 0..<existingSinglesCount { singlesDivisor *= 2 }
        let defaultRound = max(drawSize / singlesDivisor, 2)
        _selectedRound = State(initialValue: defaultRound)
        // scheduledStart: today at 9 AM if today falls within the tournament window;
        // otherwise clamp to tournamentStartDate at 9 AM so the picker opens in-range.
        let cal = Calendar.current
        let todayStart = cal.startOfDay(for: Date())
        let tStart = cal.startOfDay(for: tournamentStartDate)
        let tEnd   = cal.startOfDay(for: tournamentEndDate)
        let baseDate = (todayStart >= tStart && todayStart <= tEnd) ? Date() : tournamentStartDate
        var comps = cal.dateComponents([.year, .month, .day], from: baseDate)
        comps.hour = 9; comps.minute = 0; comps.second = 0
        let defaultStart = cal.date(from: comps) ?? tournamentStartDate
        _scheduledStart = State(initialValue: defaultStart)
    }

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

    // MARK: - Date range for pickers

    /// Closed range spanning the full tournament: 00:00:00 on startDate through
    /// 23:59:59 on endDate (device local calendar). Applied to both DatePickers.
    private var dateRange: ClosedRange<Date> {
        let cal = Calendar.current
        let lower = cal.startOfDay(for: tournamentStartDate)
        let upper = cal.date(bySettingHour: 23, minute: 59, second: 59, of: tournamentEndDate)
            ?? cal.date(byAdding: .day, value: 1, to: lower)!
        return lower <= upper ? lower...upper : lower...lower
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Form {
                Section("Schedule") {
                    DatePicker(
                        "Match start",
                        selection: $scheduledStart,
                        in: dateRange,
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
                    header: Text("Labels"),
                    footer: Text("All optional. Displayed on the match card.")
                ) {
                    // round-progression-and-formats spec §J: constrained round picker.
                    // Normal mode: locked to the next allowed round (read-only label +
                    //   "Edit earlier round" backfill affordance).
                    // Backfill mode: full draw picker (user opted in explicitly).
                    if isBackfillMode {
                        Picker("Round", selection: $selectedRound) {
                            ForEach(RoundVocab.roundOptions(for: drawSize), id: \.self) { r in
                                Text(RoundVocab.label(for: r)).tag(r)
                            }
                        }
                        .pickerStyle(.menu)
                    } else {
                        HStack {
                            Text("Round")
                            Spacer()
                            Text(RoundVocab.label(for: nextAllowedRoundFor(matchType)))
                                .foregroundStyle(.secondary)
                        }
                        Button("Edit earlier round") {
                            // Ensure selectedRound is in sync before entering backfill.
                            selectedRound = nextAllowedRoundFor(matchType)
                            isBackfillMode = true
                        }
                        .font(.caption)
                        .foregroundStyle(Color.accentColor)
                    }

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
            // round-progression-and-formats spec §J: reset selectedRound to the
            // next allowed round for the newly-selected stream when not in backfill mode.
            .onChange(of: matchType) { _, newType in
                if !isBackfillMode {
                    selectedRound = nextAllowedRoundFor(newType)
                }
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
        let opponentLabel = trimmedOrNil(opponentLabelText)
        let courtLabel    = trimmedOrNil(courtLabelText)

        do {
            _ = try await appState.repository.createMatch(
                tournamentId: tournamentId,
                scheduledStart: scheduledStart,
                round: selectedRound,
                // roundLabel is intentionally nil — the API auto-derives it from `round`
                roundLabel: nil,
                opponentLabel: opponentLabel,
                courtLabel: courtLabel,
                displayOrder: existingMatchCount + 1,
                matchType: matchType,
                doublesFormat: matchType == .doubles ? doublesFormat : nil,
                opponentPlayerId: opponentPlayerId
            )
            // Invalidate the cached plan so the next `generatePlan(for:)` call
            // fetches a fresh plan that includes the new match.
            appState.invalidatePlanCache(for: tournamentId)
            // Show spinner immediately while the fresh plan loads.
            appState.currentPlanEnvelope = .idle
            dismiss()
            // Re-generate the plan with the new match included.
            //
            // WHY THIS IS NEEDED:
            // TournamentDashboardView uses `.task(id: tournament.id)` which only
            // re-fires when tournament.id changes. Since the id is stable across
            // match additions, dismissing MatchCreateView would leave the dashboard
            // stuck on `.idle` (spinner) forever — nobody re-triggers generatePlan.
            //
            // This Task outlives the sheet dismissal: it is NOT bound to the view
            // lifecycle (unlike .task modifier). AppState is global; the dashboard
            // observes @Published changes via @EnvironmentObject and updates when
            // the fresh plan arrives.
            let capturedTid = tournamentId
            Task { await appState.generatePlan(for: capturedTid) }
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? error.localizedDescription
            isSaving = false
        }
    }

    // MARK: - Round Progression Helpers

    /// Returns the next allowed round for the given match type.
    ///
    /// Formula: drawSize / 2^streamCount, clamped to ≥2 (the Final).
    ///   - First match in stream (count=0): drawSize (e.g. 32 for a 32-draw)
    ///   - Second match (count=1): drawSize / 2 (e.g. 16)
    ///   - etc.
    ///
    /// round-progression-and-formats spec §J
    private func nextAllowedRoundFor(_ type: MatchType) -> Int {
        let count = type == .singles ? existingSinglesCount : existingDoublesCount
        var divisor = 1
        for _ in 0..<count { divisor *= 2 }
        return max(drawSize / divisor, 2)
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
    let start = Calendar.current.startOfDay(for: Date())
    let end   = Calendar.current.date(byAdding: .day, value: 2, to: start) ?? start
    return MatchCreateView(
        tournamentId: UUID(uuidString: "11111111-0000-0000-0000-000000000001")!,
        drawSize: 64,
        existingMatchCount: 0,
        tournamentStartDate: start,
        tournamentEndDate: end
    )
    .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    let start = Calendar.current.startOfDay(for: Date())
    let end   = Calendar.current.date(byAdding: .day, value: 2, to: start) ?? start
    return MatchCreateView(
        tournamentId: UUID(uuidString: "11111111-0000-0000-0000-000000000001")!,
        drawSize: 64,
        existingMatchCount: 0,
        tournamentStartDate: start,
        tournamentEndDate: end
    )
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
