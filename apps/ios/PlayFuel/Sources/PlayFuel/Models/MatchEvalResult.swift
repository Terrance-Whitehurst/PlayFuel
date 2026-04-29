import Foundation

/// Outcome of a tennis match from the player's perspective.
/// Mirrors the `match_eval_result` Postgres enum in migration 0011.
enum MatchEvalResult: String, Codable, CaseIterable, Identifiable, Sendable {
    case won       = "won"
    case lost      = "lost"
    case withdrew  = "withdrew"
    case retired   = "retired"

    var id: String { rawValue }

    /// Parent-facing display label shown in the form and read-only card.
    var displayName: String {
        switch self {
        case .won:      return "Won"
        case .lost:     return "Lost"
        case .withdrew: return "Withdrew"
        case .retired:  return "Retired"
        }
    }

    /// Short emoji accent used in the result pill.
    var emoji: String {
        switch self {
        case .won:      return "🏆"
        case .lost:     return "💪"
        case .withdrew: return "🤚"
        case .retired:  return "🩹"
        }
    }

    /// Whether this result counts as a positive outcome for visual accents.
    var isPositive: Bool { self == .won }

    /// Color token string for the result pill background.
    var colorName: String {
        switch self {
        case .won:              return "green"
        case .lost:             return "red"
        case .withdrew, .retired: return "gray"
        }
    }
}
