import Foundation

/// Typed URL + request builders for every PlayFuel API endpoint.
/// Coverage parity with `apps/api/README.md` endpoint inventory (18 endpoints).
///
/// All builders are pure functions — no networking, no state. Each returns a
/// `URLRequest` pre-configured with method, path, and (where needed) body.
/// `APIClient` injects the `Authorization: Bearer` header at send time.
enum Endpoints {

    // MARK: - Health (no auth)

    /// GET /healthz — liveness + rules version.
    static func healthz(baseURL: URL) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("healthz"))
    }

    // MARK: - Me

    /// GET /v1/me — current authenticated user record.
    static func me(baseURL: URL) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/me"))
    }

    // MARK: - Tournaments

    /// GET /v1/tournaments — list user's tournaments (RLS-filtered).
    static func listTournaments(baseURL: URL) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/tournaments"))
    }

    /// GET /v1/tournaments/{id} — fetch single tournament.
    static func getTournament(baseURL: URL, id: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/tournaments/\(id.uuidString)"))
    }

    /// POST /v1/tournaments — create tournament.
    /// Not called from any view in Task #6 (create flow is a later task).
    static func createTournament(baseURL: URL, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/tournaments"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// PUT /v1/tournaments/{id} — update tournament.
    static func updateTournament(baseURL: URL, id: UUID, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/tournaments/\(id.uuidString)"))
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// DELETE /v1/tournaments/{id} — delete tournament.
    static func deleteTournament(baseURL: URL, id: UUID) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/tournaments/\(id.uuidString)"))
        req.httpMethod = "DELETE"
        return req
    }

    // MARK: - Player Profiles

    /// GET /v1/player-profiles — list profiles.
    static func listPlayerProfiles(baseURL: URL) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/player-profiles"))
    }

    /// POST /v1/player-profiles — create profile.
    static func createPlayerProfile(baseURL: URL, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/player-profiles"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// GET /v1/player-profiles/{id} — fetch profile.
    static func getPlayerProfile(baseURL: URL, id: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/player-profiles/\(id.uuidString)"))
    }

    /// PUT /v1/player-profiles/{id} — update profile.
    static func updatePlayerProfile(baseURL: URL, id: UUID, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/player-profiles/\(id.uuidString)"))
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// DELETE /v1/player-profiles/{id} — delete profile (204).
    static func deletePlayerProfile(baseURL: URL, id: UUID) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/player-profiles/\(id.uuidString)"))
        req.httpMethod = "DELETE"
        return req
    }

    // MARK: - Matches

    /// GET /v1/tournaments/{tid}/matches — list matches.
    static func listMatches(baseURL: URL, tournamentId: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent("v1/tournaments/\(tournamentId.uuidString)/matches"))
    }

    /// GET /v1/tournaments/{tid}/matches/{mid} — fetch single match.
    static func getMatch(baseURL: URL, tournamentId: UUID, matchId: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/matches/\(matchId.uuidString)"
        ))
    }

    /// POST /v1/tournaments/{tid}/matches — create match.
    static func createMatch(baseURL: URL, tournamentId: UUID, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/matches"
        ))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// PUT /v1/tournaments/{tid}/matches/{mid} — update match.
    static func updateMatch(baseURL: URL, tournamentId: UUID, matchId: UUID, body: Data) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/matches/\(matchId.uuidString)"
        ))
        req.httpMethod = "PUT"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    /// DELETE /v1/tournaments/{tid}/matches/{mid} — delete match.
    static func deleteMatch(baseURL: URL, tournamentId: UUID, matchId: UUID) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/matches/\(matchId.uuidString)"
        ))
        req.httpMethod = "DELETE"
        return req
    }

    // MARK: - Plans

    /// POST /v1/tournaments/{tid}/plans/generate — run rules engine + persist plan.
    static func generatePlan(baseURL: URL, tournamentId: UUID) -> URLRequest {
        var req = URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/plans/generate"
        ))
        req.httpMethod = "POST"
        return req
    }

    /// GET /v1/tournaments/{tid}/plans — list plans (newest first).
    static func listPlans(baseURL: URL, tournamentId: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/plans"
        ))
    }

    /// GET /v1/tournaments/{tid}/plans/{pid} — fetch single plan.
    static func getPlan(baseURL: URL, tournamentId: UUID, planId: UUID) -> URLRequest {
        URLRequest(url: baseURL.appendingPathComponent(
            "v1/tournaments/\(tournamentId.uuidString)/plans/\(planId.uuidString)"
        ))
    }
}
