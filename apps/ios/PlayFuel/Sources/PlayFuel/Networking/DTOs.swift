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

    // OQ-API-1(a) label fields — migration 0005. Decoded via .convertFromSnakeCase.
    let roundLabel: String?    // round_label → roundLabel
    let opponentLabel: String? // opponent_label → opponentLabel
    let courtLabel: String?    // court_label → courtLabel

    // Player Scouting — migration 0010. Decoded via .convertFromSnakeCase.
    let opponentPlayerId: UUID? // opponent_player_id → opponentPlayerId

    // Doubles spec (Phase 7 — 0007_doubles_support.sql). Decoded via .convertFromSnakeCase.
    // `format` is pre-existing in the DB (0002_tables.sql) but was omitted from MatchDTO
    // until this spec — add it here alongside the new doubles_format column.
    let doublesFormat: String?  // doubles_format → doublesFormat (migration 0007)
}

// MARK: - POST /v1/tournaments/{tid}/plans/generate
//
// BREAKING CHANGE (Phase 7 Doubles spec):
// The API now returns { "singlesPlan": Plan|null, "doublesPlan": Plan|null }.
// The old `{ "plan": Plan }` envelope (GeneratePlanResponseDTO) is replaced by
// PlanEnvelopeDTO. Repository.generatePlan() decodes PlanEnvelopeDTO.
//
// Decoded with camelDecoder (no key conversion). API uses Pydantic alias_generator=to_camel.

/// Phase 8 envelope: { singlesPlans: [PlanCoreDTO], doublesPlans: [PlanCoreDTO] }.
/// BREAKING CHANGE from Phase 7 (which used singular singlesPlan/doublesPlan).
/// Both arrays default to [] when the key is absent (backwards-compat with Phase 7 API).
struct PlanEnvelopeDTO: Decodable {
    let singlesPlans: [PlanCoreDTO]
    let doublesPlans: [PlanCoreDTO]

    enum CodingKeys: String, CodingKey {
        case singlesPlans, doublesPlans
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        singlesPlans = try c.decodeIfPresent([PlanCoreDTO].self, forKey: .singlesPlans) ?? []
        doublesPlans = try c.decodeIfPresent([PlanCoreDTO].self, forKey: .doublesPlans) ?? []
    }

    /// Map wire-format envelope → iOS PlanEnvelope domain model.
    func toModel() -> PlanEnvelope {
        PlanEnvelope(
            singlesPlans: singlesPlans.map { $0.toModel() },
            doublesPlans: doublesPlans.map { $0.toModel() }
        )
    }
}

/// Core plan fields returned by the rules engine.
/// All keys are camelCase in the API response (Pydantic alias_generator=to_camel).
///
/// Phase 5 (Task #8): now includes weather, foodOptions, timeline, bagFallbackOnly
/// directly from the API — FakeData splice retired.
struct PlanCoreDTO: Decodable {
    let planId: UUID                   // serialized as UUID string by Pydantic; JSONDecoder parses it
    let tournamentId: UUID
    let generatedAt: String            // ISO 8601 datetime string; kept as String to match Plan.generatedAt
    let rulesConstantsVersion: String
    let scheduleConfidence: String?
    let heatEmergencyText: String?
    let warnings: [String]
    let scenarioPlans: [ScenarioPlanDTO]
    // Phase 4/5 additions
    let weather: WeatherBlockDTO?       // nil when no venue coords or provider error
    let foodOptions: [FoodOptionDTO]?   // nil when all scenarios are bag_only
    let timeline: [TimelineEventDTO]    // empty list when engine produces none
    let bagFallbackOnly: Bool           // true when all scenarios use bag_only bucket
    let llmSummary: PlanExplanationDTO? // nil for pre-Phase-6 plans or when provider unavailable
    // Phase 7 — match type for which this plan was generated (DOUBLES_SPEC_V1.md §D.3)
    let matchType: String               // "singles" | "doubles"; decodeIfPresent defaults to "singles"
    // Phase 8 — per-match anchoring (NUTRITION_FIRST_IA_V1.md §E)
    let matchId: UUID?                  // nil for legacy plans pre-migration-0008
    let nextAction: NextActionDTO?      // nil when no future events in 6h lookahead window
    let scheduledStart: String?         // ISO 8601 timestamp of the match start; for strip ordering

