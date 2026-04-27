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
}
