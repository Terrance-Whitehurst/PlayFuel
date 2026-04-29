import SwiftUI

/// Profile menu — quick-access popout for app-level actions.
///
/// Presented from the profile button (person.crop.circle.fill) in the nav-bar toolbar
/// on TournamentListView and TournamentDashboardView.
///
/// Rows:
///   1. Settings (live) — drills into SettingsView which holds the Appearance toggle
///   2. Dashboard (live) — Tournament History calendar with dummy data
///   3. Players (live) — Opponent scouting roster (PLAYER_SCOUTING_V1.md §E.1)
struct ProfileMenuSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var showSettings  = false
    @State private var showDashboard = false
    @State private var showPlayers   = false

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

                // Row 2: Dashboard (live — tournament history calendar)
                Button {
                    showDashboard = true
                } label: {
                    HStack {
                        Image(systemName: "square.grid.2x2.fill")
                            .foregroundStyle(.indigo)
                            .frame(width: 28)
                        Text("Dashboard")
                            .foregroundStyle(.primary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                // Row 3: Players — opponent scouting roster (PLAYER_SCOUTING_V1.md §E.1)
                Button {
                    showPlayers = true
                } label: {
                    HStack {
                        Image(systemName: "person.2.fill")
                            .foregroundStyle(.green)
                            .frame(width: 28)
                        Text("Players")
                            .foregroundStyle(.primary)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
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
            .sheet(isPresented: $showDashboard) {
                DashboardView()
                    .presentationDetents([.large])
                    .presentationDragIndicator(.visible)
            }
            .sheet(isPresented: $showPlayers) {
                PlayerListView()
                    .presentationDetents([.large])
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
