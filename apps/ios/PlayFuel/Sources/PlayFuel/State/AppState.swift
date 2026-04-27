import Foundation
import Combine

/// Global app state injected as an environment object from PlayFuelApp.
/// Phase 3: replace `isAuthenticated` with real Supabase session tracking.
final class AppState: ObservableObject {

    // MARK: - Auth

    /// Phase 1: toggled by the fake SignInWithApple tap.
    /// Phase 2+: driven by Supabase session state.
    @Published var isAuthenticated: Bool = false

    // MARK: - Navigation

    /// The tournament currently selected for dashboard / timeline / plan views.
    @Published var selectedTournamentId: UUID? = nil

    // MARK: - Fake Sign-In (Phase 1 only)

    /// Called by SignInView. Phase 3: replace with real Apple token → Supabase exchange.
    func fakeSignIn() {
        isAuthenticated = true
    }

    func signOut() {
        isAuthenticated = false
        selectedTournamentId = nil
    }
}
