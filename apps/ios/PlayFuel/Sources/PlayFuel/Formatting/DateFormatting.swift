import Foundation

/// Human-readable timestamp formatter for PlayFuel.
///
/// Converts `Date` objects and ISO 8601 strings into concise, locale-aware
/// clock-time strings for display in the timeline and next-action surfaces.
///
/// Used at:
///   - TimelineView (left-column event timestamp — was raw ISO "2026-04-28T19:00:00+00:00")
///   - Any future view rendering `TimelineEvent.time` or schedule timestamps
///
/// Format spec:
///   Same-day event  → "7:00 PM"
///   Different-day   → "Mon · 7:00 PM"
///   ISO 8601 String → parses then formats; non-ISO strings pass through unchanged
///
/// Companion to DurationFormatting.swift (minute-count → "X hr Y min").
enum DateFormatting {

    // MARK: - Core formatters

    /// Clock time only. "7:00 PM"
    ///
    /// Uses `Date.FormatStyle` (iOS 15+) — locale-aware, no `DateFormatter` reuse pitfalls.
    static func clockTime(_ date: Date) -> String {
        date.formatted(date: .omitted, time: .shortened)
    }

    /// Compact event timestamp for timeline left column.
    ///
    /// Same-day-as-reference: `"7:00 PM"`
    /// Different-day-from-reference: `"Mon · 7:00 PM"`
    ///
    /// - Parameters:
    ///   - date: The event date to format.
    ///   - referenceDate: The "today" anchor. Defaults to `Date()` (now).
    static func eventTimestamp(_ date: Date, referenceDate: Date = Date()) -> String {
        let cal = Calendar.current
        if cal.isDate(date, inSameDayAs: referenceDate) {
            return clockTime(date)
        }
        let weekday = date.formatted(.dateTime.weekday(.abbreviated))
        return "\(weekday) · \(clockTime(date))"
    }

    /// Relative countdown phrase for next-action badge etc.
    ///
    /// Composes with `DurationFormatting.friendly` so "in 28 min" / "in 1 hr 30 min" are
    /// consistent with all other minute-count displays in the app.
    ///
    /// - Parameters:
    ///   - date: The target date.
    ///   - now: Current time anchor. Defaults to `Date()`.
    /// - Returns: e.g. `"in 28 min"`, `"in 1 hr 30 min"`, or `"now"` when ≤ 0 minutes away.
    static func relativeFromNow(_ date: Date, now: Date = Date()) -> String {
        let mins = Int(date.timeIntervalSince(now) / 60)
        if mins <= 0 { return "now" }
        return "in " + DurationFormatting.friendly(minutes: mins)
    }
}

// MARK: - Date Extensions

extension Date {
    /// Clock time only. `"7:00 PM"`.
    var asClockTime: String { DateFormatting.clockTime(self) }

    /// Same-day: `"7:00 PM"`. Different-day: `"Mon · 7:00 PM"`.
    var asEventTimestamp: String { DateFormatting.eventTimestamp(self) }
}

// MARK: - String Extension

extension String {
    /// Parse as ISO 8601 then format as clock time.
    ///
    /// Returns the original string unchanged on parse failure — safe to call on
    /// non-ISO strings like FakeData's `"During Match"` or `"~11:00 AM"`.
    ///
    /// Handles both `Z` and `±hh:mm` offset forms (e.g. `"2026-04-28T19:00:00+00:00"`).
    var asClockTimeFromISO: String {
        let formatter = ISO8601DateFormatter()
        // .withInternetDateTime covers full date+time with timezone offset/Z.
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: self) {
            return DateFormatting.clockTime(date)
        }
        // Fallback: try the system default (handles some edge-case variants).
        if let date = ISO8601DateFormatter().date(from: self) {
            return DateFormatting.clockTime(date)
        }
        // Non-ISO string (e.g. FakeData's "During Match", "6:00 AM") — pass through unchanged.
        return self
    }
}
