import Foundation

/// Human-readable duration formatter for PlayFuel.
///
/// Converts raw integer minute counts into concise hr/min strings,
/// matching iOS convention ("1 hr 15 min", not "1 hour 15 minutes").
///
/// Used at every view site that previously rendered raw `"\(x)m"` or `"\(x) min"` integers:
///   - ScenarioCardView (duration header, gap pill, re-warm-up text)
///   - MatchCreateView (duration picker labels)
///   - FoodCardView (drive time)
///   - NextActionCard (minsUntil badge)
///
/// Format table (format is locked — do NOT change without updating all tests):
///   0        → "0 min"
///   1–59     → "X min"
///   60       → "1 hr"
///   61–119   → "1 hr Y min"
///   ≥120, exact hour → "X hr"
///   ≥120, with minutes → "X hr Y min"
///   negative → "-" + friendly(-minutes)
enum DurationFormatting {

    /// Formats a duration in minutes as a human-readable string.
    ///
    /// - Parameter minutes: Duration in integer minutes. May be negative (overrun).
    /// - Returns: Localized-style string, e.g. "30 min", "1 hr", "1 hr 15 min", "3 hr 45 min"
    static func friendly(minutes: Int) -> String {
        if minutes < 0 { return "-" + friendly(minutes: -minutes) }
        if minutes < 60 { return "\(minutes) min" }
        let hr = minutes / 60
        let min = minutes % 60
        if min == 0 { return "\(hr) hr" }
        return "\(hr) hr \(min) min"
    }
}

// MARK: - Int Extension

extension Int {
    /// Returns `DurationFormatting.friendly(minutes: self)`.
    /// Convenience for use at call sites: `plan.durationMin.asFriendlyDuration`.
    var asFriendlyDuration: String { DurationFormatting.friendly(minutes: self) }
}
