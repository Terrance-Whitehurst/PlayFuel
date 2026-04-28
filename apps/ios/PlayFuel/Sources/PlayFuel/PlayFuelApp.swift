import SwiftUI

// MARK: - Appearance Mode

/// User-selectable appearance override.
/// Stored in UserDefaults so it persists across launches.
/// Default: .system (honours iOS Display & Brightness setting).
enum AppearanceMode: String, CaseIterable {
    case system = "system"
    case light  = "light"
    case dark   = "dark"

    var displayName: String {
        switch self {
        case .system: return "System"
        case .light:  return "Light"
        case .dark:   return "Dark"
        }
    }

    /// Maps to SwiftUI's `ColorScheme?`. `nil` means "follow the system".
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light:  return .light
        case .dark:   return .dark
        }
    }
}

@main
struct PlayFuelApp: App {

    @StateObject private var appState: AppState

    /// Persisted appearance preference. Defaults to system.
    @AppStorage("appearance_mode") private var appearanceModeRaw: String = AppearanceMode.system.rawValue

    private var activeColorScheme: ColorScheme? {
        AppearanceMode(rawValue: appearanceModeRaw)?.colorScheme
    }

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
                .preferredColorScheme(activeColorScheme)
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
