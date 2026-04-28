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
    ///
    /// FOOD_DECK_AND_MAP_V1.md §I-3: widened from `Int` to `Int?` —
    /// Python is `Optional[int]`; prior `?? 0` shim in FoodOptionDTO.toModel() removed.
    let driveTimeMin: Int?

    /// Recommended order text — single-line fallback derived from `suggestions`.
    /// Used by LLM input builder and legacy iOS consumers. Not rendered in FoodOptionDetailSheet.
    let recommendedOrder: String

    // MARK: - Phase 5 additions (Task #8)

    /// True when this template is an OQ-B unconfirmed draft (sandwich_shop, grocery_prepared,
    /// breakfast_cafe). False for confirmed templates (fast_casual_bowl).
    let isDraft: Bool

    /// Straight-line distance from the tournament venue in metres. Nil when unknown.
    let distanceMeters: Int?

    /// Provider-specific place ID for potential deep-linking (deferred). Nil for mock provider.
    let placeId: String?

    /// Data source: "google" (real Places API) or "mock" (deterministic fixture) or "fake".
    let provider: String

    // MARK: - Phase 9 additions (FOOD_DECK_AND_MAP_V1.md)

    /// Structured nutrition suggestions for the deck detail sheet.
    /// Nil for plans generated before the Phase 9 backend update.
    /// UI falls back to `FoodSuggestions.empty` when nil — sections are hidden when empty.
    let suggestions: FoodSuggestions?

    /// Venue latitude for map pins (Google Places `geometry.location.lat`).
    /// Nil for pre-Phase-9 plans or when the Places provider could not geocode the place.
    let lat: Double?

    /// Venue longitude for map pins.
    let lng: Double?
}
