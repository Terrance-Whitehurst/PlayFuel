import Foundation

// MARK: - PlanEnvelope

/// Wraps the per-match plans returned by
/// `POST /v1/tournaments/{tid}/plans/generate`.
///
/// NUTRITION_FIRST_IA_V1.md §E (Phase 8 breaking change):
/// The API now returns one Plan per match, grouped by match type.
///
///   singlesPlans: [Plan]  — ordered by match scheduledStart ASC; empty when no singles matches
///   doublesPlans: [Plan]  — ordered by match scheduledStart ASC; empty when no doubles matches
///
/// iOS usage (DOUBLES_SPEC_V1.md §E.1 + NUTRITION_FIRST_IA_V1.md §B):
///   - hasBothTypes == false → Dashboard renders the active plan without a type picker
///   - hasBothTypes == true  → Dashboard shows segmented "Singles | Doubles" picker
///   - ScheduleStripView consumes `allPlans` and drives selection via `AppState.selectedMatchId`
///
/// CODABLE NOTE: No stored-property defaults on let fields (Session 2 lesson).
/// All call sites must pass values explicitly.
struct PlanEnvelope: Codable, Sendable {

    /// Plans for singles matches, ordered by match scheduledStart ASC.
    let singlesPlans: [Plan]

    /// Plans for doubles matches, ordered by match scheduledStart ASC.
    let doublesPlans: [Plan]

    // MARK: - Convenience

    /// True when both singles and doubles plans are present.
    /// Dashboard shows the segmented picker only when this is true.
    var hasBoth: Bool { !singlesPlans.isEmpty && !doublesPlans.isEmpty }

    /// Alias for existing call sites that referenced `hasBothTypes`.
    var hasBothTypes: Bool { hasBoth }

    /// All plans from both types, singles first then doubles.
    var allPlans: [Plan] { singlesPlans + doublesPlans }

    /// The first non-nil plan (singles preferred). Used for single-type and legacy
    /// code paths that don't need type discrimination.
    var anyPlan: Plan? { singlesPlans.first ?? doublesPlans.first }

    // MARK: - Lookup

    /// Returns the plan for the given match UUID, searching both arrays.
    /// Used by TournamentDashboardView when selectedMatchId is set.
    func plan(for matchId: UUID) -> Plan? {
        allPlans.first { $0.matchId == matchId }
    }

    /// Returns the first plan for the given match type.
    /// Used for the Singles | Doubles segmented picker when hasBothTypes == true.
    func plan(for type: MatchType) -> Plan? {
        type == .singles ? singlesPlans.first : doublesPlans.first
    }

    // MARK: - Default Selection

    /// Returns the plan whose match starts soonest after `now`.
    /// Falls back to the most-recently-completed plan, then `anyPlan`.
    /// Used by AppState.defaultMatchId(from:now:).
    func nextUpcomingPlan(now: Date = .now) -> Plan? {
        let iso = ISO8601DateFormatter()
        let plans = allPlans

        // 1. Next upcoming
        let upcoming = plans.compactMap { plan -> (Plan, Date)? in
            guard let str = plan.scheduledStart,
                  let date = iso.date(from: str),
                  date > now else { return nil }
            return (plan, date)
        }
        if let first = upcoming.min(by: { $0.1 < $1.1 })?.0 { return first }

        // 2. Most recently completed (latest scheduledStart in the past)
        let past = plans.compactMap { plan -> (Plan, Date)? in
            guard let str = plan.scheduledStart,
                  let date = iso.date(from: str),
                  date <= now else { return nil }
            return (plan, date)
        }
        if let latest = past.max(by: { $0.1 < $1.1 })?.0 { return latest }

        // 3. Fallback
        return anyPlan
    }
}