    enum CodingKeys: String, CodingKey {
        case planId, tournamentId, generatedAt, rulesConstantsVersion
        case scheduleConfidence, heatEmergencyText, warnings, scenarioPlans
        case weather, foodOptions, timeline, bagFallbackOnly, llmSummary
        case matchType
        case matchId
        case nextAction
        case scheduledStart
    }

    // Custom init: normalise generatedAt to String; use decodeIfPresent for
    // optional/defaulted fields so older API versions don't break decoding.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.planId                = try c.decode(UUID.self,   forKey: .planId)
        self.tournamentId          = try c.decode(UUID.self,   forKey: .tournamentId)
        self.rulesConstantsVersion = try c.decode(String.self, forKey: .rulesConstantsVersion)
        self.scheduleConfidence    = try c.decodeIfPresent(String.self, forKey: .scheduleConfidence)
        self.heatEmergencyText     = try c.decodeIfPresent(String.self, forKey: .heatEmergencyText)
        self.warnings              = try c.decodeIfPresent([String].self, forKey: .warnings) ?? []
        self.scenarioPlans         = try c.decode([ScenarioPlanDTO].self, forKey: .scenarioPlans)
        // Phase 4/5
        self.weather               = try c.decodeIfPresent(WeatherBlockDTO.self,    forKey: .weather)
        self.foodOptions           = try c.decodeIfPresent([FoodOptionDTO].self,    forKey: .foodOptions)
        self.timeline              = try c.decodeIfPresent([TimelineEventDTO].self, forKey: .timeline) ?? []
        self.bagFallbackOnly       = try c.decodeIfPresent(Bool.self, forKey: .bagFallbackOnly) ?? false
        self.llmSummary            = try c.decodeIfPresent(PlanExplanationDTO.self, forKey: .llmSummary)
        // Phase 7: match_type defaults to "singles" for legacy plans that predate migration 0007.
        self.matchType             = try c.decodeIfPresent(String.self, forKey: .matchType) ?? "singles"
        // Phase 8: per-match fields; all optional for backwards-compat with Phase 7 API.
        self.matchId               = try c.decodeIfPresent(UUID.self,   forKey: .matchId)
        self.nextAction            = try c.decodeIfPresent(NextActionDTO.self, forKey: .nextAction)
        self.scheduledStart        = try c.decodeIfPresent(String.self, forKey: .scheduledStart)
        // `generated_at` is a Python `datetime` → Pydantic serialises as ISO 8601 string in JSON.
        self.generatedAt = try c.decode(String.self, forKey: .generatedAt)
    }

    /// Map wire-format DTO → canonical iOS Plan domain model.
    func toModel() -> Plan {
        Plan(
            id: planId,
            planId: planId.uuidString,
            tournamentId: tournamentId,
            generatedAt: generatedAt,
            warnings: warnings,
            scenarioPlans: scenarioPlans.map { $0.toModel() },
            weather: weather?.toModel() ?? _weatherUnavailable,
            foodOptions: (foodOptions ?? []).map { $0.toModel() },
            timeline: timeline.map { $0.toModel() },
            bagFallbackOnly: bagFallbackOnly,
            llmSummary: llmSummary?.toModel(),
            matchType: MatchType(rawValue: matchType) ?? .singles,
            matchId: matchId ?? UUID(),   // Phase 8: fallback UUID for legacy plans
            nextAction: nextAction?.toModel(),
            scheduledStart: scheduledStart
        )
    }
}

// MARK: - Sentinel: weather unavailable
//
// Used when the API returns null for `weather` (no venue coordinates, provider
// error). Renders as 0°F / 0% humidity / no flags — EmergencyBanner will NOT
// fire. A future OQ should surface a "weather unavailable" state in the UI.
private let _weatherUnavailable = WeatherSnapshot(
    tempF: 0, humidity: 0, windMph: 0, precipProb: 0, uvIndex: nil, flags: []
)

