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
    // Phase 7 — Doubles spec (DOUBLES_SPEC_V1.md §C.1)
    // Emitted by the backend at T−60m when match_type == "doubles".
    // TimelineView.swift exhaustive switches must handle this case.
    case partnerCoordination  // Doubles-only: confirm with doubles partner
    // ACCOMMODATIONS_V1 — departure event (§E.2)
    // Emitted when accommodation is set; anchored at match_start - ARRIVE_SNACK_MIN - drive_minutes.
    // iOS renders with car or figure.walk icon (see TimelineView kindIcon switch).
    // Added in lockstep with Python enums.py TimelineEventKind.departure = "departure".
    case departure  // Leave accommodation — drive to venue
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
