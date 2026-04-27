import Foundation
import Combine

// MARK: - LoadState

/// Generic wrapper for async data with idle / loading / loaded / failed semantics.
/// Used by AppState to drive conditional view rendering without booleans.
enum LoadState<T> {
    case idle
    case loading
    case loaded(T)
    case failed(String)   // user-facing error message
}

// MARK: - AppState

/// Global app state. Owns Repository + AuthService and exposes loadable data
/// for views via @Published LoadState wrappers.
///
/// Observes `AuthService.isSignedIn` via Combine so `RootView` routes between
/// `SignInView` and the main `NavigationStack` reactively.
@MainActor
final class AppState: ObservableObject {

    // MARK: - Auth

    /// Mirrors `AuthService.isSignedIn`. RootView switches on this.
    @Published var isAuthenticated: Bool

    // MARK: - Navigation

    /// Tournament currently selected for detail / dashboard views.
    @Published var selectedTournamentId: UUID? = nil

    // MARK: - Loadable Data

    @Published var tournaments: LoadState<[Tournament]> = .idle
    @Published var currentPlan: LoadState<Plan> = .idle

    // MARK: - Dependencies

    let repository: Repository
    let authService: AuthService

    private var cancellables: Set<AnyCancellable> = []

    // MARK: - Init

    init(repository: Repository, authService: AuthService) {
        self.repository  = repository
        self.authService = authService
        self.isAuthenticated = authService.isSignedIn

        // Mirror auth state changes to `isAuthenticated` so RootView reacts.
        authService.$isSignedIn
            .receive(on: DispatchQueue.main)
            .sink { [weak self] signedIn in
                self?.isAuthenticated = signedIn
            }
            .store(in: &cancellables)
    }

    // MARK: - Loaders

    /// Fetch the tournament list. Skips if already `.loaded` (cached per session).
    func loadTournaments() async {
        tournaments = .loading
        do {
            let list = try await repository.fetchTournaments()
            tournaments = .loaded(list)
        } catch {
            tournaments = .failed(
                (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            )
        }
    }

    /// Run the rules engine for a tournament and assemble the hybrid Plan.
    func generatePlan(for tournamentId: UUID) async {
        currentPlan = .loading
        do {
            let plan = try await repository.generatePlan(tournamentId: tournamentId)
            currentPlan = .loaded(plan)
        } catch {
            currentPlan = .failed(
                (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            )
        }
    }

    // MARK: - Sign Out

    func signOut() {
        authService.signOut()
        selectedTournamentId = nil
        tournaments = .idle
        currentPlan = .idle
    }
}
