import Foundation

// MARK: - Wire-Format DTOs
//
// These types match the API's wire format exactly and provide `.toModel()` mappers
// to the canonical iOS Models in `Sources/PlayFuel/Models/`.
//
// Two key encoding contexts:
//   snake_case (with .convertFromSnakeCase) — /v1/me, /v1/tournaments, /v1/matches
//   camelCase  (no key conversion)          — /v1/tournaments/{tid}/plans/generate
//
// ScenarioPlan has a client-only `id: UUID` not in the API response. To avoid a
// DecodingError.keyNotFound, we decode via ScenarioPlanDTO and inject UUID() on map.

// MARK: - /v1/me

/// Wire format for the `public.users` row returned by GET /v1/me.
/// Decoded with snakeDecoder (.convertFromSnakeCase). All fields arrive as snake_case.
struct UserDTO: Decodable {
    let id: UUID
    let createdAt: Date    // "created_at" → camel via .convertFromSnakeCase
    let updatedAt: Date

    func toModel() -> User {
        User(id: id)
    }
}

// MARK: - /v1/tournaments

/// Wire format for a `public.tournaments` row.
/// Decoded with snakeDecoder. Field names match DB column names (snake → camel by decoder).
struct TournamentDTO: Decodable {
    let id: UUID
    let userId: UUID?
    let name: String
    let venueName: String?
    let venueAddress: String?
    let venueCity: String?
    let venueRegion: String?
    let venuePostal: String?
    let venueLat: Double?
    let venueLng: Double?
    let startDate: String    // ISO date string kept as-is; matches iOS Tournament.startDate
    let endDate: String?
    let createdAt: Date?
    let updatedAt: Date?

    /// Map DB row → iOS Tournament model.
    /// Collapses structured venue address into a single display string.
    /// lat/lon default to 0.0 when absent (Phase 4 weather call will gracefully no-op).
    func toModel() -> Tournament {
        Tournament(
            id: id,
            name: name,
            venue: venueName ?? "Unknown Venue",
            lat: venueLat ?? 0.0,
            lon: venueLng ?? 0.0,
            startDate: startDate,
            endDate: endDate
        )
    }
}

// MARK: - /v1/tournaments/{tid}/matches
//
// STRUCTURAL DIVERGENCE: The DB stores `scheduled_start` as a full timestamp
// plus `estimated_duration_minutes`. The iOS `Match` model expects display
// strings (`scheduledTime: "9:00 AM"`) and fields like `round`, `opponent`,
// `court` that don't exist in the DB schema (OQ-iOS-2).
//
// Repository.fetchMatches returns [MatchDTO] directly — converting to Match
// requires multi-row context (next-match time derived from index+1) and view-
// layer time formatters. Views in Task #6 do not call fetchMatches.

struct MatchDTO: Decodable {
    let id: UUID
    let tournamentId: UUID
    let scheduledStart: Date          // ISO 8601 full timestamp
    let estimatedDurationMinutes: Int?
    let actualEndAt: Date?
    let surface: String?
    let format: String?
    let ageBracket: String?
    let displayOrder: Int?
    let createdAt: Date?
    let updatedAt: Date?
}

// MARK: - POST /v1/tournaments/{tid}/plans/generate

/// Outer envelope: {"plan": PlanCoreDTO}.
/// Decoded with camelDecoder (no key conversion). API uses Pydantic alias_generator=to_camel.
struct GeneratePlanResponseDTO: Decodable {
    let plan: PlanCoreDTO
}

/// Core plan fields returned by the rules engine.
/// All keys are camelCase in the API response (Pydantic alias_generator=to_camel).
///
/// Fields the iOS Plan model needs but the API does NOT return in Phase 3:
///   weather    — Phase 4 (Task #7 weather integration)
///   foodOptions — Phase 5 (Task #8 food/places integration)
///   timeline   — Phase 5
/// Repository.assembleHybridPlan splices those from FakeData until the phases land.
struct PlanCoreDTO: Decodable {
    let planId: UUID                   // serialized as UUID string by Pydantic; JSONDecoder parses it
    let tournamentId: UUID
    let generatedAt: String            // ISO 8601 datetime string; kept as String to match Plan.generatedAt
    let rulesConstantsVersion: String
    let scheduleConfidence: String?
    let heatEmergencyText: String?
    let warnings: [String]
    let scenarioPlans: [ScenarioPlanDTO]

    enum CodingKeys: String, CodingKey {
        case planId, tournamentId, generatedAt, rulesConstantsVersion
        case scheduleConfidence, heatEmergencyText, warnings, scenarioPlans
    }

    // Custom init because `generatedAt` may arrive as a Date in iso8601 format
    // or already as a String. We normalise to String either way.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.planId             = try c.decode(UUID.self,   forKey: .planId)
        self.tournamentId       = try c.decode(UUID.self,   forKey: .tournamentId)
        self.rulesConstantsVersion = try c.decode(String.self, forKey: .rulesConstantsVersion)
        self.scheduleConfidence = try c.decodeIfPresent(String.self, forKey: .scheduleConfidence)
        self.heatEmergencyText  = try c.decodeIfPresent(String.self, forKey: .heatEmergencyText)
        self.warnings           = try c.decodeIfPresent([String].self, forKey: .warnings) ?? []
        self.scenarioPlans      = try c.decode([ScenarioPlanDTO].self, forKey: .scenarioPlans)

        // `generated_at` is a Python `datetime` → Pydantic serialises as ISO 8601 string in JSON.
        // Decode as String directly (the camelDecoder .iso8601 strategy affects Date, not String).
        self.generatedAt = try c.decode(String.self, forKey: .generatedAt)
    }
}

// MARK: - ScenarioPlan wire format
//
// The iOS `ScenarioPlan` model has a client-only `id: UUID` that is NOT in the
// API response. Synthesised Decodable would throw `keyNotFound` for `id`.
// Solution: decode via this DTO (all fields except `id`), then map to ScenarioPlan
// with a fresh `UUID()` injected — preserving SwiftUI list identity without
// requiring any change to the existing model.

/// Wire-format ScenarioPlan. Decoded with camelDecoder (camelCase keys from Pydantic aliases).
/// All sub-types (GapStatus, FoodStrategy, PickupStrategy, RewarmUp, OverrunWarning)
/// are already Codable in Sources/PlayFuel/Models/ScenarioPlan.swift and decode naturally.
struct ScenarioPlanDTO: Decodable {
    let scenario: String            // "short" | "normal" | "long"
    let durationMin: Int
    let estimatedEnd: String
    let gapMinutes: Int?
    let gapStatus: GapStatus
    let foodStrategy: FoodStrategy?
    let pickupStrategy: PickupStrategy
    let rewarmUp: RewarmUp?
    let overrunWarning: OverrunWarning?
    let warnings: [String]

    /// Map wire format to canonical iOS model. Injects a fresh UUID for SwiftUI identity.
    func toModel() -> ScenarioPlan {
        ScenarioPlan(
            id: UUID(),
            scenario: scenario,
            durationMin: durationMin,
            estimatedEnd: estimatedEnd,
            gapMinutes: gapMinutes,
            gapStatus: gapStatus,
            foodStrategy: foodStrategy,
            pickupStrategy: pickupStrategy,
            rewarmUp: rewarmUp,
            overrunWarning: overrunWarning,
            warnings: warnings
        )
    }
}
