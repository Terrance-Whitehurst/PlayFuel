import Foundation

/// Single read-path facade over APIClient.
///
/// Returns canonical iOS Model types (Tournament, Plan, User, etc.) so views
/// remain structurally unchanged. DTOs in Networking/DTOs.swift do the wire-
/// format adaptation.
///
/// Phase 5 (April 2026): Hybrid splice retired — `Repository` now consumes the
/// real API response directly for weather, timeline, and food options.
/// `FakeData` remains in the build target for SwiftUI `#Preview` blocks only.
@MainActor
final class Repository: ObservableObject {

    private let api: APIClient

    /// Encoder for POST request bodies.
    /// .convertToSnakeCase maps Swift camelCase property names → API snake_case field names.
    /// .iso8601 handles Date → "2026-04-27T09:00:00Z" (accepted by FastAPI `datetime` fields).
    private let postEncoder: JSONEncoder = {
        let enc = JSONEncoder()
        enc.keyEncodingStrategy = .convertToSnakeCase
        enc.dateEncodingStrategy = .iso8601
        return enc
    }()

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

    // MARK: - Tournament Mutation

    /// Create a new tournament via POST /v1/tournaments.
    ///
    /// `startDate` and `endDate` are formatted as "yyyy-MM-dd" strings because the API's
    /// `TournamentCreate` Pydantic model declares them as `date` (not `datetime`) type.
    ///
    /// `timeZone` is presented in the iOS form for future use but is NOT in the current API
    /// Pydantic model — it is omitted from the encoded request body.
    func createTournament(
        name: String,
        venueName: String,
        venueLat: Double,
        venueLng: Double,
        startDate: Date,
        endDate: Date,
        timeZone: String
    ) async throws -> Tournament {
        let dateFmt = DateFormatter()
        dateFmt.dateFormat = "yyyy-MM-dd"
        dateFmt.timeZone = TimeZone(identifier: "UTC")
        let body = TournamentCreateRequest(
            name: name,
            venueName: venueName,
            venueLat: venueLat,
            venueLng: venueLng,
            startDate: dateFmt.string(from: startDate),
            endDate: dateFmt.string(from: endDate)
        )
        let bodyData = try postEncoder.encode(body)
        let dto = try await api.send(
            Endpoints.createTournament(baseURL: api.baseURL, body: bodyData),
            as: .snake,
            expecting: TournamentDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Match Mutation

    /// Create a new match via POST /v1/tournaments/{tid}/matches.
    ///
    /// `estimatedNextMatchTime` is collected by the iOS form for UX (pre-filling next match
    /// time) but is NOT a DB column — it is derived from match ordering. It is omitted from
    /// the encoded request body.
    func createMatch(
        tournamentId: UUID,
        scheduledStart: Date,
        estimatedDurationMinutes: Int,
        roundLabel: String?,
        opponentLabel: String?,
        courtLabel: String?,
        estimatedNextMatchTime: Date?,
        displayOrder: Int
    ) async throws -> Match {
        let body = MatchCreateRequest(
            scheduledStart: scheduledStart,
            estimatedDurationMinutes: estimatedDurationMinutes,
            roundLabel: roundLabel,
            opponentLabel: opponentLabel,
            courtLabel: courtLabel,
            displayOrder: displayOrder
        )
        let bodyData = try postEncoder.encode(body)
        let dto = try await api.send(
            Endpoints.createMatch(baseURL: api.baseURL, tournamentId: tournamentId, body: bodyData),
            as: .snake,
            expecting: MatchDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Plans

    /// Generate a plan for a tournament via the rules engine and return a full `Plan`
    /// mapped directly from the API response (weather, food options, and timeline
    /// are all real data as of Phase 5).
    ///
    /// HTTP 200 always (the backend returns 200 even for overrun scenarios per OQ-14/§G).
    func generatePlan(tournamentId: UUID) async throws -> Plan {
        let envelope = try await api.send(
            Endpoints.generatePlan(baseURL: api.baseURL, tournamentId: tournamentId),
            as: .camel,
            expecting: GeneratePlanResponseDTO.self
        )
        return envelope.plan.toModel()
    }
}
