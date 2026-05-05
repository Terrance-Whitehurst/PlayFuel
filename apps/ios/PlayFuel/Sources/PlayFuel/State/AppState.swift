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

    // Phase 7 — replaced `currentPlan: LoadState<Plan>` with the doubles-spec envelope.
    // Both singles and doubles plans are carried together; views resolve the active plan
    // using `currentPlanEnvelope.plan(for: selectedMatchType)`.
    @Published var currentPlanEnvelope: LoadState<PlanEnvelope> = .idle

    /// Which match type is currently selected on the dashboard segmented picker.
    /// Used for the Singles | Doubles type-level picker when hasBothTypes == true.
    /// Persisted in-session only (not UserDefaults). Defaults to .singles.
    @Published var selectedMatchType: MatchType = .singles

    /// The specific match ID selected in ScheduleStripView.
    /// Drives planContent — the dashboard renders the plan for this match.
    /// Set by AppState.defaultMatchId(from:now:) on envelope arrival.
    @Published var selectedMatchId: UUID? = nil

    // MARK: - Dependencies

    let repository: Repository
    let authService: AuthService

    private var cancellables: Set<AnyCancellable> = []

    // MARK: - Plan Cache
    //
    // Stores generated PlanEnvelopes keyed by tournament ID.
    // Cache hit → show plan instantly + trigger silent background refresh.
    // Cache miss → normal loading path (spinner).
    // Invalidated when: (a) a match is added to a tournament (plan is stale),
    //                   (b) user signs out (signOut() calls clearPlanCache()).
    //
    // Thread safety: AppState is @MainActor — all access is on the main actor.
    // TTL: session-scoped (no expiry). Invalidate explicitly on data changes.
    private var planCache: [UUID: PlanEnvelope] = [:]

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

    /// Run the rules engine for a tournament and populate `currentPlanEnvelope`.
    ///
    /// Phase 8 (Nutrition-First IA): generatePlan returns a PlanEnvelope with
    /// per-match plan arrays (one Plan per match). After the envelope arrives,
    /// `selectedMatchId` is anchored to the most actionable match.
    ///
    /// Perf (perf/measure-and-optimize): cache-first path.
    ///   - Cache HIT  → publish the stored envelope immediately (0 ms to first render),
    ///                  then silently refresh in the background and update when done.
    ///   - Cache MISS → normal loading path (spinner until network responds).
    ///
    /// Rollback / error on background refresh: silent. The user already sees a valid
    /// cached plan. We do NOT replace a good loaded state with a failed state from a
    /// background refresh. Log to debug console only.
    func generatePlan(for tournamentId: UUID) async {
        if let cached = planCache[tournamentId] {
            // Cache HIT — show immediately, no spinner.
            currentPlanEnvelope = .loaded(cached)
            selectedMatchId = defaultMatchId(from: cached)
            // Background refresh — update the cache + UI if the refresh succeeds.
            Task {
                do {
                    let fresh = try await repository.generatePlan(tournamentId: tournamentId)
                    planCache[tournamentId] = fresh
                    // Only update the UI if the user is still viewing this tournament.
                    if case .loaded = currentPlanEnvelope {
                        currentPlanEnvelope = .loaded(fresh)
                        selectedMatchId = defaultMatchId(from: fresh)
                    }
                } catch {
                    // Silent failure — keep the cached plan displayed.
                    #if DEBUG
                    print("[PlayFuel Perf] generatePlan background refresh failed for \(tournamentId): \(error)")
                    #endif
                }
            }
        } else {
            // Cache MISS — standard spinner path.
            currentPlanEnvelope = .loading
            do {
                let envelope = try await repository.generatePlan(tournamentId: tournamentId)
                planCache[tournamentId] = envelope
                currentPlanEnvelope = .loaded(envelope)
                // Anchor strip selection to the most actionable match.
                selectedMatchId = defaultMatchId(from: envelope)
            } catch {
                currentPlanEnvelope = .failed(
                    (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                )
            }
        }
    }

    /// Invalidate the cached plan for a specific tournament.
    /// Call this after adding a match to a tournament so the next `generatePlan(for:)`
    /// skips the cache and fetches a fresh plan that includes the new match.
    func invalidatePlanCache(for tournamentId: UUID) {
        planCache.removeValue(forKey: tournamentId)
    }

    /// Clear all cached plans. Called on sign-out so the next user starts clean.
    private func clearPlanCache() {
        planCache.removeAll()
    }

    // MARK: - Sign Out

    // MARK: - Match Selection Helper

    /// Returns the matchId to use as the default selection for a given envelope.
    /// Priority: next upcoming match → most-recently-completed → any plan.
    /// `now` is injectable for test determinism.
    func defaultMatchId(from envelope: PlanEnvelope, now: Date = .now) -> UUID? {
        envelope.nextUpcomingPlan(now: now)?.matchId ?? envelope.anyPlan?.matchId
    }

    // MARK: - Sign Out

    func signOut() {
        authService.signOut()
        selectedTournamentId = nil
        tournaments = .idle
        currentPlanEnvelope = .idle
        selectedMatchType = .singles
        selectedMatchId = nil
        clearPlanCache()
    }
}