// MARK: - Phase 4/5 DTOs

// MARK: WeatherBlockDTO
//
// Decoded from the `weather` field of PlanCoreDTO. Maps to iOS `WeatherSnapshot`.
// Note: the API WeatherBlock does not surface `windMph`, `precipProb`, or `uvIndex`
// as scalar values — only boolean flags. iOS domain model defaults those to 0.0/nil.
// NEW-OQ-W1: consider adding wind_mph / precip_prob / uv_index to the API WeatherBlock
// so WeatherCardView can display accurate values from the real provider.
struct WeatherBlockDTO: Decodable {
    let tempF: Double
    let humidityPct: Double
    let condition: String      // decoded as String to tolerate unknown enum additions
    let flagHot: Bool
    let flagVeryHot: Bool
    let flagHumid: Bool
    let flagCold: Bool
    let flagWindy: Bool
    let flagRainRisk: Bool
    let flagExtremeHeatRisk: Bool
    let isStale: Bool
    let fetchedAt: String      // ISO 8601 datetime string
    let provider: String

    /// Map API WeatherBlock → iOS WeatherSnapshot.
    /// Boolean flags are reconstructed into the [WeatherFlag] array.
    /// windMph / precipProb / uvIndex are not available from the API at this time.
    func toModel() -> WeatherSnapshot {
        var flags: [WeatherFlag] = []
        if flagVeryHot { flags.append(.very_hot) }
        if flagHot && !flagVeryHot { flags.append(.hot) }  // hot is mutually exclusive with very_hot in UI
        if flagHumid    { flags.append(.humid) }
        if flagCold     { flags.append(.cold) }
        if flagWindy    { flags.append(.windy) }
        if flagRainRisk { flags.append(.rain_risk) }
        return WeatherSnapshot(
            tempF: tempF,
            humidity: humidityPct,
            windMph: 0.0,      // NEW-OQ-W1: not yet surfaced by API WeatherBlock
            precipProb: 0.0,   // NEW-OQ-W1: not yet surfaced by API WeatherBlock
            uvIndex: nil,      // NEW-OQ-W1: not yet surfaced by API WeatherBlock
            flags: flags
        )
    }
}

// MARK: FoodSuggestionsDTO
//
// Decoded from the `suggestions` field of FoodOptionDTO (camelCase wire format).
// Maps to iOS `FoodSuggestions` domain model.
// FOOD_DECK_AND_MAP_V1.md §A.1
struct FoodSuggestionsDTO: Decodable {
    let mainOptions: [String]
    let addOns: [String]
    let drinks: [String]
    let avoid: [String]
    let notes: [String]

    func toModel() -> FoodSuggestions {
        FoodSuggestions(
            mainOptions: mainOptions,
            addOns: addOns,
            drinks: drinks,
            avoid: avoid,
            notes: notes
        )
    }
}

// MARK: FoodOptionDTO
//
// Decoded from each element of PlanCoreDTO.foodOptions (camelCase wire format).
// Maps to iOS `FoodOption` domain model.
//
// FOOD_DECK_AND_MAP_V1.md §I-3: `driveTimeMin` is now `Int?` on the iOS model.
// The previous `?? 0` shim has been removed — nil passes through cleanly.
struct FoodOptionDTO: Decodable {
    let name: String
    let category: String
    let driveTimeMinutes: Int?   // nullable on the API side (mock provider may omit)
    let recommendedOrder: String
    let isDraft: Bool
    let distanceMeters: Int?
    let placeId: String?
    let provider: String
    // Phase 9 additions — FOOD_DECK_AND_MAP_V1.md
    let suggestions: FoodSuggestionsDTO?  // nil for pre-Phase-9 plans
    let lat: Double?                       // venue latitude for map pins
    let lng: Double?                       // venue longitude for map pins

