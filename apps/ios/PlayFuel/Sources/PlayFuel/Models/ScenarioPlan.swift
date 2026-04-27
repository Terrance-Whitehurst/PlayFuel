import Foundation

// MARK: - Supporting Enums (RULES_CONSTANTS_V1 §B / §G)

/// Gap status per §G.1. Carried on every ScenarioPlan.
enum GapStatus: String, Codable {
    case ok
    case tight
    case overrun
    case no_next_match
}

/// Food strategy bucket per §B.2. Ranges (half-open, lower-inclusive):
///   bag_only    [0, 45)
///   portable    [45, 90)
///   quick_pickup [90, 150)
///   light_meal  [150, ∞)
enum FoodBucket: String, Codable {
    case bag_only
    case portable
    case quick_pickup
    case light_meal
}

/// Parent pickup strategy bucket per §B.3. Ranges:
///   bring_portable       [0, 60)
///   pickup_during_match  [60, 120)
///   wait_until_end       [120, ∞)
enum PickupBucket: String, Codable {
    case bring_portable
    case pickup_during_match
    case wait_until_end
}

// MARK: - Supporting Structs

/// Food strategy: bucket + display text from §B.2 canonical text.
struct FoodStrategy: Codable, Hashable {
    let bucket: FoodBucket
    let text: String
}

/// Parent pickup strategy: optional bucket + display text from §B.3.
/// `bucket` is nil for `no_next_match` (§G.5).
struct PickupStrategy: Codable, Hashable {
    let bucket: PickupBucket?
    let text: String
}

/// Re-warm-up window relative to `estimated_next_match_start` (§D.2).
///   startOffsetMin: -30  (T-30 min before next match start)
///   durationMin:     20  (20-minute dynamic warm-up)
/// nil when gap_minutes < 60 or gap_status == .overrun.
struct RewarmUp: Codable, Hashable {
    let startOffsetMin: Int   // negative = before next match start
    let durationMin: Int
}

/// Overrun warning per §G.3 and §H.1.
struct OverrunWarning: Codable, Hashable {
    let code: String        // "MATCH_OVERRUN"
    let severity: String    // "high"
    let minutesOver: Int
    let message: String     // verbatim from §H.1 OVERRUN_MESSAGE
}

// MARK: - ScenarioPlan

/// A single match-duration scenario plan.
/// JSON shape mirrors RULES_CONSTANTS_V1 §G.2 / §G.3 / §G.5 exactly.
/// Phase 3: decoded from `POST /tournaments/{id}/generate-plan` response.
struct ScenarioPlan: Codable, Identifiable, Hashable {

    /// Client-side UUID for SwiftUI list identity. Not in server schema — generated on decode.
    let id: UUID

    /// "short" | "normal" | "long"
    let scenario: String

    /// Match duration in minutes per §A.1 (75 / 120 / 180).
    let durationMin: Int

    /// Human-readable estimated match end time, e.g. "10:15 AM".
    let estimatedEnd: String

    /// Gap in minutes between estimated match end and next match start.
    /// nil for `no_next_match`.
    let gapMinutes: Int?

    /// Gap status per §G.1.
    let gapStatus: GapStatus

    /// Food strategy. nil for `no_next_match` (§G.5).
    let foodStrategy: FoodStrategy?

    /// Parent pickup strategy. Always present (never nil), but `bucket` may be nil (§G.5).
    let pickupStrategy: PickupStrategy

    /// Re-warm-up window. nil when gap_minutes < 60 or overrun (§D.2, §G.3).
    let rewarmUp: RewarmUp?

    /// Overrun warning. nil unless `gapStatus == .overrun` (§G.3).
    let overrunWarning: OverrunWarning?

    /// Warning code strings, e.g. ["MATCH_OVERRUN"]. Empty array when no warnings.
    let warnings: [String]

    // MARK: - Display helpers

    var scenarioLabel: String {
        switch scenario {
        case "short":  return "Short"
        case "normal": return "Normal"
        case "long":   return "Long"
        default:       return scenario.capitalized
        }
    }
}
