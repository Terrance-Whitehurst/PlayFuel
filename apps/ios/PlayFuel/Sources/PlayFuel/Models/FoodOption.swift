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
    /// Nil when the API cannot determine drive time (e.g. mock provider without routing).
    let driveTimeMin: Int

    /// Recommended order text from §F.3 registry.
    /// `fast_casual_bowl` is confirmed: "Chicken rice bowl with light beans, mild toppings, sauce on the side"
    /// Other templates are [DRAFT — OQ-B].
    let recommendedOrder: String

    // MARK: - Phase 5 additions (Task #8)

    /// True when this template is an OQ-B unconfirmed draft (sandwich_shop, grocery_prepared, breakfast_cafe).
    /// False for confirmed templates (fast_casual_bowl).
    let isDraft: Bool

    /// Straight-line distance from the tournament venue in metres. Nil when unknown.
    let distanceMeters: Int?

    /// Provider-specific place ID for potential deep-linking (deferred). Nil for mock provider.
    let placeId: String?

    /// Data source: "google" (real Places API) or "mock" (deterministic fixture).
    let provider: String
}
