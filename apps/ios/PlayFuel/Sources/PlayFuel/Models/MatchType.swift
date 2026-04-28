import Foundation

// MARK: - MatchType

/// Singles vs. doubles match distinction.
/// Raw values match the DB `matches.format` column text values exactly.
///
/// Doubles spec (DOUBLES_SPEC_V1.md §A.4):
///   - "singles" → default / existing matches when format column is null
///   - "doubles" → requires DoublesFormat selection in MatchCreateView
enum MatchType: String, Codable, CaseIterable, Hashable, Sendable {
    case singles
    case doubles

    /// Display label used in the segmented picker on TournamentDashboardView.
    var displayName: String {
        switch self {
        case .singles: return "Singles"
        case .doubles: return "Doubles"
        }
    }
}

// MARK: - DoublesFormat

/// Doubles match format. Only meaningful when MatchType == .doubles.
/// Raw values match the DB `matches.doubles_format` column text values exactly.
///
/// Scenario duration constants per format (DOUBLES_SPEC_V1.md §B.1 — all DRAFT):
///   bestOf3:  short=60, normal=90,  long=135
///   proSet8:  short=45, normal=70,  long=100
enum DoublesFormat: String, Codable, CaseIterable, Hashable, Sendable {
    case bestOf3 = "best_of_3"
    case proSet8 = "pro_set_8"

    /// Display label used in the segmented picker on MatchCreateView.
    var displayName: String {
        switch self {
        case .bestOf3: return "Best of 3"
        case .proSet8: return "8-Game Pro Set"
        }
    }
}
