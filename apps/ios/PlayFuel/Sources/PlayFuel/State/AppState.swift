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

    // MARK: - Cached Envelope Access

    /// Exposes the cached PlanEnvelope for a tournament without triggering a network load.
    /// Used by delete confirmation dialogs to display accurate match / plan counts.
    func cachedPlanEnvelope(for tournamentId: UUID) -> PlanEnvelope? {
        planCache[tournamentId]
    }

    // MARK: - Optimistic Tournament List Mutations

    /// Optimistically removes a tournament from the loaded list before the API call fires.
    /// Returns `(tournament, originalIndex)` so the caller can restore on error.
    /// Returns nil if the list isn’t loaded or the tournament isn’t in the list.
    @discardableResult
    func optimisticRemoveTournament(id: UUID) -> (tournament: Tournament, index: Int)? {
        guard case .loaded(let list) = tournaments,
              let idx = list.firstIndex(where: { $0.id == id }) else { return nil }
        var updated = list
        let removed = updated.remove(at: idx)
        tournaments = .loaded(updated)
        return (removed, idx)
    }

    /// Restores a tournament to the loaded list at its original index.
    /// Used for error recovery after a failed optimistic delete.
    func restoreTournament(_ tournament: Tournament, at index: Int) {
        guard case .loaded(var list) = tournaments else { return }
        let safeIndex = min(index, list.count)
        list.insert(tournament, at: safeIndex)
        tournaments = .loaded(list)
    }

    // MARK: - Delete API Wrappers

    /// Calls the API to delete a tournament.
    /// Returns `true` on 204 (success) or 404 (already gone — spec §D.4 silent success).
    /// Returns `false` on any other error.
    func deleteTournamentViaAPI(id: UUID) async -> Bool {
        do {
            try await repository.deleteTournament(id: id)
            invalidatePlanCache(for: id)
            return true
        } catch APIError.notFound {
            // Already gone — treat as silent success per spec §D.4.
            invalidatePlanCache(for: id)
            return true
        } catch {
            return false
        }
    }

    /// Calls the API to delete a match.
    /// Returns `true` on 204 or 404 (silent success); `false` on any other error.
    func deleteMatchViaAPI(matchId: UUID, tournamentId: UUID) async -> Bool {
        do {
            try await repository.deleteMatch(tournamentId: tournamentId, matchId: matchId)
            invalidatePlanCache(for: tournamentId)
            return true
        } catch APIError.notFound {
            invalidatePlanCache(for: tournamentId)
            return true
        } catch {
            return false
        }
    }

    // MARK: - Match Done Toggle (match-done-state-cards spec §E.6 + §J)

    /// Toggle the done state of the given match:
    ///   1. Derive new isDone (toggle current value)
    ///   2. Optimistically update currentPlanEnvelope (instant chip/deck response)
    ///   3. PUT /v1/tournaments/{tid}/matches/{mid}
    ///   4. On success: regenerate plan (server state wins)
    ///   5. On failure: revert optimistic update; caller shows error toast
    ///
    /// Returns `true` on success so TournamentDashboardView can show a toast on failure.
    @discardableResult
    func toggleMatchDone(matchId: UUID, tournamentId: UUID) async -> Bool {
        guard case .loaded(let envelope) = currentPlanEnvelope,
              let plan = envelope.plan(for: matchId) else { return false }
        let newIsDone = !plan.isDone

        // Step 2: instant optimistic update (no spinner)
        optimisticallySetIsDone(matchId: matchId, isDone: newIsDone)

        // Step 3: API call
        let success = await repository.updateMatchDone(
            matchId: matchId, tournamentId: tournamentId, isDone: newIsDone
        )

        if success {
            // Step 4: refresh plan from server
            await generatePlan(for: tournamentId)
        } else {
            // Step 5: revert optimistic update
            optimisticallySetIsDone(matchId: matchId, isDone: !newIsDone)
        }
        return success
    }

    /// Mutates `currentPlanEnvelope` in-place to flip `isDone` on the matching plan.
    /// Rebuilds both singlesPlans and doublesPlans arrays with a value-copy of the
    /// modified Plan (Plan is a struct — copy-on-write semantics via a new init).
    private func optimisticallySetIsDone(matchId: UUID, isDone: Bool) {
        guard case .loaded(let envelope) = currentPlanEnvelope else { return }

        func updatePlan(_ plan: Plan) -> Plan {
            guard plan.matchId == matchId else { return plan }
            return Plan(
                id: plan.id,
                planId: plan.planId,
                tournamentId: plan.tournamentId,
                generatedAt: plan.generatedAt,
                warnings: plan.warnings,
                scenarioPlans: plan.scenarioPlans,
                weather: plan.weather,
                foodOptions: plan.foodOptions,
                timeline: plan.timeline,
                bagFallbackOnly: plan.bagFallbackOnly,
                llmSummary: plan.llmSummary,
                matchType: plan.matchType,
                matchId: plan.matchId,
                nextAction: plan.nextAction,
                scheduledStart: plan.scheduledStart,
                isDone: isDone,
                placesUnavailable: plan.placesUnavailable  // OQ-FOOD-EMPTY-1: preserve existing value
            )
        }

        let updated = PlanEnvelope(
            singlesPlans: envelope.singlesPlans.map(updatePlan),
            doublesPlans: envelope.doublesPlans.map(updatePlan)
        )
        currentPlanEnvelope = .loaded(updated)
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
