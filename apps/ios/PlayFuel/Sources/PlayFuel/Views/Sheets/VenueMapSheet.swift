import SwiftUI
import MapKit

/// Interactive MapKit sheet centred on the tournament venue.
///
/// Shows:
///   • Blue tennisball.fill pin at the tournament venue.
///   • Orange fork.knife annotation for each food option that has lat/lng.
/// Tap a food annotation → `FoodOptionDetailSheet` (reuses §C).
///
/// Library: MapKit (SwiftUI `Map`, iOS 17+) — no API key, no third-party SDK.
/// Placement: third bubble in HeaderBubbleRow ("Map" bubble, green tint).
///
/// Empty state: when tournament.lat == 0 && tournament.lon == 0 (TournamentDTO
/// defaults to 0.0 when the DB row has no venue coordinates).
///
/// FOOD_DECK_AND_MAP_V1.md §D · §F.11
/// OQ-FOOD-DECK-3: Food pin coordinates are best-guess for demo fixtures.
///                  Real coords will come from Google Places geometry.location.
struct VenueMapSheet: View {

    let tournament: Tournament
    let foodOptions: [FoodOption]

    @State private var selectedFood: FoodOption? = nil
    @Environment(\.dismiss) private var dismiss

    /// Venue coords are non-optional on the model (0.0 when absent via TournamentDTO fallback).
    /// Treat (0, 0) as "no venue location" — coordinates for the Gulf of Guinea.
    private var hasVenueCoords: Bool {
        tournament.lat != 0 || tournament.lon != 0
    }

    var body: some View {
        NavigationStack {
            mapContent
                .navigationTitle("Tournament Map")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
        .sheet(item: $selectedFood) { food in
            FoodOptionDetailSheet(option: food)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    // MARK: - Map Content

    @ViewBuilder
    private var mapContent: some View {
        if !hasVenueCoords {
            ContentUnavailableView(
                "No venue location",
                systemImage: "mappin.slash",
                description: Text("Add a venue address to see the map")
            )
        } else {
            Map(initialPosition: .region(venueRegion)) {

                // Tournament venue pin — blue
                Marker(
                    tournament.venue,
                    systemImage: "tennisball.fill",
                    coordinate: CLLocationCoordinate2D(
                        latitude: tournament.lat,
                        longitude: tournament.lon
                    )
                )
                .tint(.blue)

                // Food option pins — orange circle with fork.knife
                // Only rendered for options that have valid coordinates.
                ForEach(foodOptionsWithCoords) { option in
                    Annotation(
                        option.name,
                        coordinate: CLLocationCoordinate2D(
                            latitude: option.lat!,
                            longitude: option.lng!
                        )
                    ) {
                        Button {
                            selectedFood = option
                        } label: {
                            ZStack {
                                Circle()
                                    .fill(Color.orange)
                                    .frame(width: 36, height: 36)
                                Image(systemName: "fork.knife")
                                    .foregroundStyle(.white)
                                    .font(.system(size: 16, weight: .semibold))
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .mapStyle(.standard)
            .mapControls {
                MapUserLocationButton()
                MapCompass()
            }
        }
    }

    // MARK: - Helpers

    private var venueRegion: MKCoordinateRegion {
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(
                latitude: tournament.lat,
                longitude: tournament.lon
            ),
            // ~4-mile view — fits all Dallas demo fixtures within ~3 miles
            span: MKCoordinateSpan(latitudeDelta: 0.06, longitudeDelta: 0.06)
        )
    }

    private var foodOptionsWithCoords: [FoodOption] {
        foodOptions.filter { $0.lat != nil && $0.lng != nil }
    }
}

#Preview {
    VenueMapSheet(
        tournament: FakeData.dallasTournament,
        foodOptions: FakeData.dallasFoodOptions
    )
}

#Preview("Dark") {
    VenueMapSheet(
        tournament: FakeData.dallasTournament,
        foodOptions: FakeData.dallasFoodOptions
    )
    .preferredColorScheme(.dark)
}
