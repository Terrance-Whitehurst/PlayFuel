import SwiftUI

/// Post-match write-up form — both create and edit modes.
///
/// Receives an optional `existingEval` for editing (pre-fills all fields).
/// On Save: calls `Repository.saveMatchEvaluation`, dismisses on success.
/// On Cancel: dismisses with no action, no confirmation needed (no destructive action
/// until the user explicitly taps Save).
///
/// POST_MATCH_EVAL_V1.md §E.3
/// Privacy guardrail (verbatim from §H.2):
///   "These notes will be added to your scouting log for this opponent."
struct PostMatchEvaluationForm: View {

    let matchId: UUID
    let existingEval: MatchEvaluation?
    var onSaved: ((MatchEvaluation) -> Void)? = nil

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - Form State

    @State private var selectedResult: MatchEvalResult = .lost
    @State private var scoreText: String = ""
    @State private var effortRating: Int = 0          // 0 = not set
    @State private var focusRating: Int = 0           // 0 = not set
    @State private var wentWellItems: [String] = [""]
    @State private var toImproveItems: [String] = [""]
    @State private var opponentObservations: String = ""
    @State private var keyMoments: String = ""

    // MARK: - Save State

    @State private var isSaving: Bool = false
    @State private var saveError: String? = nil

    // MARK: - Constants

    private let maxListItems = 5
    private let maxItemChars = 200
    private let maxTextChars = 500
    private let maxScoreChars = 80

