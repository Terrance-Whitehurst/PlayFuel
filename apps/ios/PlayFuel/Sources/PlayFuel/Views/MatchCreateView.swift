import SwiftUI

/// US-04 extension — In-app match creation.
/// Phase 5b: shipped to replace the "create via Supabase Console" workaround.
///
/// On save: POSTs to /v1/tournaments/{tid}/matches via `Repository.createMatch`,
/// resets `appState.currentPlan` to `.idle` (forces re-generation with the new match),
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

    /// 0 = Short (75 min), 1 = Normal (120 min), 2 = Long (180 min). Default: Normal.
    @State private var durationIndex: Int = 1

    @State private var roundLabelText: String = ""
    @State private var opponentLabelText: String = ""
    @State private var courtLabelText: String = ""

    @State private var hasNextMatch: Bool = false
    @State private var nextMatchTime: Date = Date()

    // MARK: - Async state

    @State private var isSaving: Bool = false
    @State private var errorMessage: String? = nil

    // MARK: - Constants

    private let durationOptions: [(label: String, minutes: Int)] = [
        ("Short (75)",   75),
        ("Normal (120)", 120),
        ("Long (180)",   180)
    ]

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

                    TextField("Opponent (e.g. Smith)", text: $opponentLabelText)
                        .autocorrectionDisabled()

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
            .onAppear {
                nextMatchTime = scheduledStart.addingTimeInterval(4 * 3600)
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
                displayOrder: existingMatchCount + 1
            )
            // Reset plan to idle so the dashboard prompts re-generation with the new match.
            appState.currentPlan = .idle
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
