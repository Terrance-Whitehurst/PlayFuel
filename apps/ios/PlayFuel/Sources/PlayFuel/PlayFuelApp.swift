import SwiftUI

@main
struct PlayFuelApp: App {

    @StateObject private var appState: AppState

    init() {
        // Wire the dependency graph at app launch.
        // AuthService → APIClient → Repository → AppState.
        let auth = AuthService()
        let api  = APIClient(authService: auth)
        let repo = Repository(api: api)
        _appState = StateObject(wrappedValue: AppState(repository: repo, authService: auth))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
        }
    }
}

// MARK: - Root Router

/// Routes between SignInView and the main NavigationStack based on auth state.
/// Reacts to `appState.isAuthenticated` which mirrors `AuthService.isSignedIn`.
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
