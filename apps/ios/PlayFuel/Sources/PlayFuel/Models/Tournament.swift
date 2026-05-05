import Foundation

/// A tennis tournament. Top-level entity in the entity hierarchy.
/// Phase 3: decoded from `GET /tournaments/{id}` response.
/// ACCOMMODATIONS_V1: accommodationLat/Lng/Address/Kind added (migration 0021).
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

    /// Bracket size: 32 | 64 | 128 | 256.
    /// Optional for backward compatibility with legacy API responses (pre-migration-0016).
    /// No stored default per project rule (Codable structs + stored defaults break memberwise init).
    let drawSize: Int?

    /// IANA timezone identifier, e.g. "America/Mexico_City". Nil for legacy rows.
    /// Phase A international: persisted via migration 0018.
    let timeZone: String?

    /// ISO 3166-1 alpha-2 country code, e.g. "MX", "US", "CA". Nil for legacy rows.
    /// Auto-populated from MKPlacemark.isoCountryCode when venue is selected.
    let venueCountry: String?

    // MARK: - Accommodations (ACCOMMODATIONS_V1 — migration 0021)

    /// Latitude of parent accommodation (hotel or home). Nil = no accommodation set.
    /// Pair constraint: accommodationLat and accommodationLng must both be set or both nil.
    let accommodationLat: Double?

    /// Longitude of parent accommodation. Pair-constrained with accommodationLat.
    let accommodationLng: Double?

    /// Human-readable address of accommodation (assembled from MapKit placemark fields).
    /// Stored for display only; plan math uses lat/lng, not this string.
    let accommodationAddress: String?

    /// Accommodation type for copy-variation: "home" or "hotel".
    /// Nil treated as "home" in display layer. Plan math is identical for both kinds.
    let accommodationKind: String?
}
