import Foundation

/// A scouted opponent player in the parent's player roster.
/// Corresponds to `public.players` in migration 0010_players_and_notes.sql.
///
/// Data-minimisation guarantee (see PLAYER_SCOUTING_V1.md §A.1):
///   • No email, phone, home address, photo, or physical-description fields.
///   • Only court-observable information plus a display name.
struct Player: Codable, Identifiable, Hashable {
    let id: UUID
    let displayName: String
    let club: String?        // e.g. "Dallas Tennis Academy" — optional
    let city: String?        // e.g. "Plano, TX" — optional regional context
    let notesSummary: String?  // parent-curated 1-line headline (OQ-SCOUT-DATA-1)
    let noteCount: Int         // derived by API; 0 when player has no notes
    let createdAt: Date
    let updatedAt: Date

    /// A one-line subtitle combining club and city for list rows.
    var locationSubtitle: String? {
        let parts = [club, city].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}
