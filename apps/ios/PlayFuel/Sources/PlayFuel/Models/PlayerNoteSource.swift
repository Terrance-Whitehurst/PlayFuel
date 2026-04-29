import Foundation

/// Source provenance for a player note.
/// Mirrors the `player_note_source` Postgres enum in migration 0010_players_and_notes.sql.
/// Raw values are snake_case to match API wire format exactly.
enum PlayerNoteSource: String, Codable, CaseIterable, Identifiable, Sendable, Hashable {
    case secondhand
    case observed
    case post_match

    var id: String { rawValue }

    /// Short display label for source pills and segmented pickers.
    var displayName: String {
        switch self {
        case .secondhand: return "Heard"
        case .observed:   return "Watched"
        case .post_match: return "Played"
        }
    }
}
