import SwiftUI

/// 1-line heat emergency strip. Rendered at position #0 in `envelopeContent()`
/// when `plan.weather.extremeHeatRisk == true`, ABOVE the Singles/Doubles picker.
///
/// Honoring both the user's "don't overload the dashboard" ask AND the safety
/// requirement that extreme-heat warnings are never opt-in (HEADER_BUBBLES_V1.md §C):
///   - Invisible on normal days (zero screen tax)
///   - Full-width red bar, impossible to miss when active
///   - One tap → `HeatGuidanceSheet` with verbatim §B + §A text
///
/// `EmergencyBanner.swift` is NOT modified — it remains available for other
/// surfaces (e.g. `DisclaimerView`) and for `#Preview` usage.
///
/// SAFETY NOTE: This strip triggers on `plan.weather.extremeHeatRisk`, which is
/// derived from the Plan model — NOT from the WeatherCard's `isExpanded` state.
/// Collapsing or ignoring the weather bubble cannot suppress this strip.
///
/// ⚠️ OQ-11: Pending attorney review — wording in `HeatGuidanceSheet` must not
///    be treated as legally cleared before App Store submission.
///
/// HEADER_BUBBLES_V1.md §F.6
struct EmergencyStrip: View {

    @State private var sheetShown = false

    var body: some View {
        Button {
            sheetShown = true
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.subheadline.weight(.semibold))

                Text("Extreme heat — tap for guidance")
                    .font(.subheadline.weight(.semibold))

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .opacity(0.8)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity)
            .background(Color.red)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Extreme heat warning. Tap for guidance.")
        .accessibilityAddTraits(.isButton)
        .sheet(isPresented: $sheetShown) {
            HeatGuidanceSheet()
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }
}

#Preview {
    VStack(spacing: 0) {
        EmergencyStrip()
        Spacer()
    }
}

#Preview("Dark") {
    VStack(spacing: 0) {
        EmergencyStrip()
        Spacer()
    }
    .preferredColorScheme(.dark)
}
