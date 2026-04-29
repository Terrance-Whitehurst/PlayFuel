import Foundation

/// A single observation note about an opponent player.
/// Corresponds to `public.player_notes` in migration 0010_players_and_notes.sql.
///
/// Notes are the parent's own court observations — never opponent-authored data.
/// All privacy guardrails are enforced at the UX layer (AddPlayerNoteSheet §A.2)
/// and at the sanitization layer (services/scouting.py §D.3) before LLM input.
struct PlayerNote: Codable, Identifiable, Hashable {
    let id: UUID
    let playerId: UUID
    let source: PlayerNoteSource  // "secondhand" | "observed" | "post_match"
    let body: String              // up to 2000 chars (enforced by backend + DB CHECK)
    let matchId: UUID?            // optional link to a specific match; SET NULL on match delete
    let createdAt: Date

    /// Formatted relative date for note list display (e.g. "2 days ago").
    var relativeDate: String {
        let fmt = RelativeDateTimeFormatter()
        fmt.unitsStyle = .abbreviated
        return fmt.localizedString(for: createdAt, relativeTo: Date())
    }
}
