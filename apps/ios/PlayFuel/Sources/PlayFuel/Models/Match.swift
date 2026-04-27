import Foundation

/// A single match within a tournament.
/// Phase 3: decoded from `GET /tournaments/{id}/matches`.
struct Match: Codable, Identifiable, Hashable {

    let id: UUID
    let tournamentId: UUID

    /// Display string, e.g. "9:00 AM". Phase 3: timezone-aware timestamp.
    let scheduledTime: String

    /// Optional estimated start time of the NEXT match, e.g. "1:00 PM".
    /// Nil triggers `no_next_match` gap status in the rules engine.
    let estimatedNextMatchTime: String?

    /// Round name, e.g. "Round of 16". Optional.
    let round: String?

    /// Opponent name. Optional.
    let opponent: String?

    /// Court identifier, e.g. "Court 4". Optional.
    let court: String?

    // MARK: - OQ-API-1(a) label fields (Phase 5)
    //
    // Explicit `= nil` default so the synthesized memberwise initialiser makes
    // these parameters omittable — existing FakeData/Match call sites need not change.

    /// Human-readable round label from the API, e.g. "R16", "QF". Optional.
    /// Distinct from the display `round` string above — populated from DB column
    /// `matches.round_label` added in migration 0005.
    let roundLabel: String? = nil

    /// Human-readable opponent display name from the API. Optional.
    let opponentLabel: String? = nil

    /// Human-readable court designation from the API, e.g. "Court 7". Optional.
    let courtLabel: String? = nil
}
