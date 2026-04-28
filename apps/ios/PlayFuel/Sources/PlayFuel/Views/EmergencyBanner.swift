import SwiftUI

/// §B Heat Emergency Banner.
///
/// Renders at the top of TournamentDashboardView when
/// `weather.extremeHeatRisk == true` (§E.2: very_hot OR (hot AND humid)).
///
/// Displays `HardCodedStrings.heatEmergencyText` VERBATIM.
/// NEVER modifies or re-phrases this text.
///
/// ⚠️ OQ-11: wording is pending attorney review — pre-launch blocker.
struct EmergencyBanner: View {

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text("❗")
                    .font(.title3)
                Text("HEAT EMERGENCY GUIDANCE")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(.white)
            }

            // §B verbatim — sourced from HardCodedStrings, never re-typed
            Text(HardCodedStrings.heatEmergencyText)
                .font(.caption)
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)

            Text("⚠️ DRAFT — OQ-11: Pending attorney review before public launch.")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.75))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.gradient)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }
}

#Preview {
    EmergencyBanner()
        .padding()
}

#Preview("Dark") {
    EmergencyBanner()
        .padding()
        .preferredColorScheme(.dark)
}
