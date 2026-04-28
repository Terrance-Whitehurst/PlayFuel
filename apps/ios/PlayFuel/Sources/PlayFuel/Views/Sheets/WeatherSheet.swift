import SwiftUI

/// Sheet presenting the full weather card.
/// Opened by tapping the weather bubble in `HeaderBubbleRow`.
///
/// Embeds `WeatherCardView(weather:, compact: false)` directly — no duplication
/// of weather card logic. The existing full card renders unchanged inside the sheet.
///
/// SAFETY NOTE: This sheet is purely informational. The `EmergencyStrip` (and
/// the `HeatGuidanceSheet` it opens) is the authoritative surface for §B heat
/// emergency text. This sheet shows temperature/flags/adjustments only.
///
/// HEADER_BUBBLES_V1.md §B (Weather Sheet) + §F.4
struct WeatherSheet: View {

    let weather: WeatherSnapshot

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                WeatherCardView(weather: weather, compact: false)
                    .padding(.vertical, 16)
            }
            .navigationTitle("Conditions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    WeatherSheet(weather: FakeData.dallasWeather)
}

#Preview("Dark") {
    WeatherSheet(weather: FakeData.dallasWeather)
        .preferredColorScheme(.dark)
}