    /// Map API FoodOption → iOS FoodOption domain model.
    /// A fresh `UUID()` is injected for SwiftUI list identity (no server-side ID).
    func toModel() -> FoodOption {
        FoodOption(
            id: UUID(),
            name: name,
            category: category,
            driveTimeMin: driveTimeMinutes,   // nil-safe: no ?? 0 shim
            recommendedOrder: recommendedOrder,
            isDraft: isDraft,
            distanceMeters: distanceMeters,
            placeId: placeId,
            provider: provider,
            suggestions: suggestions?.toModel(),
            lat: lat,
            lng: lng
        )
    }
}

// MARK: TimelineEventDTO
//
// Decoded from each element of PlanCoreDTO.timeline (camelCase wire format).
// Maps to iOS `TimelineEvent` domain model.
struct TimelineEventDTO: Decodable {
    let id: String               // UUID v4 string; fresh per request
    let time: String             // ISO 8601 timestamp
    let title: String
    let detail: String
    let kind: TimelineEventKind  // decoded with fallback to .gap for unknown values

    enum CodingKeys: String, CodingKey {
        case id, time, title, detail, kind
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id     = try c.decode(String.self, forKey: .id)
        time   = try c.decode(String.self, forKey: .time)
        title  = try c.decode(String.self, forKey: .title)
        detail = try c.decode(String.self, forKey: .detail)
        // Decode kind as String with fallback so unknown future event kinds
        // don't crash iOS — they render as .gap visually.
        let kindRaw = try c.decode(String.self, forKey: .kind)
        kind = TimelineEventKind(rawValue: kindRaw) ?? .gap
    }

    /// Map API TimelineEventOut → iOS TimelineEvent domain model.
    func toModel() -> TimelineEvent {
        TimelineEvent(
            id: UUID(uuidString: id) ?? UUID(),
            time: time,
            title: title,
            detail: detail,
            kind: kind
        )
    }
}

// MARK: - Request body structs
//
// Encodable-only (never decoded). Repository's postEncoder uses .convertToSnakeCase
// so Swift camelCase property names map to the API's snake_case request fields.

/// Request body for POST /v1/tournaments.
/// NOTE: `time_zone` is collected by the iOS form but is NOT in the API's TournamentCreate
/// Pydantic model (migration pending). Omitted here — the iOS form retains it for future use.
struct TournamentCreateRequest: Encodable {
    let name: String
    let venueName: String       // → venue_name
    let venueLat: Double        // → venue_lat
    let venueLng: Double        // → venue_lng
    let startDate: String       // → start_date ("yyyy-MM-dd" string; API type is `date`)
    let endDate: String         // → end_date
}

/// Request body for POST /v1/tournaments/{tid}/matches.
/// NOTE: `estimated_next_match_time` is NOT a DB column — it is derived from the match list
/// (next match's scheduledStart). The iOS form collects it for UX but it is not sent to the API.
/// Phase 7: `format` and `doublesFormat` added per DOUBLES_SPEC_V1.md §A.2.
/// Player Scouting: `opponentPlayerId` added per PLAYER_SCOUTING_V1.md §E.4.
struct MatchCreateRequest: Encodable {
    let scheduledStart: Date            // → scheduled_start (ISO 8601 datetime)
    let estimatedDurationMinutes: Int?  // → estimated_duration_minutes
    let roundLabel: String?             // → round_label
    let opponentLabel: String?          // → opponent_label
    let courtLabel: String?             // → court_label
    let displayOrder: Int?              // → display_order
    // Phase 7 — match type + doubles format
    let format: String                  // → format ("singles" | "doubles")
    let doublesFormat: String?          // → doubles_format ("best_of_3" | "pro_set_8" | null)
    // Player Scouting — optional FK to scouted opponent
    let opponentPlayerId: UUID?         // → opponent_player_id (migration 0010)
}

// MARK: - Player Scouting DTOs (migration 0010)
//
// All player endpoints (/v1/players) use the snake decoder (.convertFromSnakeCase).
// Request bodies are encoded with postEncoder (.convertToSnakeCase + .iso8601).

