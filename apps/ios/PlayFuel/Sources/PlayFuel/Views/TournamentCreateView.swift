import SwiftUI

/// US-03 extension — In-app tournament creation.
/// Phase 5b: shipped to replace the "create via Supabase Console" workaround.
///
/// On save: POSTs to /v1/tournaments via `Repository.createTournament`, sets
/// `AppState.selectedTournamentId`, forces a list reload, then dismisses.
///
/// Presented as a sheet from `TournamentListView`.
struct TournamentCreateView: View {

    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - Form state

    @State private var name: String = ""
    @State private var venueName: String = ""
    @State private var latText: String = "32.78"
    @State private var lngText: String = "-96.80"
    @State private var startDate: Date = Date()
    @State private var endDate: Date = Calendar.current.date(byAdding: .day, value: 1, to: Date()) ?? Date()
    @State private var selectedTimeZone: String = "America/Chicago"

    // MARK: - Async state

    @State private var isSaving: Bool = false
    @State private var errorMessage: String? = nil

    // MARK: - Constants

    private let timeZones: [(id: String, label: String)] = [
        ("America/Chicago",     "Central (CT)"),
        ("America/New_York",    "Eastern (ET)"),
        ("America/Denver",      "Mountain (MT)"),
        ("America/Los_Angeles", "Pacific (PT)"),
        ("America/Phoenix",     "Arizona (AZ)")
    ]

    // MARK: - Validation

    /// True when all required fields are non-empty, coordinates parse, and end ≥ start.
    private var isValid: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        !venueName.trimmingCharacters(in: .whitespaces).isEmpty &&
        Double(latText) != nil &&
        Double(lngText) != nil &&
        endDate >= startDate
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Form {
                Section("Tournament") {
                    TextField("Name (required)", text: $name)
                        .autocorrectionDisabled()

                    TextField("Venue name (required)", text: $venueName)
                        .autocorrectionDisabled()
                }

                Section(
                    header: Text("Venue Coordinates"),
                    footer: Text("Defaults to Dallas demo coords. Geocoding arrives in a later version.")
                ) {
                    HStack {
                        Text("Latitude")
                            .foregroundStyle(.secondary)
                        Spacer()
                        TextField("32.78", text: $latText)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .multilineTextAlignment(.trailing)
                    }
                    HStack {
                        Text("Longitude")
                            .foregroundStyle(.secondary)
                        Spacer()
                        TextField("-96.80", text: $lngText)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .multilineTextAlignment(.trailing)
                    }
                }

                Section("Dates") {
                    DatePicker(
                        "Start date",
                        selection: $startDate,
                        displayedComponents: .date
                    )
                    DatePicker(
                        "End date",
                        selection: $endDate,
                        in: startDate...,
                        displayedComponents: .date
                    )
                }

                Section(
                    header: Text("Time Zone"),
                    footer: Text("Captured for future plan scheduling. Not yet stored by the API.")
                ) {
                    Picker("Time zone", selection: $selectedTimeZone) {
                        ForEach(timeZones, id: \.id) { tz in
                            Text(tz.label).tag(tz.id)
                        }
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
            .navigationTitle("New Tournament")
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
                        .disabled(!isValid)
                    }
                }
            }
            // Keep endDate valid whenever startDate advances past it
            .onChange(of: startDate) { _, newStart in
                if endDate < newStart {
                    endDate = newStart
                }
            }
        }
    }

    // MARK: - Save

    private func save() async {
        guard isValid, !isSaving else { return }
        isSaving = true
        errorMessage = nil

        let lat = Double(latText) ?? 32.78
        let lng = Double(lngText) ?? -96.80

        do {
            let tournament = try await appState.repository.createTournament(
                name: name.trimmingCharacters(in: .whitespaces),
                venueName: venueName.trimmingCharacters(in: .whitespaces),
                venueLat: lat,
                venueLng: lng,
                startDate: startDate,
                endDate: endDate,
                timeZone: selectedTimeZone
            )
            // Select the new tournament and refresh the list before dismissing.
            appState.selectedTournamentId = tournament.id
            await appState.loadTournaments()
            dismiss()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription
                ?? error.localizedDescription
            isSaving = false
        }
    }
}

// MARK: - Preview

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return TournamentCreateView()
        .environmentObject(state)
}
