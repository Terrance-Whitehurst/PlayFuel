import SwiftUI

/// App settings sheet.
///
/// Initial scope: Appearance toggle (relocated from DisclaimerView in Profile-Button delegate).
/// Future sections: notifications, account, data / privacy.
///
/// Writes to the same `@AppStorage("appearance_mode")` key that
/// PlayFuelApp reads for `.preferredColorScheme()` on the root WindowGroup.
/// Key is intentionally identical — changing here takes effect immediately.
struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("appearance_mode") private var appearanceModeRaw: String = AppearanceMode.system.rawValue

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Appearance", selection: $appearanceModeRaw) {
                        ForEach(AppearanceMode.allCases, id: \.rawValue) { mode in
                            Text(mode.displayName).tag(mode.rawValue)
                        }
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text("Appearance")
                } footer: {
                    Text("Overrides your iOS Display & Brightness setting for this app only.")
                }

                // Future sections (notifications, account, etc.) go here.
            }
            .navigationTitle("Settings")
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
    SettingsView()
}

#Preview("Dark") {
    SettingsView()
        .preferredColorScheme(.dark)
}
