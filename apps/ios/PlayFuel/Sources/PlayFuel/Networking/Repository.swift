import Foundation

/// Single read-path facade over APIClient.
///
/// Returns canonical iOS Model types (Tournament, Plan, User, etc.) so views
/// remain structurally unchanged. DTOs in Networking/DTOs.swift do the wire-
/// format adaptation.
///
/// Hybrid plan strategy (Phase 1.5 — active until Tasks #7/#8 land):
///   REAL from API:  scenarioPlans, planId, generatedAt, warnings, heatEmergencyText
///   STUB from FakeData: weather, foodOptions, timeline
/// The splice boundary is marked `// PHASE 4/5 SPLICE` below.
@MainActor
final class Repository: ObservableObject {

    private let api: APIClient

    init(api: APIClient) {
        self.api = api
    }

    // MARK: - User

    /// Fetch the authenticated user's own record from GET /v1/me.
    func fetchMe() async throws -> User {
        let dto = try await api.send(
            Endpoints.me(baseURL: api.baseURL),
            as: .snake,
            expecting: UserDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Tournaments

    /// Fetch all tournaments for the current user (RLS-filtered).
    func fetchTournaments() async throws -> [Tournament] {
        let dtos = try await api.send(
            Endpoints.listTournaments(baseURL: api.baseURL),
            as: .snake,
            expecting: [TournamentDTO].self
        )
        return dtos.map { $0.toModel() }
    }

    /// Fetch a single tournament by ID.
    func fetchTournament(id: UUID) async throws -> Tournament {
        let dto = try await api.send(
            Endpoints.getTournament(baseURL: api.baseURL, id: id),
            as: .snake,
            expecting: TournamentDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Matches
    //
    // Returns raw MatchDTOs — mapping to iOS Match requires multi-row context
    // (next-match time string derived from index+1) and display-layer time
    // formatters that don't exist in Task #6. Views in Task #6 don't call
    // fetchMatches; this method is here for completeness and Phase 4+ wiring.

    /// Fetch all matches for a tournament, ordered by display_order / scheduled_start.
    func fetchMatches(tournamentId: UUID) async throws -> [MatchDTO] {
        try await api.send(
            Endpoints.listMatches(baseURL: api.baseURL, tournamentId: tournamentId),
            as: .snake,
            expecting: [MatchDTO].self
        )
    }

    // MARK: - Plans

    /// Generate a plan for a tournament via the rules engine, then assemble a
    /// hybrid `Plan` model splicing in FakeData for weather/food/timeline.
    ///
    /// HTTP 200 always (the backend returns 200 even for overrun scenarios per OQ-14/§G).
    func generatePlan(tournamentId: UUID) async throws -> Plan {
        let envelope = try await api.send(
            Endpoints.generatePlan(baseURL: api.baseURL, tournamentId: tournamentId),
            as: .camel,
            expecting: GeneratePlanResponseDTO.self
        )
        return assembleHybridPlan(core: envelope.plan, tournamentId: tournamentId)
    }

    // MARK: - Internal

    /// Assembles a full iOS `Plan` model from real API engine output + FakeData splices.
    ///
    /// - PHASE 4/5 SPLICE -
    /// `weather`, `foodOptions`, and `timeline` are sourced from FakeData until:
    ///   - Phase 4 (Task #7): real weather from classify_weather() + weather provider
    ///   - Phase 5 (Task #8): real food options from Places API
    ///
    /// Only the Dallas tournament UUID has FakeData; others fall back to safe defaults
    /// (dallasWeather + empty arrays). This is intentional — Phase 4 will replace
    /// the splice for all tournaments.
    private func assembleHybridPlan(core: PlanCoreDTO, tournamentId: UUID) -> Plan {
        // PHASE 4/5 SPLICE — replace these three assignments when Tasks #7/#8 land.
        let fakePlan   = FakeData.plan(for: tournamentId)
        let weather    = fakePlan?.weather    ?? FakeData.dallasWeather
        let foodOptions = fakePlan?.foodOptions ?? []
        let timeline   = fakePlan?.timeline   ?? []

        return Plan(
            id: core.planId,
            planId: core.planId.uuidString,
            tournamentId: core.tournamentId,
            generatedAt: core.generatedAt,
            warnings: core.warnings,
            scenarioPlans: core.scenarioPlans.map { $0.toModel() },
            weather: weather,
            foodOptions: foodOptions,
            timeline: timeline
        )
    }
}
