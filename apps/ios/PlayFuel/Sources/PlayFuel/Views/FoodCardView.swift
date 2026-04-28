import SwiftUI

/// US-08 — Nearby food options card.
///
/// Kept for previews; not rendered on the dashboard as of FOOD_DECK_AND_MAP_V1.
/// The dashboard uses `FoodOptionDeck` (scroll-snap cards + detail sheets).
///
/// Renders a list of FoodOption items from the plan.
/// Falls back to bag-food content (§F.4 / §H.3) when `foodOptions` is empty.
/// Does NOT make performance claims — per SAFETY_DISCLAIMERS §C / US-08 AC.
struct FoodCardView: View {

    let foodOptions: [FoodOption]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {

            // Header
            Label("Nearby Food Options", systemImage: "fork.knife.circle.fill")
                .font(.headline)
                .padding(.horizontal, 16)
                .padding(.top, 16)

            if foodOptions.isEmpty {
                // Bag-food fallback per §F.4 / §H.3
                bagFoodFallback
            } else {
                // Option list
                VStack(spacing: 0) {
                    ForEach(Array(foodOptions.enumerated()), id: \.element.id) { index, option in
                        FoodOptionRow(option: option)
                        if index < foodOptions.count - 1 {
                            Divider()
                                .padding(.leading, 16)
                        }
                    }
                }
            }

            // Safety note — must not claim food prevents anything (§C)
            Text("If your player has food allergies, intolerances, or dietary restrictions, consult the relevant professional before following these suggestions.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal, 16)
    }

    // MARK: - Bag-Food Fallback (§F.4 / §H.3)

    private var bagFoodFallback: some View {
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

// MARK: - Food Option Row

private struct FoodOptionRow: View {

    let option: FoodOption

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(option.name)
                        .font(.subheadline.weight(.semibold))

                    Text(categoryLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                HStack(spacing: 4) {
                    Image(systemName: "car")
                        .font(.caption)
                    Text("~\(DurationFormatting.friendly(minutes: option.driveTimeMin ?? 0))")
                        .font(.caption.weight(.medium))
                }
                .foregroundStyle(.secondary)
            }

            // Recommended order
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: "text.quote")
                    .font(.caption2)
                    .foregroundStyle(.green)
                    .padding(.top, 2)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Suggested order")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(option.recommendedOrder)
                        .font(.caption)
                        .foregroundStyle(.primary)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private var categoryLabel: String {
        switch option.category {
        case "fast_casual_bowl":   return "Fast casual bowl"
        case "sandwich_shop":      return "Sandwich shop"
        case "grocery_prepared":   return "Grocery prepared"
        case "breakfast_cafe":     return "Breakfast café"
        default:                   return option.category.replacingOccurrences(of: "_", with: " ")
        }
    }
}

#Preview {
    ScrollView {
        VStack(spacing: 20) {
            FoodCardView(foodOptions: FakeData.dallasFoodOptions)
            FoodCardView(foodOptions: [])
        }
        .padding(.vertical)
    }
}

#Preview("Dark") {
    ScrollView {
        VStack(spacing: 20) {
            FoodCardView(foodOptions: FakeData.dallasFoodOptions)
            FoodCardView(foodOptions: [])
        }
        .padding(.vertical)
    }
    .preferredColorScheme(.dark)
}
