import Foundation

/// Structured nutrition suggestions for a food option.
///
/// Five-bucket schema per FOOD_DECK_AND_MAP_V1.md §A.1.
///
/// Replaces the flat `recommendedOrder: String` for iOS UI rendering.
/// The backend derives `recommendedOrder` via `derive_recommended_order()` for
/// LLM input and legacy API consumers — structured suggestions are iOS-display only.
///
/// FOOD_DECK_AND_MAP_V1.md §A.1
struct FoodSuggestions: Codable, Hashable, Sendable {

    /// Headline meal orders — what to get (e.g. "Rice bowl: brown or white rice base").
    var mainOptions: [String]

    /// Supplemental carbs, sides, and easy fuel (e.g. "Banana or fruit cup").
    var addOns: [String]

    /// Recommended beverages (e.g. "16–20 oz water").
    var drinks: [String]

    /// What to skip pre-match / dietary cautions (e.g. "Sour cream", "Spicy salsas").
    var avoid: [String]

    /// Timing, logistics, brief tips (e.g. "Eat 60–90 min before next match").
    var notes: [String]

    init(
        mainOptions: [String] = [],
        addOns: [String] = [],
        drinks: [String] = [],
        avoid: [String] = [],
        notes: [String] = []
    ) {
        self.mainOptions = mainOptions
        self.addOns = addOns
        self.drinks = drinks
        self.avoid = avoid
        self.notes = notes
    }

    /// Convenience empty value — safe default for pre-Phase-9 plans or
    /// options without structured suggestions.
    static let empty = FoodSuggestions()

    /// True when all five buckets are empty.
    var allEmpty: Bool {
        mainOptions.isEmpty && addOns.isEmpty && drinks.isEmpty && avoid.isEmpty && notes.isEmpty
    }
}