    var body: some View {
        NavigationStack {
            Form {

                // MARK: Result (required)
                Section {
                    resultPicker
                } header: {
                    Text("Result")
                } footer: {
                    Text("Required — only field you must fill in.")
                        .font(.caption)
                }

                // MARK: Score (optional)
                Section("Score (optional)") {
                    TextField("e.g. 6-4, 3-6, 10-7", text: $scoreText)
                        .onChange(of: scoreText) { _, new in
                            if new.count > maxScoreChars {
                                scoreText = String(new.prefix(maxScoreChars))
                            }
                        }
                }

                // MARK: Ratings (optional)
                Section("Ratings (optional)") {
                    ratingRow(label: "Effort", binding: $effortRating,
                               hint: "1 = low, 5 = maximum")
                    ratingRow(label: "Focus", binding: $focusRating,
                               hint: "1 = distracted, 5 = locked in")
                }

                // MARK: What Went Well
                Section {
                    dynamicListEditor(items: $wentWellItems,
                                      placeholder: "e.g. First-serve percentage")
                } header: {
                    Text("What Went Well (optional)")
                } footer: {
                    Text("Up to 5 items.")
                        .font(.caption)
                }

                // MARK: What to Improve
                Section {
                    dynamicListEditor(items: $toImproveItems,
                                      placeholder: "e.g. Net approach timing")
                } header: {
                    Text("What to Improve (optional)")
                } footer: {
                    Text("Up to 5 items. Constructive framing — not failures, growth areas.")
                        .font(.caption)
                }

                // MARK: Opponent Observations
                Section {
                    ZStack(alignment: .topLeading) {
                        if opponentObservations.isEmpty {
                            Text("Opponent strengths, tendencies, patterns...")
                                .foregroundStyle(.secondary)
                                .padding(.top, 8)
                                .padding(.leading, 4)
                                .allowsHitTesting(false)
                        }
                        TextEditor(text: $opponentObservations)
                            .frame(minHeight: 80)
                            .onChange(of: opponentObservations) { _, new in
                                if new.count > maxTextChars {
                                    opponentObservations = String(new.prefix(maxTextChars))
                                }
                            }
                    }
                    charCount(current: opponentObservations.count, max: maxTextChars)
                    // Verbatim privacy guardrail — POST_MATCH_EVAL_V1.md §H.2
                    Text("These notes will be added to your scouting log for this opponent.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Opponent Observations (optional)")
                }

                // MARK: Key Moments
                Section {
                    ZStack(alignment: .topLeading) {
                        if keyMoments.isEmpty {
                            Text("e.g. Saved a break point at 5-4 in the second set")
                                .foregroundStyle(.secondary)
                                .padding(.top, 8)
                                .padding(.leading, 4)
                                .allowsHitTesting(false)
                        }
                        TextEditor(text: $keyMoments)
                            .frame(minHeight: 80)
                            .onChange(of: keyMoments) { _, new in
                                if new.count > maxTextChars {
                                    keyMoments = String(new.prefix(maxTextChars))
                                }
                            }
                    }
                    charCount(current: keyMoments.count, max: maxTextChars)
                } header: {
                    Text("Key Moments (optional)")
                }

                // MARK: Save Error
                if let err = saveError {
                    Section {
                        Text(err)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
            }
            .navigationTitle(existingEval == nil ? "Add Write-Up" : "Edit Write-Up")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        Task { await save() }
                    }
                    .disabled(isSaving)
                    .fontWeight(.semibold)
                }
            }
            .onAppear { prefill() }
        }
    }

    // MARK: - Result Picker

    private var resultPicker: some View {
        Picker("Result", selection: $selectedResult) {
            ForEach(MatchEvalResult.allCases) { r in
                Text(r.displayName).tag(r)
            }
        }
        .pickerStyle(.segmented)
        .listRowInsets(EdgeInsets(top: 8, leading: 0, bottom: 8, trailing: 0))
        .listRowBackground(Color.clear)
    }

    // MARK: - Rating Row

    private func ratingRow(label: String, binding: Binding<Int>, hint: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.subheadline)
            HStack(spacing: 8) {
                // "None" option
                Button {
                    binding.wrappedValue = 0
                } label: {
                    Text("None")
                        .font(.caption)
                        .foregroundStyle(binding.wrappedValue == 0 ? Color.accentColor : .secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .overlay(
                            Capsule().stroke(
                                binding.wrappedValue == 0 ? Color.accentColor : Color(.systemGray4),
                                lineWidth: 1
                            )
                        )
                }
                .buttonStyle(.plain)

                ForEach(1...5, id: \.self) { i in
                    Button {
                        binding.wrappedValue = i
                    } label: {
                        Image(systemName: i <= binding.wrappedValue ? "circle.fill" : "circle")
                            .font(.title3)
                            .foregroundStyle(i <= binding.wrappedValue ? Color.accentColor : Color(.systemGray4))
                    }
                    .buttonStyle(.plain)
                }

                Spacer()
            }
            Text(hint)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    // MARK: - Dynamic List Editor

    @ViewBuilder
    private func dynamicListEditor(items: Binding<[String]>, placeholder: String) -> some View {
        ForEach(items.wrappedValue.indices, id: \.self) { index in
            HStack {
                TextField(placeholder, text: items[index])
                    .onChange(of: items.wrappedValue[index]) { _, new in
                        if new.count > maxItemChars {
                            items.wrappedValue[index] = String(new.prefix(maxItemChars))
                        }
                    }
                if items.wrappedValue.count > 1 {
                    Button {
                        items.wrappedValue.remove(at: index)
                    } label: {
                        Image(systemName: "minus.circle.fill")
                            .foregroundStyle(.red)
                    }
                    .buttonStyle(.plain)
                }
            }
        }

        if items.wrappedValue.count < maxListItems {
            Button {
                items.wrappedValue.append("")
            } label: {
                Label("Add another", systemImage: "plus.circle")
                    .font(.subheadline)
                    .foregroundStyle(Color.accentColor)
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Char Count Helper

    private func charCount(current: Int, max: Int) -> some View {
        HStack {
            Spacer()
            Text("\(current) / \(max)")
                .font(.caption2)
                .foregroundStyle(current >= max ? .orange : .secondary)
        }
    }

    // MARK: - Prefill

    private func prefill() {
        guard let eval = existingEval else { return }
        selectedResult = eval.result
        scoreText = eval.scoreText ?? ""
        effortRating = eval.effortRating ?? 0
        focusRating = eval.focusRating ?? 0
        wentWellItems = eval.wentWell.isEmpty ? [""] : eval.wentWell
        toImproveItems = eval.toImprove.isEmpty ? [""] : eval.toImprove
        opponentObservations = eval.opponentObservations ?? ""
        keyMoments = eval.keyMoments ?? ""
    }

    // MARK: - Save

    private func save() async {
        isSaving = true
        saveError = nil

        // Clean lists: filter empty strings, trim whitespace
        let cleanWentWell = wentWellItems.map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        let cleanToImprove = toImproveItems.map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }

        let request = MatchEvaluationCreateRequest(
            result: selectedResult.rawValue,
            scoreText: scoreText.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            effortRating: effortRating > 0 ? effortRating : nil,
            focusRating: focusRating > 0 ? focusRating : nil,
            wentWell: cleanWentWell,
            toImprove: cleanToImprove,
            opponentObservations: opponentObservations.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            keyMoments: keyMoments.trimmingCharacters(in: .whitespaces).nilIfEmpty
        )

        do {
            let saved = try await appState.repository.saveMatchEvaluation(
                matchId: matchId,
                request: request
            )
            onSaved?(saved)
            dismiss()
        } catch {
            saveError = "Save failed — please try again. (\(error.localizedDescription))"
        }

        isSaving = false
    }
}

// MARK: - String Helper

private extension String {
    /// Returns nil when the string is empty, self otherwise.
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    PostMatchEvaluationForm(
        matchId: UUID(uuidString: "AAAA0000-0000-0000-0000-000000000001")!,
        existingEval: nil
    )
    .environmentObject(state)
}
