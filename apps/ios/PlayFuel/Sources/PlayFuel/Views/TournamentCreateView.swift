import SwiftUI

/// US-03 extension — In-app tournament creation.
/// Phase 5b: shipped to replace the "create via Supabase Console" workaround.
///
/// On save: POSTs to /v1/tournaments via `Repository.createTournament`, sets
/// `AppState.selectedTournamentId`, forces a list reload, then dismisses.
///
/// Presented as a sheet from `TournamentListView`.
///
/// ACCOMMODATIONS_V1: Optional accommodation section added. The Venue Section
/// is refactored to use the shared `VenuePickerSection` private component.
/// Accommodation fields are fully optional — `isValid` gate is unchanged.
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

    // MARK: - Accommodations (ACCOMMODATIONS_V1 — migration 0021)
    @StateObject private var accommodationVM = VenueSearchViewModel()
    @State private var accommodationKind: String = "home"  // default: home

    // MARK: - Async state

    @State private var isSaving: Bool = false
    @State private var errorMessage: String? = nil

    // MARK: - Constants

    private let timeZones: [(id: String, label: String)] = [
        // Americas — North
        ("America/New_York",    "Eastern (ET)"),
        ("America/Chicago",     "Central (CT)"),
        ("America/Denver",      "Mountain (MT)"),
        ("America/Phoenix",     "Arizona (AZ)"),
        ("America/Los_Angeles", "Pacific (PT)"),
        ("America/Toronto",     "Toronto (ET)"),
        ("America/Vancouver",   "Vancouver (PT)"),
        // Americas — Mexico + Latin America
        ("America/Mexico_City", "Mexico City (CST)"),
        ("America/Monterrey",   "Monterrey (CST)"),
        ("America/Tijuana",     "Tijuana (PST)"),
        ("America/Sao_Paulo",   "São Paulo (BRT)"),
        // Europe
        ("Europe/London",       "London (GMT)"),
        ("Europe/Madrid",       "Madrid (CET)"),
        ("Europe/Paris",        "Paris (CET)"),
        ("Europe/Berlin",       "Berlin (CET)"),
        ("Europe/Rome",         "Rome (CET)"),
        // Asia / Oceania
        ("Asia/Tokyo",          "Tokyo (JST)"),
        ("Australia/Sydney",    "Sydney (AEST)")
    ]

    // MARK: - Validation

    /// True when name is non-empty, a venue has been picked from autocomplete, and end >= start.
    /// ACCOMMODATIONS_V1: accommodation is fully optional — NOT part of isValid gate.
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

                // Venue section — refactored to use shared VenuePickerSection component.
                Section("Venue") {
                    VenuePickerSection(vm: venueVM, placeholder: "Search for a venue…")
                }

                Section {
                    Picker("", selection: $drawSize) {
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

                // MARK: — Accommodations Section (ACCOMMODATIONS_V1 §D.1)
                Section {
                    Picker("", selection: $accommodationKind) {
                        Text(HardCodedStrings.accommodationsToggleHome).tag("home")
                        Text(HardCodedStrings.accommodationsToggleHotel).tag("hotel")
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: accommodationKind) { _, _ in accommodationVM.clear() }

                    VenuePickerSection(
                        vm: accommodationVM,
                        placeholder: accommodationKind == "hotel"
                            ? HardCodedStrings.accommodationsPlaceholderHotel
                            : HardCodedStrings.accommodationsPlaceholderHome
                    )

                    Button(HardCodedStrings.accommodationsSkipCTA) {
                        accommodationVM.clear()
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                } header: {
                    Text(HardCodedStrings.accommodationsSectionHeader)
                } footer: {
                    Text(HardCodedStrings.accommodationsSectionFooter)
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
                    footer: Text("Stored with the tournament for display and future server-side scheduling.")
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

        // Accommodation (optional) — assemble full display address string.
        // [venueAddress, venueCity, venueRegion].compactMap strips nils; join with ", ".
        // Nil if no accommodation selected or if all address parts are nil.
        let accommodation = accommodationVM.selectedVenue
        let accAddress: String? = {
            guard let acc = accommodation else { return nil }
            let parts = [acc.venueAddress, acc.venueCity, acc.venueRegion].compactMap { $0 }
            return parts.isEmpty ? nil : parts.joined(separator: ", ")
        }()

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
                timeZone: selectedTimeZone,
                venueCountry: venue.venueCountry,
                // Accommodation fields — nil when none selected (§D.4)
                accommodationLat: accommodation?.venueLat,
                accommodationLng: accommodation?.venueLng,
                accommodationAddress: accAddress,
                accommodationKind: accommodation != nil ? accommodationKind : nil
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

// MARK: - VenuePickerSection

/// Reusable MapKit venue-search picker UI.
/// Extracted from TournamentCreateView inline code (ACCOMMODATIONS_V1 §D.2).
/// Used for both the tournament venue picker and the accommodation picker.
///
/// - `vm`: The VenueSearchViewModel driving this picker (a separate instance per picker).
/// - `placeholder`: Search field placeholder text; varies by context (venue vs accommodation kind).
///
/// When a venue is selected (`vm.selectedVenue != nil`), renders a card with address lines
/// and a "Change location" destructive button. When searching, renders a TextField bound
/// to `vm.query` plus inline MapKit autocomplete suggestions.
private struct VenuePickerSection: View {
    @ObservedObject var vm: VenueSearchViewModel
    let placeholder: String

    var body: some View {
        if let v = vm.selectedVenue {
            // Selected state — show address card + clear button
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
            Button(HardCodedStrings.accommodationsChangeButton, role: .destructive) {
                vm.clear()
            }
            .font(.caption)
        } else {
            // Search state — text field + MapKit autocomplete suggestions
            TextField(placeholder, text: $vm.query)
                .autocorrectionDisabled()
            if vm.isSearching {
                HStack {
                    Spacer()
                    ProgressView().controlSize(.small)
                    Spacer()
                }
            }
            ForEach(vm.suggestions, id: \.self) { suggestion in
                Button {
                    Task { await vm.select(suggestion) }
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