/// Wire format for a `public.players` row returned by player CRUD endpoints.
/// Decoded with snakeDecoder. noteCount is a derived field (subquery in route).
struct PlayerDTO: Decodable {
    let id: UUID
    let userId: UUID
    let displayName: String
    let club: String?
    let city: String?
    let notesSummary: String?
    let noteCount: Int
    let createdAt: Date
    let updatedAt: Date

    func toModel() -> Player {
        Player(
            id: id,
            displayName: displayName,
            club: club,
            city: city,
            notesSummary: notesSummary,
            noteCount: noteCount,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

/// Wire format for a `public.player_notes` row.
/// Decoded with snakeDecoder.
struct PlayerNoteDTO: Decodable {
    let id: UUID
    let playerId: UUID
    let userId: UUID
    let source: String           // "secondhand" | "observed" | "post_match"
    let body: String
    let matchId: UUID?
    let createdAt: Date

    func toModel() -> PlayerNote {
        PlayerNote(
            id: id,
            playerId: playerId,
            source: PlayerNoteSource(rawValue: source) ?? .observed,
            body: body,
            matchId: matchId,
            createdAt: createdAt
        )
    }
}

/// Request body for POST /v1/players.
/// Encoded with postEncoder (.convertToSnakeCase).
struct PlayerCreateRequest: Encodable {
    let displayName: String      // → display_name
    let club: String?            // → club (optional)
    let city: String?            // → city (optional)
    let notesSummary: String?    // → notes_summary (optional)
}

/// Request body for PATCH /v1/players/{id}.
struct PlayerUpdateRequest: Encodable {
    let displayName: String?
    let club: String?
    let city: String?
    let notesSummary: String?
}

/// Request body for POST /v1/players/{id}/notes.
struct PlayerNoteCreateRequest: Encodable {
    let source: String           // → source ("secondhand" | "observed" | "post_match")
    let body: String             // → body (max 2000 chars)
    let matchId: UUID?           // → match_id (optional)
}

// MARK: - Post-Match Evaluation DTOs (migration 0011)
//
// Endpoints: GET/POST/PATCH/DELETE /v1/matches/{mid}/evaluation
// Request bodies encoded with postEncoder (.convertToSnakeCase + .iso8601).
// Response decoded with snakeDecoder (.convertFromSnakeCase + .iso8601).

/// Wire format for a `public.match_evaluations` row.
/// Decoded with snakeDecoder (.convertFromSnakeCase + .iso8601 dates).
struct MatchEvaluationDTO: Decodable {
    let id: UUID
    let matchId: UUID
    let result: String          // "won" | "lost" | "withdrew" | "retired"
    let scoreText: String?
    let effortRating: Int?
    let focusRating: Int?
    let wentWell: [String]
    let toImprove: [String]
    let opponentObservations: String?
    let keyMoments: String?
    let createdAt: Date
    let updatedAt: Date

    func toModel() -> MatchEvaluation {
        MatchEvaluation(
            id: id,
            matchId: matchId,
            result: MatchEvalResult(rawValue: result) ?? .lost,
            scoreText: scoreText,
            effortRating: effortRating,
            focusRating: focusRating,
            wentWell: wentWell,
            toImprove: toImprove,
            opponentObservations: opponentObservations,
            keyMoments: keyMoments,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

/// Request body for POST /v1/matches/{mid}/evaluation.
/// Encoded with postEncoder (.convertToSnakeCase).
struct MatchEvaluationCreateRequest: Encodable {
    let result: String              // → result
    let scoreText: String?          // → score_text
    let effortRating: Int?          // → effort_rating
    let focusRating: Int?           // → focus_rating
    let wentWell: [String]          // → went_well
    let toImprove: [String]         // → to_improve
    let opponentObservations: String? // → opponent_observations
    let keyMoments: String?         // → key_moments
}

// MARK: - MatchDTO.toModel()

extension MatchDTO {
    /// Map API MatchDTO → iOS Match domain model.
    /// `scheduledTime` is a display string formatted in the device's local timezone.
    /// `estimatedNextMatchTime` is nil — it is derived from multi-row match context,
    /// not stored in the DB. Views that need it must compute it from the ordered match list.
    /// Phase 7: `format` and `doublesFormat` are passed explicitly so the doubles-spec
    /// fields round-trip through the match card UI without loss.
    func toModel() -> Match {
        let fmt = DateFormatter()
        fmt.dateFormat = "h:mm a"
        fmt.amSymbol = "AM"
        fmt.pmSymbol = "PM"
        return Match(
            id: id,
            tournamentId: tournamentId,
            scheduledTime: fmt.string(from: scheduledStart),
            estimatedNextMatchTime: nil,
            round: roundLabel,
            opponent: opponentLabel,
            court: courtLabel,
            // roundLabel / opponentLabel / courtLabel use their `= nil` stored-property defaults
            // Phase 7: pass format + doublesFormat explicitly from the DB row
            format: format,
            doublesFormat: doublesFormat
            // opponentPlayerId uses its `= nil` stored-property default; populated via Codable
            // when Match is decoded directly. In MatchDTO.toModel() it defaults to nil because
            // MatchDTO carries it but Match.opponentPlayerId is set via Codable decode path.
        )
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

// MARK: - Phase 8 — NextActionDTO
//
// Decoded from the `nextAction` field of PlanCoreDTO (camelCase wire format).
// Maps to the iOS `NextAction` domain model.
// Produced by `rules/next_action.py` on the backend — never from the LLM.

struct NextActionDTO: Decodable {
    let title: String
    let detail: String
    let scheduledFor: Date?   // decoded via camelDecoder .iso8601 strategy; nil on recovery_fallback
    let kind: String
    let minsUntil: Int?       // nil on recovery_fallback

    enum CodingKeys: String, CodingKey {
        case title, detail, scheduledFor, kind, minsUntil
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title        = try c.decode(String.self,  forKey: .title)
        detail       = try c.decode(String.self,  forKey: .detail)
        scheduledFor = try c.decodeIfPresent(Date.self, forKey: .scheduledFor)
        kind         = try c.decode(String.self,  forKey: .kind)
        minsUntil    = try c.decodeIfPresent(Int.self,  forKey: .minsUntil)
    }

    /// Map API NextAction → iOS NextAction domain model.
    func toModel() -> NextAction {
        NextAction(
            title: title,
            detail: detail,
            scheduledFor: scheduledFor,
            kind: kind,
            minsUntil: minsUntil
        )
    }
}

// MARK: - Phase 6 / Task #9 — PlanExplanationDTO
//
// Decoded from the `llmSummary` field of PlanCoreDTO (camelCase wire format,
// no key conversion — same camelDecoder as the rest of the Plan envelope).
// Maps to the iOS `PlanExplanation` domain model.
//
// Safety: the backend `sanitize_or_fallback()` guarantees that:
//   - No prohibited phrase (SAFETY_DISCLAIMERS §C) appears in any field.
//   - `safetyNote` contains the §A disclaimer verbatim.
//   - When extreme_heat_risk, `safetyNote` is prepended with §B text verbatim.
//   - No restaurant name appears that wasn't in the structured `food_recommendations` input.

struct PlanExplanationDTO: Codable, Hashable {
    let summary: String
    let scenarioExplanations: [String: String]
    let weatherNote: String?
    let foodNote: String?
    let safetyNote: String
    let provider: String
    let model: String?
    let generatedAt: Date   // decoded via camelDecoder's .iso8601 dateDecodingStrategy

    /// Map API PlanExplanation → iOS PlanExplanation domain model.
    func toModel() -> PlanExplanation {
        PlanExplanation(
            summary: summary,
            scenarioExplanations: scenarioExplanations,
            weatherNote: weatherNote,
            foodNote: foodNote,
            safetyNote: safetyNote,
            provider: provider,
            model: model,
            generatedAt: generatedAt
        )
    }
}
