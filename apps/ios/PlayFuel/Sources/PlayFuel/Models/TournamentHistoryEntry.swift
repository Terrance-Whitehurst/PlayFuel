import Foundation

/// A historical tournament record for display in the Dashboard calendar view.
///
/// All instances in the current build come from `FakeHistoryData.dummyHistory`.
/// When real persistence is wired, this will be decoded from the API.
/// `Codable` is forward-looking so the struct can round-trip through `JSONDecoder`
/// with no changes when the real endpoint ships.
struct TournamentHistoryEntry: Identifiable, Hashable, Codable {
    let id: UUID
    let name: String
    let venueName: String
    let city: String
    let startDate: Date
    let endDate: Date          // Same as startDate for single-day entries
    let result: String         // "Champion", "Runner-up", "Semifinalist", "Quarterfinals",
                               // "Round of 16", "First round", "Withdrew (injury)"
    let notes: String          // Free-text parent notes
    let highlights: [String]   // 2–3 bullet strings
    let matchCount: Int
}
