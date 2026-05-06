import MapKit
import SwiftUI

// MARK: - SelectedVenue

/// Resolved placemark fields populated when user taps an autocomplete suggestion.
struct SelectedVenue {
    let venueName: String
    let venueAddress: String?
    let venueCity: String?
    let venueRegion: String?
    let venuePostal: String?
    let venueLat: Double
    let venueLng: Double
    /// ISO 3166-1 alpha-2 country code from MKPlacemark.isoCountryCode (e.g. "MX", "US").
    /// Nil if MapKit cannot resolve a country code for the placemark.
    let venueCountry: String?
}

// MARK: - VenueSearchViewModel

/// View-model for the venue autocomplete picker in `TournamentCreateView`.
///
/// Wraps `MKLocalSearchCompleter` (MapKit, keyless, zero new dependencies).
/// User types → suggestions update → user taps → `selectedVenue` is populated
/// from the resolved `MKMapItem.placemark`.
///
/// Spec: tournament-location-spec.md §E.1
final class VenueSearchViewModel: NSObject, ObservableObject, MKLocalSearchCompleterDelegate {

    // MARK: - Published state

    /// Text the user is typing in the search field.
    @Published var query: String = "" {
        didSet { completer.queryFragment = query }
    }

    /// Current autocomplete suggestions from MapKit.
    @Published private(set) var suggestions: [MKLocalSearchCompletion] = []

    /// Populated once the user selects a suggestion and it resolves to a placemark.
    @Published private(set) var selectedVenue: SelectedVenue? = nil

    /// True while an async `MKLocalSearch` request is in flight.
    @Published private(set) var isSearching: Bool = false

    // MARK: - Private

    private let completer: MKLocalSearchCompleter

    // MARK: - Init

    override init() {
        completer = MKLocalSearchCompleter()
        super.init()
        completer.resultTypes = [.pointOfInterest, .address]
        completer.delegate = self
    }

    // MARK: - MKLocalSearchCompleterDelegate

    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        suggestions = completer.results
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        suggestions = []
    }

    // MARK: - Selection

    /// Resolve an autocomplete completion to a full placemark and populate `selectedVenue`.
    @MainActor
    func select(_ completion: MKLocalSearchCompletion) async {
        isSearching = true
        defer { isSearching = false }
        let request = MKLocalSearch.Request(completion: completion)
        do {
            let response = try await MKLocalSearch(request: request).start()
            guard let item = response.mapItems.first else { return }
            let pm = item.placemark
            // Build a single-line street address from sub-thoroughfare + thoroughfare
            let streetParts = [pm.subThoroughfare, pm.thoroughfare]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
            let streetAddress = streetParts.isEmpty ? nil : streetParts.joined(separator: " ")
            selectedVenue = SelectedVenue(
                venueName:    pm.name ?? completion.title,
                venueAddress: streetAddress,
                venueCity:    pm.locality,
                venueRegion:  pm.administrativeArea,
                venuePostal:  pm.postalCode,
                venueLat:     pm.coordinate.latitude,
                venueLng:     pm.coordinate.longitude,
                venueCountry: pm.isoCountryCode
            )
            query = ""
            suggestions = []
        } catch {
            // Silently suppress — user can retry by tapping a different suggestion
        }
    }

    /// Clear the current selection so the user can search again.
    func clear() {
        selectedVenue = nil
        query = ""
        suggestions = []
        completer.queryFragment = ""
    }
}
