import Foundation

/// The full tournament-day plan for one tournament.
/// Mirrors the `tournament_plans.plan_json` structure from spec §13.
/// Phase 3: decoded from `POST /tournaments/{id}/generate-plan`
///          and recalled via `GET /tournaments/{id}/plans/latest`.
struct Plan: Codable, Identifiable {

    /// Maps to `tournament_plans.id` in Supabase.
    let id: UUID

    /// Human-readable plan identifier string (mirrors plan_id in API response).
    let planId: String

    /// The tournament this plan belongs to.
    let tournamentId: UUID

    /// ISO 8601 generation timestamp. Kept as String for prototype.
    let generatedAt: String

    /// Aggregated warning codes from all ScenarioPlans (§G.4).
    /// e.g. ["MATCH_OVERRUN"] if any scenario overruns.
    let warnings: [String]

    /// Short (75min), Normal (120min), Long (180min) scenario plans.
    let scenarioPlans: [ScenarioPlan]

    /// Weather snapshot at plan generation time.
    let weather: WeatherSnapshot

    /// Nearby food options (3–5 per §16 / US-08).
    let foodOptions: [FoodOption]

    /// Chronological day timeline from wake-up through recovery.
    let timeline: [TimelineEvent]
}
