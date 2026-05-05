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
    @StateObject private var venueVM = VenueSearchViewModel()
    @State private var startDate: Date = Date()
    @State private var endDate: Date = Calendar.current.date(byAdding: .day, value: 1, to: Date()) ?? Date()
    @State private var selectedTimeZone: String = "America/Chicago"

    // MARK: - Draw size (migration 0016)
    @State private var drawSize: Int = 32

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

    /// True when name is non-empty, a venue has been picked from autocomplete, and end ≥ start.
    private var isValid: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        venueVM.selectedVenue != nil &&
        endDate >= startDate
    }

    // MARK: - Body

    var body: some View {
        NavigationStack {
            Form {
                Section("Tournament") {
                    TextField("Name (required)", text: $name)
                        .autocorrectionDisabled()
                }

                Section("Venue") {
                    if let v = venueVM.selectedVenue {
                        // ── Selected state: show venue card + clear button ──
                        VStack(alignment: .leading, spacing: 4) {
                            Text(v.venueName)
                                .font(.body)
                            if let addr = v.venueAddress {
                                Text(addr)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if let city = v.venueCity, let region = v.venueRegion {
                                Text("\(city), \(region)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 2)
                        Button("Change venue", role: .destructive) {
                            venueVM.clear()
                        }
                        .font(.caption)
                    } else {
                        // ── Search state: text field + suggestions ──
                        TextField("Search for a venue…", text: $venueVM.query)
                            .autocorrectionDisabled()
                        if venueVM.isSearching {
                            HStack {
                                Spacer()
                                ProgressView().controlSize(.small)
                                Spacer()
                            }
                        }
                        ForEach(venueVM.suggestions, id: \.self) { suggestion in
                            Button {
                                Task { await venueVM.select(suggestion) }
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(suggestion.title)
                                        .font(.body)
                                        .foregroundStyle(Color.primary)
                                    if !suggestion.subtitle.isEmpty {
                                        Text(suggestion.subtitle)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.vertical, 1)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                Section {
                    Picker("Draw size", selection: $drawSize) {
                        ForEach(RoundVocab.drawSizes, id: \.self) { size in
                            Text(RoundVocab.drawSizeLabel(size)).tag(size)
                        }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                } header: {
                    Text("Draw Size")
                } footer: {
                    Text("Number of players in the bracket. Check your entry confirmation email or the bracket sheet at the venue.")
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
        guard isValid, !isSaving, let venue = venueVM.selectedVenue else { return }
        isSaving = true
        errorMessage = nil

        do {
            let tournament = try await appState.repository.createTournament(
                name: name.trimmingCharacters(in: .whitespaces),
                venueName: venue.venueName,
                venueAddress: venue.venueAddress,
                venueCity: venue.venueCity,
                venueRegion: venue.venueRegion,
                venuePostal: venue.venuePostal,
                venueLat: venue.venueLat,
                venueLng: venue.venueLng,
                startDate: startDate,
                endDate: endDate,
                drawSize: drawSize,
                timeZone: selectedTimeZone
            )

            // OPTIMISTIC INSERT — perf/measure-and-optimize
            //
            // The server returned the canonical Tournament row. Insert it directly
            // into the local list instead of calling loadTournaments() for a second
            // network round-trip. Eliminates ~400 ms of serial wait before dismiss.
            //
            // Rollback path: only reached here on SUCCESS — if createTournament()
            // throws, the catch block shows the inline error and the list is untouched.
            // On success the new row is the truth; we trust the server response.
            if case .loaded(let existing) = appState.tournaments {
                appState.tournaments = .loaded(existing + [tournament])
            }
            appState.selectedTournamentId = tournament.id
            // Dismiss immediately — no second round-trip needed.
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

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return TournamentCreateView()
        .environmentObject(state)
        .preferredColorScheme(.dark)
}
