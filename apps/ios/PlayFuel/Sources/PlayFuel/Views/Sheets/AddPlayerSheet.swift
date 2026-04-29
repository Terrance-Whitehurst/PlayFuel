import SwiftUI

/// Sheet for creating or editing a scouted player.
///
/// Reused for both create (existingPlayer == nil) and edit (existingPlayer != nil).
/// The `onSave` closure is called when the parent should write to the API; the
/// sheet itself is responsible only for form state, not networking.
///
/// Per PLAYER_SCOUTING_V1.md §E.6:
///   - display_name is required (1–120 chars)
///   - club and city are optional (max 120 chars each)
struct AddPlayerSheet: View {

    /// When non-nil, the form is pre-filled for editing.
    let existingPlayer: Player?
    /// Called with (displayName, club, city) when Save is tapped.
    let onSave: (String, String, String) async -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var displayName: String
    @State private var club: String
    @State private var city: String
    @State private var isSaving = false
    @State private var errorMessage: String? = nil

    private var isEditing: Bool { existingPlayer != nil }

    init(existingPlayer: Player?, onSave: @escaping (String, String, String) async -> Void) {
        self.existingPlayer = existingPlayer
        self.onSave = onSave
        _displayName = State(initialValue: existingPlayer?.displayName ?? "")
        _club        = State(initialValue: existingPlayer?.club ?? "")
        _city        = State(initialValue: existingPlayer?.city ?? "")
    }

    private var isSaveEnabled: Bool {
        !displayName.trimmingCharacters(in: .whitespaces).isEmpty && !isSaving
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Player's name", text: $displayName)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.words)
                        .onChange(of: displayName) { _, new in
                            if new.count > 120 { displayName = String(new.prefix(120)) }
                        }
                } header: {
                    Text("Name")
                } footer: {
                    Text("Required")
                }

                Section {
                    TextField("Club (e.g. Dallas Tennis Academy)", text: $club)
                        .autocorrectionDisabled()
                        .onChange(of: club) { _, new in
                            if new.count > 120 { club = String(new.prefix(120)) }
                        }
                    TextField("City (e.g. Plano, TX)", text: $city)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.words)
                        .onChange(of: city) { _, new in
                            if new.count > 120 { city = String(new.prefix(120)) }
                        }
                } header: {
                    Text("Optional Info")
                } footer: {
                    Text("Helps identify this player across tournaments.")
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
            .navigationTitle(isEditing ? "Edit Player" : "Add Player")
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
        let trimmedName = displayName.trimmingCharacters(in: .whitespaces)
        let trimmedClub = club.trimmingCharacters(in: .whitespaces)
        let trimmedCity = city.trimmingCharacters(in: .whitespaces)
        await onSave(trimmedName, trimmedClub, trimmedCity)
        isSaving = false
        dismiss()
    }
}

// MARK: - Previews

#Preview("New Player") {
    AddPlayerSheet(existingPlayer: nil) { _, _, _ in }
}

#Preview("Edit Player") {
    AddPlayerSheet(existingPlayer: FakeData.fakePlayers[0]) { _, _, _ in }
}

#Preview("Dark") {
    AddPlayerSheet(existingPlayer: nil) { _, _, _ in }
        .preferredColorScheme(.dark)
}
