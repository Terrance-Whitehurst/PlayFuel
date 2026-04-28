import SwiftUI

/// Profile menu — quick-access popout for app-level actions.
///
/// Presented from the profile button (person.crop.circle.fill) in the nav-bar toolbar
/// on TournamentListView and TournamentDashboardView.
///
/// Rows:
///   1. Settings (live) — drills into SettingsView which holds the Appearance toggle
///   2. Dashboard (placeholder) — the next planned feature; shown disabled with "Coming soon"
struct ProfileMenuSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            List {
                // Row 1: Settings (live)
                Button {
                    showSettings = true
                } label: {
                    HStack {
                        Image(systemName: "gearshape.fill")
                            .foregroundStyle(.blue)
                            .frame(width: 28)
                        Text("Settings")
                            .foregroundStyle(.primary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                // Row 2: Dashboard placeholder (next feature)
                HStack {
                    Image(systemName: "square.grid.2x2.fill")
                        .foregroundStyle(.gray)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Dashboard")
                            .foregroundStyle(.secondary)
                        Text("Coming soon")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    Spacer()
                }
                .opacity(0.6)
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
        }
    }
}

#Preview {
    ProfileMenuSheet()
}

#Preview("Dark") {
    ProfileMenuSheet()
        .preferredColorScheme(.dark)
}
