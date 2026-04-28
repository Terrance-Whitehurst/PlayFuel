import Foundation

// MARK: - NextAction

/// The most immediately actionable item for the parent, derived deterministically
/// from the plan's timeline by `rules/next_action.py` on the backend.
///
/// The backend walks timeline events, finds the next event whose start_time > now
/// (at plan-generation time), and returns this struct. If no event is within the
/// 6-hour lookahead window, a `recovery_fallback` is returned.
///
/// This is NEVER produced by the LLM — it is a pure rules-engine output.
///
/// Safety note: if `extreme_heat_risk == true` and the event kind is heat-sensitive
/// (`match_start`, `warmup`, `hydration_check`), the backend prepends
/// "Extreme heat — extra hydration. " to the `detail` field. iOS renders verbatim.
///
/// See NUTRITION_FIRST_IA_V1.md §D for the full specification.
struct NextAction: Codable, Hashable, Sendable {

    /// Short event title, e.g. "Pre-match meal". Sourced from the timeline event.
    let title: String

    /// Parent-friendly detail from NEXT_ACTION_COPY_MAP on the backend.
    /// May be prepended with "Extreme heat — extra hydration. " when heat-sensitive.
    let detail: String

    /// Scheduled time of this event. Nil for `recovery_fallback` entries.
    let scheduledFor: Date?

    /// Timeline event kind string, e.g. "warmup", "pre_match_meal".
    /// "recovery_fallback" is a special sentinel kind (not a DB enum value).
    let kind: String

    /// Minutes from plan-generation `now` until the event. Nil for `recovery_fallback`.
    let minsUntil: Int?
}
