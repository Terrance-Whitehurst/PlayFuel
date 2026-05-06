import XCTest
@testable import PlayFuel

// MARK: - AccommodationsTests
//
// Acceptance tests for ACCOMMODATIONS_V1 iOS layer.
// See spec §I.1 acceptance scenarios T-15, T-16, T-17.
//
// T-15 — Tournament decode: JSON without accommodation fields decodes without crash;
//         accommodationLat == nil.
// T-16 — TimelineEvent decode: kind = "departure" decodes as .departure; renders
//         in TimelineView (render-no-crash via TimelineEventKind switch exhaustiveness).
// T-17 — Unknown kind fallback regression: kind = "foobar" falls back to .gap.
//
// These tests are regression guards:
//   - T-15 guards against the Codable strict-init rule (no stored-property defaults):
//     if Tournament gains a non-optional field without a default, legacy API responses
//     without that field will crash — catching it here is the earliest signal.
//   - T-17 guards against accidental removal of the TimelineEventDTO graceful fallback
//     introduced in DTOs.swift (kind decode: TimelineEventKind(rawValue:) ?? .gap).

final class AccommodationsTests: XCTestCase {

    // MARK: - T-15: Tournament decode without accommodation fields

    func test_T15_tournament_decodesWithoutAccommodationFields() throws {
        // JSON matching a pre-migration-0021 API response — no accommodation keys.
        let json = """
        {
            "id": "11111111-0000-0000-0000-000000000001",
            "userId": "AAAAAAAA-0000-0000-0000-000000000001",
            "name": "Dallas Spring Open",
            "venueName": "Samuell Grand Tennis Center",
            "venueAddress": "6200 East Grand Ave",
            "venueCity": "Dallas",
            "venueRegion": "TX",
            "venuePostal": "75223",
            "venueLat": 32.7767,
            "venueLng": -96.7970,
            "startDate": "2026-04-26",
            "endDate": "2026-04-27",
            "drawSize": 32,
            "timeZone": "America/Chicago",
            "venueCountry": "US",
            "createdAt": "2026-04-01T00:00:00Z",
            "updatedAt": "2026-04-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        // Must not throw — graceful nil for all accommodation fields
        let dto = try decoder.decode(TournamentDTO.self, from: json)
        let model = dto.toModel()

        XCTAssertNil(model.accommodationLat,     "T-15: accommodationLat must be nil when absent from JSON")
        XCTAssertNil(model.accommodationLng,     "T-15: accommodationLng must be nil when absent from JSON")
        XCTAssertNil(model.accommodationAddress, "T-15: accommodationAddress must be nil when absent from JSON")
        XCTAssertNil(model.accommodationKind,    "T-15: accommodationKind must be nil when absent from JSON")
        XCTAssertEqual(model.name, "Dallas Spring Open")
    }

    func test_T15b_tournament_decodesWithAccommodationFields() throws {
        // JSON with all four accommodation fields populated — hotel scenario.
        let json = """
        {
            "id": "11111111-0000-0000-0000-000000000001",
            "userId": "AAAAAAAA-0000-0000-0000-000000000001",
            "name": "Dallas Spring Open",
            "venueName": "Samuell Grand Tennis Center",
            "venueAddress": "6200 East Grand Ave",
            "venueCity": "Dallas",
            "venueRegion": "TX",
            "venuePostal": "75223",
            "venueLat": 32.7767,
            "venueLng": -96.7970,
            "startDate": "2026-04-26",
            "endDate": "2026-04-27",
            "drawSize": 32,
            "timeZone": "America/Chicago",
            "venueCountry": "US",
            "accommodationLat": 32.8968,
            "accommodationLng": -97.0381,
            "accommodationAddress": "2626 Meacham Blvd, Fort Worth, TX",
            "accommodationKind": "hotel",
            "createdAt": "2026-04-01T00:00:00Z",
            "updatedAt": "2026-04-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601

        let dto = try decoder.decode(TournamentDTO.self, from: json)
        let model = dto.toModel()

        let lat = try XCTUnwrap(model.accommodationLat, "T-15b: accommodationLat must not be nil")
        let lng = try XCTUnwrap(model.accommodationLng, "T-15b: accommodationLng must not be nil")
        XCTAssertEqual(lat, 32.8968, accuracy: 0.0001,
                       "T-15b: accommodationLat should decode to 32.8968")
        XCTAssertEqual(lng, -97.0381, accuracy: 0.0001,
                       "T-15b: accommodationLng should decode to -97.0381")
        XCTAssertEqual(model.accommodationAddress, "2626 Meacham Blvd, Fort Worth, TX")
        XCTAssertEqual(model.accommodationKind, "hotel")
    }

    // MARK: - T-16: TimelineEvent decodes "departure" kind

    func test_T16_timelineEvent_departureKindDecodes() throws {
        // JSON for a departure event as the backend would emit it.
        let json = """
        {
            "id": "CCCCCCCC-0000-0000-0000-000000000001",
            "time": "2026-04-26T08:30:00-05:00",
            "title": "Leave home",
            "detail": "30-minute drive — arrive at the venue by 9:30 AM.",
            "kind": "departure"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let dto = try decoder.decode(TimelineEventDTO.self, from: json)
        let model = dto.toModel()

        XCTAssertEqual(model.kind, .departure,
                       "T-16: kind=departure must decode as TimelineEventKind.departure")
        XCTAssertEqual(model.title, "Leave home")
        // Verify the UUID round-trips safely
        XCTAssertNotNil(model.id)
    }

    func test_T16b_timelineEvent_departureIsExhaustive() {
        // Exhaustiveness guard: TimelineEventKind.allCases must contain .departure.
        // If .departure is ever removed from the enum, this test fails immediately
        // rather than letting the TimelineView switch silently fall through.
        let allCases = TimelineEventKind.allCases
        XCTAssertTrue(allCases.contains(.departure),
                      "T-16b: TimelineEventKind.allCases must include .departure")
    }

    // MARK: - T-17: Unknown kind falls back to .gap (regression guard)

    func test_T17_timelineEvent_unknownKindFallsBackToGap() throws {
        // Spec §I T-17: any unknown kind string must fall back to .gap.
        // This guards against future enum additions breaking old iOS clients.
        let json = """
        {
            "id": "DDDDDDDD-0000-0000-0000-000000000001",
            "time": "2026-04-26T07:00:00-05:00",
            "title": "Unknown Event",
            "detail": "Future event type from a newer API version.",
            "kind": "foobar"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let dto = try decoder.decode(TimelineEventDTO.self, from: json)
        let model = dto.toModel()

        XCTAssertEqual(model.kind, .gap,
                       "T-17: Unknown kind string must fall back to .gap (not crash)")
    }

    func test_T17b_timelineEvent_nilKindFallsBackToGap() throws {
        // Edge case: if kind field is an empty string (not null), also falls back.
        let json = """
        {
            "id": "EEEEEEEE-0000-0000-0000-000000000001",
            "time": "2026-04-26T07:00:00-05:00",
            "title": "Empty Kind",
            "detail": "kind is an empty string.",
            "kind": ""
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let dto = try decoder.decode(TimelineEventDTO.self, from: json)
        let model = dto.toModel()

        XCTAssertEqual(model.kind, .gap,
                       "T-17b: Empty kind string must fall back to .gap")
    }
}
