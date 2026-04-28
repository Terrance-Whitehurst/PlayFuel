import SwiftUI

/// Sheet presenting verbatim heat emergency guidance and the usage disclaimer.
/// Opened by tapping `EmergencyStrip` when `extreme_heat_risk == true`.
///
/// VERBATIM RULE: Both strings below are sourced EXCLUSIVELY from `HardCodedStrings`.
/// Do NOT modify, paraphrase, summarise, or reformat either string.
/// Changes require updating `HardCodedStrings.swift` first (SAFETY_DISCLAIMERS.md §H).
///
/// ⚠️ OQ-11: Pending attorney review — do not treat wording as legally cleared
///    before App Store submission. Surface ONLY through this file and `HardCodedStrings`.
///
/// HEADER_BUBBLES_V1.md §B (Heat Guidance Sheet) + §F.5
struct HeatGuidanceSheet: View {

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // MARK: §B Heat Emergency Text — VERBATIM, never paraphrased
                    // Source: HardCodedStrings.heatEmergencyText (SAFETY_DISCLAIMERS.md §B v1.1)
                    Text(HardCodedStrings.heatEmergencyText)
                        .font(.body)
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Divider()

                    // MARK: §A User Disclaimer — VERBATIM, never paraphrased
                    // Source: HardCodedStrings.userDisclaimer (SAFETY_DISCLAIMERS.md §A)
                    Text(HardCodedStrings.userDisclaimer)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(20)
            }
            .navigationTitle("Heat Emergency Guidance")
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
    HeatGuidanceSheet()
}

#Preview("Dark") {
    HeatGuidanceSheet()
        .preferredColorScheme(.dark)
}
