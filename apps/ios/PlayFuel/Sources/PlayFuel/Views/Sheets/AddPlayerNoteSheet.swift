import SwiftUI

/// Sheet for adding a new note about a scouted opponent player.
///
/// Per PLAYER_SCOUTING_V1.md §E.5:
///   - Source segmented picker (Heard / Watched / Played)
///   - TextEditor with 2000-char limit + live count
///   - Verbatim privacy guardrail text (§A.2) always visible
///
/// The `onSave` closure is called when Save is tapped; the parent is responsible
/// for the API call, and this sheet is responsible only for form state.
struct AddPlayerNoteSheet: View {

    let playerId: UUID
    let onSave: (PlayerNoteSource, String) async -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var source: PlayerNoteSource = .observed
    @State private var noteBody: String = ""
    @State private var isSaving = false
    @State private var errorMessage: String? = nil

    private let bodyLimit = 2000

    private var isSaveEnabled: Bool {
        !noteBody.trimmingCharacters(in: .whitespaces).isEmpty
            && noteBody.count <= bodyLimit
            && !isSaving
    }

    var body: some View {
        NavigationStack {
            Form {
                // MARK: Source picker
                Section {
                    Picker("Source", selection: $source) {
                        ForEach(PlayerNoteSource.allCases) { src in
                            Text(src.displayName).tag(src)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                } header: {
                    Text("Source")
                } footer: {
                    Text("Where did this observation come from?")
                }

                // MARK: Note body
                Section {
                    TextEditor(text: $noteBody)
                        .frame(minHeight: 120)
                        .onChange(of: noteBody) { _, new in
                            // Enforce hard cap at 2000 chars
                            if new.count > bodyLimit {
                                noteBody = String(new.prefix(bodyLimit))
                            }
                        }
                } header: {
                    Text("Note")
                } footer: {
                    HStack {
                        Spacer()
                        Text("\(self.noteBody.count) / \(bodyLimit)")
                            .font(.caption2)
                            .foregroundStyle(self.noteBody.count >= bodyLimit ? .red : .secondary)
                    }
                }

                // MARK: Privacy guardrail (§A.2 verbatim, always visible)
                Section {
                    Text("Notes are private to your account. Don't include personal contact info, photos, or anything not directly observable on court.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let error = errorMessage {
                    Section {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.red)
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.red)
                        }
                    }
                }
            }
            .navigationTitle("Add Note")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .disabled(isSaving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if isSaving {
                        ProgressView().controlSize(.small)
                    } else {
                        Button("Save") {
                            Task { await save() }
                        }
                        .disabled(!isSaveEnabled)
                    }
                }
            }
        }
    }

    // MARK: - Save

    private func save() async {
        guard isSaveEnabled else { return }
        isSaving = true
        errorMessage = nil
        let trimmedBody = noteBody.trimmingCharacters(in: .whitespaces)
        await onSave(source, trimmedBody)
        isSaving = false
        dismiss()
    }
}

// MARK: - Previews

#Preview {
    AddPlayerNoteSheet(playerId: UUID()) { _, _ in }
}

#Preview("Dark") {
    AddPlayerNoteSheet(playerId: UUID()) { _, _ in }
        .preferredColorScheme(.dark)
}
