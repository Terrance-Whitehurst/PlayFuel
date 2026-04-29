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

    // MARK: - Doubles spec fields (Phase 7 — DOUBLES_SPEC_V1.md §A.2 / §E.5)
    //
    // Both use `= nil` defaults (same pattern as roundLabel above) so existing
    // FakeData / MatchDTO.toModel() call sites are unaffected unless they want to
    // explicitly supply a value.

    /// Match type: "singles" or "doubles". Nil for pre-doubles-spec matches
    /// (treat as singles via the `matchType` computed accessor).
    /// Maps to `matches.format` DB column (pre-existing — 0002_tables.sql).
    let format: String?

    /// Doubles format string: "best_of_3" or "pro_set_8".
    /// Nil when format != "doubles". Maps to `matches.doubles_format` (migration 0007).
    let doublesFormat: String?

    // MARK: - Player Scouting (migration 0010 — PLAYER_SCOUTING_V1.md §E.4)
    //
    // FK to `public.players.id`. Nil when the parent hasn’t linked a scouted opponent.
    // Populated from DB column `matches.opponent_player_id` via MatchDTO.toModel().

    /// UUID of the scouted opponent player (from `players` table). Optional.
    let opponentPlayerId: UUID? = nil

    // MARK: - Typed Accessors

    /// Typed MatchType derived from `format`. Defaults to `.singles` when nil
    /// (pre-doubles-spec matches, or explicit singles matches).
    var matchType: MatchType {
        MatchType(rawValue: format ?? "singles") ?? .singles
    }

    /// Typed DoublesFormat, or nil when not a doubles match.
    var doublesFormatTyped: DoublesFormat? {
        guard matchType == .doubles, let df = doublesFormat else { return nil }
        return DoublesFormat(rawValue: df)
    }
}
