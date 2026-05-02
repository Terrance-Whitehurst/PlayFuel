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

    /// Date formatter for tournament date fields ("yyyy-MM-dd" strings, UTC).
    /// Static to avoid re-allocating DateFormatter on every `createTournament` call.
    /// DateFormatter is expensive to construct (locale resolution, calendar setup).
    private static let tournamentDateFormatter: DateFormatter = {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(identifier: "UTC")
        return fmt
    }()

    /// Encoder for POST request bodies.
    /// .convertToSnakeCase maps Swift camelCase property names → API snake_case field names.
    /// .iso8601 handles Date → "2026-04-27T09:00:00Z" (accepted by FastAPI `datetime` fields).
    private let postEncoder: JSONEncoder = {
        let enc = JSONEncoder()
        enc.keyEncodingStrategy = .convertToSnakeCase
        enc.dateEncodingStrategy = .iso8601
        return enc
    }()

    // MARK: - Performance Instrumentation

    /// Lightweight call-site timer. Printed to debug console only; never included in
    /// release builds. Helps diagnose network latency per hot path.
    ///
    /// Usage:
    ///   let t = Repository.clock()
    ///   defer { Repository.lap(t, label: "myMethod") }
    static func clock() -> Date { Date() }
    static func lap(_ start: Date, label: String) {
        #if DEBUG
        let ms = Int(Date().timeIntervalSince(start) * 1_000)
        print("[PlayFuel Perf] \(label): \(ms) ms")
        #endif
    }

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
        let t = Repository.clock()
        defer { Repository.lap(t, label: "fetchTournaments") }
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
    ///
    /// Venue address fields are optional (nil for legacy callers / tests). When present
    /// they are sent to the API and persisted on the tournament row (columns exist per
    /// migration 0002; venue_place_id added by migration 0012).
    func createTournament(
        name: String,
        venueName: String,
        venueAddress: String? = nil,
        venueCity: String? = nil,
        venueRegion: String? = nil,
        venuePostal: String? = nil,
        venuePlaceId: String? = nil,
        venueLat: Double? = nil,
        venueLng: Double? = nil,
        startDate: Date,
        endDate: Date,
        timeZone: String
    ) async throws -> Tournament {
        let t = Repository.clock()
        defer { Repository.lap(t, label: "createTournament") }
        let dateFmt = Repository.tournamentDateFormatter
        let body = TournamentCreateRequest(
            name: name,
            venueName: venueName,
            venueAddress: venueAddress,
            venueCity: venueCity,
            venueRegion: venueRegion,
            venuePostal: venuePostal,
            venuePlaceId: venuePlaceId,
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
    ///
    /// Phase 7: `matchType` and `doublesFormat` added per DOUBLES_SPEC_V1.md §A.2.
    /// Player Scouting: `opponentPlayerId` added per PLAYER_SCOUTING_V1.md §E.4.
    func createMatch(
        tournamentId: UUID,
        scheduledStart: Date,
        estimatedDurationMinutes: Int,
        roundLabel: String?,
        opponentLabel: String?,
        courtLabel: String?,
        estimatedNextMatchTime: Date?,
        displayOrder: Int,
        matchType: MatchType = .singles,
        doublesFormat: DoublesFormat? = nil,
        opponentPlayerId: UUID? = nil
    ) async throws -> Match {
        let body = MatchCreateRequest(
            scheduledStart: scheduledStart,
            estimatedDurationMinutes: estimatedDurationMinutes,
            roundLabel: roundLabel,
            opponentLabel: opponentLabel,
            courtLabel: courtLabel,
            displayOrder: displayOrder,
            format: matchType.rawValue,
            doublesFormat: doublesFormat?.rawValue,
            opponentPlayerId: opponentPlayerId
        )
        let bodyData = try postEncoder.encode(body)
        let dto = try await api.send(
            Endpoints.createMatch(baseURL: api.baseURL, tournamentId: tournamentId, body: bodyData),
            as: .snake,
            expecting: MatchDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Scouting Players (PLAYER_SCOUTING_V1.md §G items 11–13)

    /// List the current user's scouted players, ordered by updated_at DESC.
    func listPlayers() async throws -> [Player] {
        let dtos = try await api.send(
            Endpoints.listPlayers(baseURL: api.baseURL),
            as: .snake,
            expecting: [PlayerDTO].self
        )
        return dtos.map { $0.toModel() }
    }

    /// Create a new scouted player.
    func createPlayer(
        displayName: String,
        club: String? = nil,
        city: String? = nil,
        notesSummary: String? = nil
    ) async throws -> Player {
        let body = PlayerCreateRequest(
            displayName: displayName,
            club: club,
            city: city,
            notesSummary: notesSummary
        )
        let bodyData = try postEncoder.encode(body)
        let dto = try await api.send(
            Endpoints.createPlayer(baseURL: api.baseURL, body: bodyData),
            as: .snake,
            expecting: PlayerDTO.self
        )
        return dto.toModel()
    }

    /// Fetch a single player by ID.
    func getPlayer(id: UUID) async throws -> Player {
        let dto = try await api.send(
            Endpoints.getPlayer(baseURL: api.baseURL, id: id),
            as: .snake,
            expecting: PlayerDTO.self
        )
        return dto.toModel()
    }

    /// Update player metadata.
    func updatePlayer(
        id: UUID,
        displayName: String? = nil,
        club: String? = nil,
        city: String? = nil,
        notesSummary: String? = nil
    ) async throws -> Player {
        let body = PlayerUpdateRequest(
            displayName: displayName,
            club: club,
            city: city,
            notesSummary: notesSummary
        )
        let bodyData = try postEncoder.encode(body)
        let dto = try await api.send(
            Endpoints.updatePlayer(baseURL: api.baseURL, id: id, body: bodyData),
            as: .snake,
            expecting: PlayerDTO.self
        )
        return dto.toModel()
    }

    /// Delete a player and cascade all their notes.
    func deletePlayer(id: UUID) async throws {
        try await api.sendNoContent(
            Endpoints.deletePlayer(baseURL: api.baseURL, id: id)
        )
    }

    /// List notes for a player, newest-first.
    func listPlayerNotes(playerId: UUID) async throws -> [PlayerNote] {
        let dtos = try await api.send(
            Endpoints.listPlayerNotes(baseURL: api.baseURL, playerId: playerId),
            as: .snake,
            expecting: [PlayerNoteDTO].self
        )
        return dtos.map { $0.toModel() }
    }

    /// Add a new note to a player.
    func addPlayerNote(
        playerId: UUID,
        source: PlayerNoteSource,
        body: String,
        matchId: UUID? = nil
    ) async throws -> PlayerNote {
        let req = PlayerNoteCreateRequest(
            source: source.rawValue,
            body: body,
            matchId: matchId
        )
        let bodyData = try postEncoder.encode(req)
        let dto = try await api.send(
            Endpoints.addPlayerNote(baseURL: api.baseURL, playerId: playerId, body: bodyData),
            as: .snake,
            expecting: PlayerNoteDTO.self
        )
        return dto.toModel()
    }

    /// Edit a note (allowed within 24h window per spec; API returns 422 after).
    func editPlayerNote(playerId: UUID, noteId: UUID, body: String) async throws -> PlayerNote {
        let req = ["body": body]
        let bodyData = try JSONEncoder().encode(req)
        let dto = try await api.send(
            Endpoints.editPlayerNote(baseURL: api.baseURL, playerId: playerId, noteId: noteId, body: bodyData),
            as: .snake,
            expecting: PlayerNoteDTO.self
        )
        return dto.toModel()
    }

    /// Delete a single note.
    func deletePlayerNote(playerId: UUID, noteId: UUID) async throws {
        try await api.sendNoContent(
            Endpoints.deletePlayerNote(baseURL: api.baseURL, playerId: playerId, noteId: noteId)
        )
    }

    // MARK: - Post-Match Evaluation (POST_MATCH_EVAL_V1.md §G items 14–16)

    /// Fetch the post-match evaluation for a match. Returns nil when no evaluation
    /// has been created yet (API returns 404 in that case).
    func getMatchEvaluation(matchId: UUID) async throws -> MatchEvaluation? {
        do {
            let dto = try await api.send(
                Endpoints.getMatchEvaluation(baseURL: api.baseURL, matchId: matchId),
                as: .snake,
                expecting: MatchEvaluationDTO.self
            )
            return dto.toModel()
        } catch APIError.notFound {
            return nil
        }
    }

    /// Create or update (upsert) the post-match evaluation for a match.
    /// The API returns 201 on first creation, 200 on subsequent saves.
    /// The auto-player-note loop (services/post_match_sync.py) fires server-side.
    func saveMatchEvaluation(
        matchId: UUID,
        request: MatchEvaluationCreateRequest
    ) async throws -> MatchEvaluation {
        let bodyData = try postEncoder.encode(request)
        let dto = try await api.send(
            Endpoints.saveMatchEvaluation(baseURL: api.baseURL, matchId: matchId, body: bodyData),
            as: .snake,
            expecting: MatchEvaluationDTO.self
        )
        return dto.toModel()
    }

    /// Delete the post-match evaluation for a match (204 expected).
    /// Also removes the auto-created post_match player_note server-side.
    func deleteMatchEvaluation(matchId: UUID) async throws {
        try await api.sendNoContent(
            Endpoints.deleteMatchEvaluation(baseURL: api.baseURL, matchId: matchId)
        )
    }

    // MARK: - Tournament Feedback (phase7-feedback-spec.md §C)

    /// Fetch the caller's existing feedback for a tournament.
    /// Returns nil when no feedback has been submitted yet (API returns 404).
    func getFeedback(tournamentId: UUID) async throws -> TournamentFeedback? {
        do {
            let dto = try await api.send(
                Endpoints.getFeedback(baseURL: api.baseURL, tournamentId: tournamentId),
                as: .camel,
                expecting: TournamentFeedbackDTO.self
            )
            return dto.toModel()
        } catch APIError.notFound {
            return nil
        }
    }

    /// Submit (or update) feedback for a tournament.
    /// Returns the stored feedback row. Both 201 (create) and 200 (update)
    /// responses carry the same FeedbackResponse JSON shape.
    func submitFeedback(
        tournamentId: UUID,
        request: TournamentFeedbackCreateRequest
    ) async throws -> TournamentFeedback {
        let bodyData = try postEncoder.encode(request)
        let dto = try await api.send(
            Endpoints.submitFeedback(
                baseURL: api.baseURL,
                tournamentId: tournamentId,
                body: bodyData
            ),
            as: .camel,
            expecting: TournamentFeedbackDTO.self
        )
        return dto.toModel()
    }

    // MARK: - Plans

    /// Generate a plan for a tournament via the rules engine.
    ///
    /// Phase 8 (Nutrition-First IA): returns a `PlanEnvelope` with arrays of plans
    /// keyed by match type — one Plan per match in the tournament.
    ///
    /// HTTP 200 always (the backend returns 200 even for overrun scenarios per OQ-14/§G).
    func generatePlan(tournamentId: UUID) async throws -> PlanEnvelope {
        let t = Repository.clock()
        defer { Repository.lap(t, label: "generatePlan") }
        let dto = try await api.send(
            Endpoints.generatePlan(baseURL: api.baseURL, tournamentId: tournamentId),
            as: .camel,
            expecting: PlanEnvelopeDTO.self
        )
        return dto.toModel()
    }
}
