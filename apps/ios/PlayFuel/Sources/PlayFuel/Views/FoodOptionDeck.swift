import SwiftUI

/// Scroll-snap horizontal deck of nearby food option cards.
///
/// Replaces the inline `FoodCardView` list on the dashboard per
/// FOOD_DECK_AND_MAP_V1.md §B (scroll-snap pattern, iOS 17+).
///
/// Layout:
///   Section header → [Card 280×170] [Card 280×170] ... (30+pt peek of next)
///
/// - Each card carries its own "Menu Suggestions" pill button (indigo capsule,
///   top-right corner) that opens `FoodOptionDetailSheet` — same pattern as
///   ScenarioCardView's "See suggestions" (SCENARIO_CARD_BUTTON_AFFORDANCE,
///   session morbp13jbtvy). Card body is non-interactive; only the pill button
///   opens the sheet. Sheet reopens cleanly on every tap (@State resets on dismiss).
/// - Empty / bag-fallback → single full-width orange card with verbatim
///   `HardCodedStrings.bagFoodFallback`
/// - Uses `ScrollView(.horizontal)` + `.scrollTargetBehavior(.viewAligned)` (iOS 17+)
///
/// FOOD_DECK_AND_MAP_V1.md §B · §F.9
/// MENU_SUGGESTIONS_AFFORDANCE (session morbp13jbtvy)
struct FoodOptionDeck: View {

    let foodOptions: [FoodOption]
    let bagFallbackOnly: Bool
    /// True when the Google Places API call failed (key invalid, billing error, network).
    /// False when the API succeeded but returned no restaurants (genuine empty result).
    /// Drives the three-way conditional render: unavailable / empty / populated.
    let placesUnavailable: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {

            // Section header
            Label("Nearby Food Options", systemImage: "fork.knife.circle.fill")
                .font(.headline)
                .padding(.horizontal, 16)

            if placesUnavailable {
                // Case 1: Places API call failed — warn the parent, then show bag fallback
                placesUnavailableCard
                bagFallbackCard
            } else if foodOptions.isEmpty || bagFallbackOnly {
                // Case 2: API succeeded but no restaurants found (rural venue / bag-only strategy)
                noRestaurantsCard
                bagFallbackCard
            } else {
                // Case 3: Populated — scroll-snap deck, each card manages its own sheet state
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 12) {
                        ForEach(foodOptions) { option in
                            FoodOptionCard(option: option)
                                .frame(width: 280, height: 170)
                        }
                    }
                    .scrollTargetLayout()
                    .padding(.horizontal, 16)
                }
                .scrollTargetBehavior(.viewAligned)
            }
        }
    }

    // MARK: - Empty States (OQ-FOOD-EMPTY-1)

    /// Case 1: Google Places API call failed — key invalid, billing off, network timeout, etc.
    /// Uses `wifi.exclamationmark` to signal "not a normal empty state, something failed."
    /// The bag-fallback card is rendered BELOW this card — the pre-packed safety net is preserved.
    private var placesUnavailableCard: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .foregroundStyle(.orange)
                .font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                Text("Nearby restaurants unavailable right now.")
                    .font(.subheadline.weight(.semibold))
                Text("Showing pre-packed bag suggestions only — verify with the venue when you arrive.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(Color.orange.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 16)
    }

    /// Case 2: Places API succeeded but no restaurants within the search radius.
    /// Plain empty state — no warning iconography (this is a legitimate outcome, not a failure).
    private var noRestaurantsCard: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "mappin.slash")
                .foregroundStyle(.secondary)
                .font(.title3)
            Text("No nearby restaurants found within search radius.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .background(Color(.systemFill))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 16)
    }

    // MARK: - Bag-Food Fallback (§H.3 verbatim)

    private var bagFallbackCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "bag.fill")
                    .foregroundStyle(.orange)
                Text("Bag Food — No Nearby Options Found")
                    .font(.subheadline.weight(.semibold))
            }
            // Verbatim from HardCodedStrings.bagFoodFallback (§H.3)
            Text(HardCodedStrings.bagFoodFallback)
                .font(.body)
                .foregroundStyle(.primary)
        }
        .padding(16)
        .background(Color.orange.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 16)
    }
}

// MARK: - Food Option Card

/// Single card in the `FoodOptionDeck`.
/// 280×170pt, rounded 16, secondary background, subtle shadow.
///
/// MENU_SUGGESTIONS_AFFORDANCE (session morbp13jbtvy):
/// "Menu Suggestions" indigo pill button at top-right corner (ZStack .topTrailing).
/// Card body is non-interactive (.accessibilityElement(children: .combine));
/// the pill button opens FoodOptionDetailSheet as a separate VoiceOver element.
/// @State showingMenu resets to false on sheet dismiss — no state leak.
///
/// Color: Color.indigo (system semantic — adapts dark mode).
///   Light: ~#5856D6 · white text contrast ~5.4:1 (WCAG AA ≥ 4.5:1 ✅)
///   NOT red (EmergencyStrip reserved) / amber (overrun reserved) /
///   yellow (tight reserved) / PlayFuel green (scenario card reserved).
private struct FoodOptionCard: View {

    let option: FoodOption

    /// Controls the Menu Suggestions sheet.
    /// Resets to false on dismiss — no manual reset needed, no state leak.
    @State private var showingMenu = false

