import Foundation

/// A tennis tournament. Top-level entity in the entity hierarchy.
/// Phase 3: decoded from `GET /tournaments/{id}` response.
struct Tournament: Codable, Identifiable, Hashable {

    /// Stable UUID — matches `tournaments.id` in Supabase schema.
    let id: UUID

    /// Display name, e.g. "Dallas Spring Open".
    let name: String

    /// Venue name, e.g. "Samuell Grand Tennis Center".
    let venue: String

    /// Venue latitude — used by weather + places APIs in Phase 4/5.
    let lat: Double

    /// Venue longitude.
    let lon: Double

    /// ISO 8601 date string, e.g. "2026-04-26". Kept as String for prototype simplicity;
    /// Phase 3: parse to Date with ISO8601DateFormatter.
    let startDate: String

    /// Optional end date. Nil for single-day tournaments.
    let endDate: String?
}
