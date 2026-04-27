import SwiftUI

@main
struct PlayFuelApp: App {

    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
        }
    }
}

// MARK: - Root Router

/// Switches between SignInView and the main NavigationStack based on auth state.
private struct RootView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        if appState.isAuthenticated {
            NavigationStack {
                TournamentListView()
            }
        } else {
            SignInView()
        }
    }
}
