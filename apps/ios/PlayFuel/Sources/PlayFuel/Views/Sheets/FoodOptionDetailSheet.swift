import SwiftUI
import MapKit

/// Per-restaurant detail sheet — structured nutrition suggestions.
///
/// Opened by tapping a card in `FoodOptionDeck` or a food pin in `VenueMapSheet`.
/// Renders five structured suggestion buckets (mainOptions, addOns, drinks, avoid, notes)
/// from `FoodOption.suggestions`. Empty buckets are hidden.
///
/// Footer: "Open in Maps" button (Apple Maps, driving directions) when lat/lng available.
/// Safety note: allergy/dietary disclaimer verbatim per §C (must not be removed).
///
/// FOOD_DECK_AND_MAP_V1.md §C · §F.10
struct FoodOptionDetailSheet: View {

    let option: FoodOption

    @Environment(\.dismiss) private var dismiss

    private var suggestions: FoodSuggestions {
        option.suggestions ?? .empty
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // DRAFT badge
                    if option.isDraft {
                        Text("Suggestions in development — confirm with your athlete")
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color(.systemFill), in: Capsule())
                    }

                    // Header: category + drive info
                    VStack(alignment: .leading, spacing: 6) {
                        Text(categoryLabel)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)

                        HStack(spacing: 6) {
                            Image(systemName: "car")
                                .font(.caption)
                            if let dt = option.driveTimeMin {
                                Text(DurationFormatting.friendly(minutes: dt))
                                    .font(.caption.weight(.medium))
                            }
                            if let dm = option.distanceMeters {
                                Text("·")
                                    .font(.caption)
                                Text(distanceText(dm))
                                    .font(.caption)
                            }
                        }
                        .foregroundStyle(.secondary)
                    }

                    Divider()

                    // What to order (mainOptions)
                    if !suggestions.mainOptions.isEmpty {
                        SuggestionSection(title: "What to order") {
                            ForEach(suggestions.mainOptions, id: \.self) { item in
                                BulletRow(text: item)
                            }
                        }
                    }

                    // Add-ons & carbs
                    if !suggestions.addOns.isEmpty {
                        SuggestionSection(title: "Add-ons & carbs") {
                            ForEach(suggestions.addOns, id: \.self) { item in
                                BulletRow(text: item)
                            }
                        }
                    }

                    // Drinks
                    if !suggestions.drinks.isEmpty {
                        SuggestionSection(title: "Drinks") {
                            ForEach(suggestions.drinks, id: \.self) { item in
                                BulletRow(text: item)
                            }
                        }
                    }

                    // Avoid before match (red)
                    if !suggestions.avoid.isEmpty {
                        SuggestionSection(
                            title: "Avoid before match",
                            icon: "exclamationmark.triangle.fill",
                            iconColor: .red
                        ) {
                            ForEach(suggestions.avoid, id: \.self) { item in
                                BulletRow(text: item, color: .red.opacity(0.8))
                            }
                        }
                    }

                    // Notes (small, grey)
                    if !suggestions.notes.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(suggestions.notes, id: \.self) { note in
                                Text(note)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Divider()

                    // "Open in Maps" footer action
                    if let lat = option.lat, let lng = option.lng {
                        Button {
                            openInMaps(lat: lat, lng: lng, name: option.name)
                        } label: {
                            Label("Open in Maps", systemImage: "map.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }

                    Divider()

                    // Safety note — VERBATIM, must not be removed (§C safety footer)
                    Text("If your player has food allergies, intolerances, or dietary restrictions, consult the relevant professional before following these suggestions.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .navigationTitle(option.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Helpers

    private var categoryLabel: String {
        switch option.category {
        case "fast_casual_bowl":  return "Fast casual bowl"
        case "sandwich_shop":     return "Sandwich shop"
        case "grocery_prepared":  return "Grocery prepared"
        case "breakfast_cafe":    return "Breakfast café"
        default:                  return option.category.replacingOccurrences(of: "_", with: " ")
        }
    }

    private func distanceText(_ meters: Int) -> String {
        let rounded = (meters / 10) * 10
        if rounded >= 1000 {
            return String(format: "%.1f km", Double(rounded) / 1000)
        }
        return "\(rounded)m"
    }

    /// Opens the food option in Apple Maps for turn-by-turn driving directions.
    private func openInMaps(lat: Double, lng: Double, name: String) {
        let placemark = MKPlacemark(coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng))
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = name
        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving
        ])
    }
}

// MARK: - Sub-views

/// A labelled section with optional icon + colour.
private struct SuggestionSection<Content: View>: View {

    let title: String
    var icon: String = "checkmark.circle"
    var iconColor: Color = .green
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(iconColor)
            content
        }
    }
}

/// A single bulleted row.
private struct BulletRow: View {

    let text: String
    var color: Color = .primary

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundStyle(color)
            Text(text)
                .foregroundStyle(color)
        }
        .font(.body)
    }
}

#Preview {
    FoodOptionDetailSheet(option: FakeData.dallasFoodOptions[0])
}

#Preview("Dark") {
    FoodOptionDetailSheet(option: FakeData.dallasFoodOptions[0])
        .preferredColorScheme(.dark)
}
