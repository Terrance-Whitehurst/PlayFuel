import Foundation

/// A structured post-match write-up stored for a single match.
/// Mirrors `public.match_evaluations` from migration 0011.
///
/// One evaluation per match (UNIQUE on match_id in DB).
/// PATCH overwrites — no version history at MVP.
///
/// Privacy: `opponentObservations` is parent-authored content about
/// a junior opponent. Handled under PRIVACY_V1.md §13 OUC posture.
/// Auto-synced to `player_notes` (source=post_match) by the backend
/// when the match has an `opponent_player_id`.
struct MatchEvaluation: Codable, Identifiable, Hashable, Sendable {

    // MARK: - Stored Properties

    let id: UUID
    let matchId: UUID

    /// Match outcome. Required field — only value that must be provided.
    let result: MatchEvalResult

    /// Score string in player-entered format, e.g. "6-4, 3-6, 10-7".
    let scoreText: String?

    /// Self-rated physical effort on a 1-5 scale (1 = low, 5 = maximum effort).
    let effortRating: Int?

    /// Self-rated mental focus on a 1-5 scale (1 = distracted, 5 = locked in).
    let focusRating: Int?

    /// Up to 5 bullets describing what went well.
    let wentWell: [String]

    /// Up to 5 bullets describing growth areas (constructive framing).
    let toImprove: [String]

    /// Free-text parent observations about the opponent (≤500 chars).
    /// Auto-synced to `player_notes` by the backend service layer.
    let opponentObservations: String?

    /// Free-text capture of turning points and key moments (≤500 chars).
    let keyMoments: String?

    let createdAt: Date
    let updatedAt: Date

    // MARK: - Computed Properties

    /// Whether the result is a positive outcome (for UI accents).
    var isPositiveResult: Bool { result == .won }

    /// True when the evaluation has any content beyond the required result field.
    var hasDetailContent: Bool {
        scoreText != nil
        || effortRating != nil
        || focusRating != nil
        || !wentWell.isEmpty
        || !toImprove.isEmpty
        || opponentObservations != nil
        || keyMoments != nil
    }
}