    var body: some View {
        // ── Glass card — inline button layout ────────────────────────────────
        // Fixes "Chipotle Mexican Grill" (and other long names) running behind
        // the menu suggestions button. Button is now inline in the name HStack
        // with layoutPriority(0) + fixedSize; name VStack takes remaining space.
        VStack(alignment: .leading, spacing: 8) {

            // Name row + button — flex HStack prevents text/button collision
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(option.name)
                        .font(.headline)
                        .lineLimit(2)
                        .truncationMode(.tail)
                        .multilineTextAlignment(.leading)
                    if option.isDraft {
                        Text("DRAFT")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color(.systemFill), in: Capsule())
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .layoutPriority(1)

                menuSuggestionsButton
            }

            // Category pill
            Text(categoryLabel)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer(minLength: 0)

            // Drive time + distance
            HStack(spacing: 4) {
                Image(systemName: "car")
                    .font(.caption)
                if let dt = option.driveTimeMin {
                    Text(DurationFormatting.friendly(minutes: dt))
                        .font(.caption.weight(.medium))
                } else {
                    Text("–")
                        .font(.caption)
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
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        // Glassmorphic card background — ultraThinMaterial + top-lit stroke
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [.white.opacity(0.40), .white.opacity(0.06)],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.12), radius: 12, x: 0, y: 6)
        // One combined VoiceOver element; button is a separate focus element.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(cardAccessibilityLabel)
        // Sheet opens on every button tap; @State resets cleanly on dismiss.
        .sheet(isPresented: $showingMenu) {
            FoodOptionDetailSheet(option: option)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    // MARK: - Menu Suggestions Button

    /// Glass pill button — inline in name row HStack (step 3 layout fix).
    /// Solid indigo base preserves WCAG AA white-text contrast (~5.4:1 ✅).
    /// Glass highlights: white overlay sheen + top-lit stroke gradient.
    private var menuSuggestionsButton: some View {
        Button(action: { showingMenu = true }) {
            Text("Menu Suggestions")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background {
                    ZStack {
                        Capsule()
                            .fill(Color.indigo)
                        Capsule()
                            .fill(.white.opacity(0.10))
                        Capsule()
                            .strokeBorder(
                                LinearGradient(
                                    colors: [.white.opacity(0.45), .white.opacity(0.08)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                ),
                                lineWidth: 1
                            )
                    }
                }
                .shadow(color: Color.indigo.opacity(0.35), radius: 8, x: 0, y: 4)
        }
        .buttonStyle(.plain)
        .fixedSize(horizontal: true, vertical: false)
        .layoutPriority(0)
    }

    // MARK: - Helpers

    private var cardAccessibilityLabel: String {
        var parts: [String] = [option.name, categoryLabel]
        if let dt = option.driveTimeMin {
            parts.append("\(dt) minute drive")
        }
        if let dm = option.distanceMeters {
            parts.append(distanceText(dm) + " away")
        }
        if option.isDraft {
            parts.append("draft suggestions")
        }
        return parts.joined(separator: ", ")
    }

    private var categoryLabel: String {
        switch option.category {
        case "fast_casual_bowl":  return "Fast casual bowl"
        case "sandwich_shop":     return "Sandwich shop"
        case "grocery_prepared":  return "Grocery prepared"
        case "breakfast_cafe":    return "Breakfast cafe"
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
}

// MARK: - Previews

#Preview {
    ScrollView {
        VStack(spacing: 20) {
            // Case 3: Populated deck — "Menu Suggestions" button visible on each card
            FoodOptionDeck(
                foodOptions: FakeData.dallasFoodOptions,
                bagFallbackOnly: false,
                placesUnavailable: false
            )
            // Case 2: No restaurants found (API ok, genuine empty result)
            FoodOptionDeck(
                foodOptions: [],
                bagFallbackOnly: false,
                placesUnavailable: false
            )
            // Case 2b: bag-only strategy
            FoodOptionDeck(
                foodOptions: [],
                bagFallbackOnly: true,
                placesUnavailable: false
            )
        }
        .padding(.vertical)
    }
}

#Preview("Places unavailable") {
    // Case 1: Google Places API failed — warning card + bag fallback
    ScrollView {
        FoodOptionDeck(
            foodOptions: [],
            bagFallbackOnly: false,
            placesUnavailable: true
        )
        .padding(.vertical)
    }
}

#Preview("Menu Suggestions sheet — Chipotle") {
    // Simulates tapping "Menu Suggestions" on Chipotle card:
    // full populated FoodOptionDetailSheet with mainOptions + addOns + drinks + avoid + notes
    FoodOptionDetailSheet(option: FakeData.dallasFoodOptions[0])
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
}

#Preview("Menu Suggestions sheet — empty suggestions") {
    // Empty-suggestions state: FoodOption with no FoodSuggestions (nil)
    // FoodOptionDetailSheet shows no suggestion sections (all hidden when empty).
    FoodOptionDetailSheet(option: FoodOption(
        id: UUID(uuidString: "CC000009-0000-0000-0000-000000000009")!,
        name: "Sample Restaurant",
        category: "fast_casual_bowl",
        driveTimeMin: 7,
        recommendedOrder: "",
        isDraft: false,
        distanceMeters: 800,
        placeId: nil,
        provider: "fake",
        suggestions: nil,
        lat: nil,
        lng: nil,
        chainMatched: false,
        chainAsOf: nil
    ))
    .presentationDetents([.medium, .large])
    .presentationDragIndicator(.visible)
}

#Preview("Dark") {
    ScrollView {
        VStack(spacing: 20) {
            FoodOptionDeck(
                foodOptions: FakeData.dallasFoodOptions,
                bagFallbackOnly: false,
                placesUnavailable: false
            )
            FoodOptionDeck(
                foodOptions: [],
                bagFallbackOnly: false,
                placesUnavailable: true
            )
            FoodOptionDeck(
                foodOptions: [],
                bagFallbackOnly: true,
                placesUnavailable: false
            )
        }
        .padding(.vertical)
    }
    .preferredColorScheme(.dark)
}
