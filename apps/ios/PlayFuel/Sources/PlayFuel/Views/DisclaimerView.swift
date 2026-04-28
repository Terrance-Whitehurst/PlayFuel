import SwiftUI

/// §A User Disclaimer screen.
///
/// Reachable from: SignInView "usage guidelines" link, TournamentDashboardView footer,
/// and (Phase 2) Settings screen.
///
/// Displays `HardCodedStrings.userDisclaimer` VERBATIM.
/// NEVER modifies or re-phrases this text.
struct DisclaimerView: View {

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // §A disclaimer — verbatim
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Usage Guidelines", systemImage: "info.circle.fill")
                            .font(.headline)

                        Text(HardCodedStrings.userDisclaimer)
                            .font(.body)
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(16)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    // §B heat emergency — verbatim
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Heat & Illness Emergency", systemImage: "cross.circle.fill")
                            .font(.headline)
                            .foregroundStyle(.red)

                        Text(HardCodedStrings.heatEmergencyText)
                            .font(.body)
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)

                        Text("⚠️ DRAFT — OQ-11: This wording is pending attorney review before public launch.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(16)
                    .background(Color.red.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    // Prohibited claims note (§C)
                    VStack(alignment: .leading, spacing: 10) {
                        Label("What This App Does NOT Do", systemImage: "xmark.shield.fill")
                            .font(.headline)
                            .foregroundStyle(.orange)

                        let prohibitedExamples = [
                            "Claim that any food or drink will prevent cramps or heat illness.",
                            "Provide medical diagnoses or tell you an injury is minor.",
                            "Guarantee performance outcomes.",
                            "Replace your player's coach, physician, athletic trainer, or dietitian."
                        ]

                        ForEach(prohibitedExamples, id: \.self) { item in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.orange)
                                    .font(.caption)
                                    .padding(.top, 3)
                                Text(item)
                                    .font(.caption)
                            }
                        }
                    }
                    .padding(16)
                    .background(Color.orange.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    Spacer(minLength: 40)
                }
                .padding(16)
            }
            .navigationTitle("Disclaimer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") { dismiss() }
                }
            }
            .background(Color(.systemGroupedBackground))
        }
    }
}

#Preview {
    DisclaimerView()
}

#Preview("Dark") {
    DisclaimerView()
        .preferredColorScheme(.dark)
}
