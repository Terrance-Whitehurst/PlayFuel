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
        // Glassmorphic red — regularMaterial + red 85% tint preserves white-text
        // WCAG AA contrast while adding the glass blur layer. Safety-critical text
        // legibility is unchanged; red prominence maintained at 0.85 opacity.
        .background {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(.regularMaterial)
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.red.opacity(0.85))
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [.white.opacity(0.30), .white.opacity(0.05)],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            }
        }
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
