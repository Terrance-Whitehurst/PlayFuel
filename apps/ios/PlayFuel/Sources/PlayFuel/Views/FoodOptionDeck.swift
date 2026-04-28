import SwiftUI

/// Scroll-snap horizontal deck of nearby food option cards.
///
/// Replaces the inline `FoodCardView` list on the dashboard per
/// FOOD_DECK_AND_MAP_V1.md §B (scroll-snap pattern, iOS 17+).
///
/// Layout:
///   Section header → [Card 280×170] [Card 280×170] ... (30+pt peek of next)
///
/// - Tap any card → `FoodOptionDetailSheet` (structured suggestions, "Open in Maps")
/// - Empty / bag-fallback → single full-width orange card with verbatim `HardCodedStrings.bagFoodFallback`
/// - Uses `ScrollView(.horizontal)` + `.scrollTargetBehavior(.viewAligned)` (iOS 17+)
///
/// FOOD_DECK_AND_MAP_V1.md §B · §F.9
struct FoodOptionDeck: View {

    let foodOptions: [FoodOption]
    let bagFallbackOnly: Bool

    @State private var selectedOption: FoodOption? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {

            // Section header
            Label("Nearby Food Options", systemImage: "fork.knife.circle.fill")
                .font(.headline)
                .padding(.horizontal, 16)

            if foodOptions.isEmpty || bagFallbackOnly {
                // Bag-food fallback — verbatim §H.3 per FOOD_DECK_AND_MAP_V1.md §B.4
                bagFallbackCard
            } else {
                // Scroll-snap deck
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 12) {
                        ForEach(foodOptions) { option in
                            Button {
                                selectedOption = option
                            } label: {
                                FoodOptionCard(option: option)
                                    .frame(width: 280, height: 170)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .scrollTargetLayout()
                    .padding(.horizontal, 16)
                }
                .scrollTargetBehavior(.viewAligned)
            }
        }
        .sheet(item: $selectedOption) { option in
            FoodOptionDetailSheet(option: option)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
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
private struct FoodOptionCard: View {

    let option: FoodOption

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {

            // Name + DRAFT badge
            HStack(alignment: .top) {
                Text(option.name)
                    .font(.headline)
                    .lineLimit(2)
                Spacer(minLength: 4)
                if option.isDraft {
                    Text("DRAFT")
                        .font(.caption2.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(.systemFill), in: Capsule())
                }
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

            // Tap affordance
            Text("Tap for suggestions →")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.08), radius: 6, x: 0, y: 2)
    }

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
}

#Preview {
    ScrollView {
        VStack(spacing: 20) {
            FoodOptionDeck(foodOptions: FakeData.dallasFoodOptions, bagFallbackOnly: false)
            FoodOptionDeck(foodOptions: [], bagFallbackOnly: true)
        }
        .padding(.vertical)
    }
}

#Preview("Dark") {
    ScrollView {
        VStack(spacing: 20) {
            FoodOptionDeck(foodOptions: FakeData.dallasFoodOptions, bagFallbackOnly: false)
            FoodOptionDeck(foodOptions: [], bagFallbackOnly: true)
        }
        .padding(.vertical)
    }
    .preferredColorScheme(.dark)
}
