import Foundation

/// A nearby food option with a recommended order template.
/// Phase 5: populated from Places API (Google Places or Yelp Fusion).
/// Phase 1: hardcoded in FakeData.swift.
struct FoodOption: Codable, Identifiable, Hashable {

    let id: UUID

    /// Restaurant name, e.g. "Chipotle".
    let name: String

    /// Template category from §F.3, e.g. "fast_casual_bowl".
    let category: String

    /// Estimated drive time from the tournament venue.
    let driveTimeMin: Int

    /// Recommended order text from §F.3 registry.
    /// `fast_casual_bowl` is confirmed: "Chicken rice bowl with light beans, mild toppings, sauce on the side"
    /// Other templates are [DRAFT — OQ-B].
    let recommendedOrder: String
}
