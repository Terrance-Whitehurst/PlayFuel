import Foundation

// MARK: - TimelineEventKind

/// Visual category for timeline event icons / colors.
enum TimelineEventKind: String, Codable, CaseIterable {
    case wakeUp         // Alarm icon
    case meal           // Fork/knife icon
    case arrive         // Location pin
    case warmUp         // Figure walk
    case match          // Tennis ball
    case recovery       // Heart
    case hydration      // Drop
    // Phase 4 additions — OQ-TRIAGE-1 (matches backend playfuel_api/models/enums.py)
    case gap            // Inter-match gap window
    case foodWindow     // Food/snack window
    case pickup         // Parent pickup window
    case matchEnd       // Estimated match end
}

// MARK: - TimelineEvent

/// A single chronological event in the tournament-day timeline.
/// Phase 3: part of the Plan's `timeline` array in plan_json.
struct TimelineEvent: Codable, Identifiable, Hashable {

    let id: UUID

    /// Display time string, e.g. "6:00 AM". Phase 3: ISO 8601 timestamp.
    let time: String

    /// Short event title, e.g. "Wake Up".
    let title: String

    /// Detail / guidance text shown below the title.
    let detail: String

    /// Visual category for icon and color treatment.
    let kind: TimelineEventKind
}
