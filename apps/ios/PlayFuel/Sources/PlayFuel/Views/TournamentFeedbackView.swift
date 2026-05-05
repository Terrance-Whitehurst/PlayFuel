import SwiftUI

/// Post-tournament plan feedback view — both create and edit modes.
///
/// Presented as a sheet from TournamentDashboardView when all matches
/// are in the past (envelope.allMatchesPast == true).
///
/// On appear: loads existing feedback via Repository.getFeedback.
///   - 200 found  → pre-populates all fields (edit mode, toolbar shows "Update")
///   - 404 / none → empty form (create mode, toolbar shows "Submit")
///
/// On save: POSTs via Repository.submitFeedback (UPSERT semantics).
///   - 201 / 200  → dismiss sheet
///   - error      → inline error message; form stays open
///
/// phase7-feedback-spec.md §E.2 + §E.3
struct TournamentFeedbackView: View {

    let tournament: Tournament

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - Load / Save State

    @State private var isLoading: Bool = true
    @State private var isSubmitting: Bool = false
    @State private var submitError: String? = nil
    @State private var existingFeedback: TournamentFeedback? = nil

    // MARK: - Form State

    @State private var selectedRating: Int = 0           // 0 = not set; 1–5 = selected
    @State private var selectedWorked: Set<String> = []
    @State private var selectedDidnt: Set<String> = []
    @State private var freeText: String = ""

    // MARK: - Constants

    private let maxTextChars = 500

    // MARK: - Computed

    /// Submit enabled when at least one field has a value.
    private var canSubmit: Bool {
        selectedRating > 0
            || !selectedWorked.isEmpty
            || !selectedDidnt.isEmpty
            || !freeText.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var isEditMode: Bool { existingFeedback != nil }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView("Loading…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    feedbackForm
                }
            }
            .navigationTitle("Rate This Tournament")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(isEditMode ? "Update" : "Submit") {
                        Task { await submit() }
                    }
                    .disabled(!canSubmit || isSubmitting)
                    .fontWeight(.semibold)
                }
            }
            .task { await loadExistingFeedback() }
        }
    }

    // MARK: - Form

    private var feedbackForm: some View {
        Form {

            // MARK: Overall Rating (optional)
            Section {
                starRatingRow
            } header: {
                Text("Overall Rating (optional)")
            } footer: {
                Text("Tap a star to set; tap again to clear.")
                    .font(.caption)
            }

            // MARK: What Worked?
            Section {
                chipGrid(tokens: FEEDBACK_CHIP_TOKENS, selection: $selectedWorked)
            } header: {
                Text("What Worked?")
            } footer: {
                Text("Select all that applied this tournament.")
                    .font(.caption)
            }

            // MARK: What Didn't Work?
            Section {
                chipGrid(tokens: FEEDBACK_CHIP_TOKENS, selection: $selectedDidnt)
            } header: {
                Text("What Didn't Work?")
            } footer: {
                Text("Select all that could improve next time.")
                    .font(.caption)
            }

            // MARK: Anything Else? (optional)
            Section {
                ZStack(alignment: .topLeading) {
                    if freeText.isEmpty {
                        Text("Optional \u{2014} any other feedback for next time?")
                            .foregroundStyle(.secondary)
                            .padding(.top, 8)
                            .padding(.leading, 4)
                            .allowsHitTesting(false)
                    }
                    TextEditor(text: $freeText)
                        .frame(minHeight: 80)
                        .onChange(of: freeText) { _, new in
                            if new.count > maxTextChars {
                                freeText = String(new.prefix(maxTextChars))
                            }
                        }
                }
                charCountRow(current: freeText.count, max: maxTextChars)
            } header: {
                Text("Anything Else? (optional)")
            }

            // MARK: Error Banner
            if let err = submitError {
                Section {
                    Text(err)
                        .foregroundStyle(.red)
                        .font(.caption)
                }
            }
        }
    }

    // MARK: - Star Rating

    private var starRatingRow: some View {
        HStack(spacing: 14) {
            ForEach(1...5, id: \.self) { star in
                Button {
                    // Tap same star a second time → clear (toggle off)
                    selectedRating = (selectedRating == star) ? 0 : star
                } label: {
                    Image(systemName: star <= selectedRating ? "star.fill" : "star")
                        .font(.title)
                        .foregroundStyle(star <= selectedRating ? Color.yellow : Color(.systemGray3))
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.vertical, 6)
    }

    // MARK: - Chip Grid

    private func chipGrid(tokens: [String], selection: Binding<Set<String>>) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 110))], spacing: 8) {
            ForEach(tokens, id: \.self) { token in
                Button {
                    if selection.wrappedValue.contains(token) {
                        selection.wrappedValue.remove(token)
                    } else {
                        selection.wrappedValue.insert(token)
                    }
                } label: {
                    Text(FEEDBACK_CHIP_LABELS[token] ?? token)
                        .font(.caption)
                        .fontWeight(selection.wrappedValue.contains(token) ? .semibold : .regular)
                        .foregroundStyle(
                            selection.wrappedValue.contains(token) ? Color.white : Color.primary
                        )
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity)
                        .background(
                            selection.wrappedValue.contains(token)
                                ? Color.accentColor
                                : Color(.systemGray5)
                        )
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
        .listRowInsets(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
        .listRowBackground(Color.clear)
    }

    // MARK: - Char Count Helper

    private func charCountRow(current: Int, max: Int) -> some View {
        HStack {
            Spacer()
            Text("\(current) / \(max)")
                .font(.caption2)
                .foregroundStyle(current >= max ? .orange : .secondary)
        }
    }

    // MARK: - Load Existing Feedback

    private func loadExistingFeedback() async {
        isLoading = true
        do {
            let existing = try await appState.repository.getFeedback(tournamentId: tournament.id)
            if let existing {
                existingFeedback = existing
                selectedRating = existing.overallRating ?? 0
                selectedWorked = Set(existing.whatWorked)
                selectedDidnt  = Set(existing.whatDidntWork)
                freeText       = existing.freeText ?? ""
            }
        } catch {
            // 404 (no prior feedback) is handled as nil by Repository.
            // Other errors are non-fatal — start with an empty form.
        }
        isLoading = false
    }

    // MARK: - Submit

    private func submit() async {
        isSubmitting = true
        submitError  = nil

        let req = TournamentFeedbackCreateRequest(
            overallRating: selectedRating > 0 ? selectedRating : nil,
            whatWorked:    Array(selectedWorked),
            whatDidntWork: Array(selectedDidnt),
            freeText:      freeText.trimmingCharacters(in: .whitespaces).nilIfEmpty
        )

        do {
            _ = try await appState.repository.submitFeedback(
                tournamentId: tournament.id,
                request: req
            )
            dismiss()
        } catch {
            submitError = "Could not save feedback \u{2014} please try again."
        }

        isSubmitting = false
    }
}

// MARK: - String Helper

private extension String {
    /// Returns nil when the string is empty, self otherwise.
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

// MARK: - Previews

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return TournamentFeedbackView(tournament: FakeData.dallasTournament)
        .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return TournamentFeedbackView(tournament: FakeData.dallasTournament)
        .environmentObject(state)
        .preferredColorScheme(.dark)
}
