import SwiftUI

/// Dashboard header bubble row — Plan Summary, Weather, and Map bubbles.
///
/// Surfaces background context one tap deep, keeping the dashboard scroll
/// clean for actionable content (schedule strip, next action, food).
///
/// Each bubble opens a `.sheet` overlay with `.presentationDetents([.medium, .large])`.
/// This component has zero coupling to `EmergencyStrip` — the weather pill
/// state cannot affect safety banner rendering.
///
/// Layout:
///   [text.bubble.fill]  [cloud/sun icon + "88°" badge]  [map.fill]  Spacer()
///
/// HEADER_BUBBLES_V1.md §F.2
/// FOOD_DECK_AND_MAP_V1.md §I-6 — `tournament: Tournament` added for Map bubble.
struct HeaderBubbleRow: View {

    let plan: Plan
    let tournament: Tournament

    @State private var planSheetShown    = false
    @State private var weatherSheetShown = false
    @State private var mapSheetShown     = false

    var body: some View {
        HStack(spacing: 16) {
            // Plan Summary bubble — only rendered when llmSummary is available
            if plan.llmSummary != nil {
                HeaderBubble(
                    systemImage: "text.bubble.fill",
                    label: "Today's Plan",
                    action: { planSheetShown = true }
                )
            }

            // Weather bubble — always rendered (plan.weather is non-optional)
            HeaderBubble(
                systemImage: weatherSymbol(for: plan.weather),
                label: "Current Conditions",
                badge: "\(Int(plan.weather.tempF.rounded()))°",
                action: { weatherSheetShown = true }
            )

            // Map bubble — always rendered (tournament coords default to 0 when absent)
            HeaderBubble(
                systemImage: "map.fill",
                label: "Venue map",
                action: { mapSheetShown = true }
            )

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        // Plan Summary sheet
        .sheet(isPresented: $planSheetShown) {
            if let summary = plan.llmSummary {
                PlanSummarySheet(explanation: summary)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
        }
        // Weather sheet
        .sheet(isPresented: $weatherSheetShown) {
            WeatherSheet(weather: plan.weather)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        // Map sheet — FOOD_DECK_AND_MAP_V1.md §D
        .sheet(isPresented: $mapSheetShown) {
            VenueMapSheet(tournament: tournament, foodOptions: plan.foodOptions)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    // MARK: - Helpers

    /// Maps active weather flags to a condition-appropriate SF Symbol.
    /// Checks in priority order: rain → extreme heat → hot → cold → default.
    ///
    /// NOTE: WeatherSnapshot uses `flags: [WeatherFlag]` (enum array), NOT
    /// individual boolean flag properties. Use `.contains()` not `.flagXxx`.
    private func weatherSymbol(for weather: WeatherSnapshot) -> String {
        if weather.flags.contains(.rain_risk) { return "cloud.rain.fill" }
        if weather.flags.contains(.very_hot)  { return "thermometer.sun.fill" }
        if weather.flags.contains(.hot)        { return "sun.max.fill" }
        if weather.flags.contains(.cold)       { return "thermometer.snowflake" }
        return "cloud.sun.fill"
    }
}

#Preview {
    HeaderBubbleRow(plan: FakeData.dallasPlan, tournament: FakeData.dallasTournament)
        .padding()
}

#Preview("Dark") {
    HeaderBubbleRow(plan: FakeData.dallasPlan, tournament: FakeData.dallasTournament)
        .padding()
        .preferredColorScheme(.dark)
}
