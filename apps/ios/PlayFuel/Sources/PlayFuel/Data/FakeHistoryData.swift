// ──────────────────────────────────────────────────────────────────────────
// FakeHistoryData — Preview-only dummy tournament history for DashboardView.
//
// Dates are derived from Date() at first access so they stay relative to
// the current date year-over-year (no hardcoded year).
//
// Real data will come from the API once tournament history persistence ships.
// Safety rule: no medical claims, no prohibited phrases from §C.
// ──────────────────────────────────────────────────────────────────────────
import Foundation

enum FakeHistoryData {

    // MARK: - Date Helpers

    private static func daysAgo(_ days: Int) -> Date {
        Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date()
    }

    private static func daysAgo(_ days: Int, offsetBy offset: Int) -> Date {
        Calendar.current.date(byAdding: .day, value: -(days - offset), to: Date()) ?? Date()
    }

    // MARK: - Dummy History (10 entries, ~6 months)

    static let dummyHistory: [TournamentHistoryEntry] = [

        // ── 1 week ago — Quarterfinals, Dallas ──────────────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000001-0000-0000-0000-000000000001")!,
            name: "North Texas Junior Classic",
            venueName: "Samuell Grand Tennis Center",
            city: "Dallas, TX",
            startDate: daysAgo(7),
            endDate: daysAgo(7),
            result: "Quarterfinals",
            notes: "Played through heat — solid mental toughness in the second set. Hydration was on point.",
            highlights: [
                "Won first round 6-2, 6-3 against the #5 seed",
                "Came back from 1-5 down in second set to force tiebreak",
                "Lost a close QF 6-7, 4-6 — best run this season so far"
            ],
            matchCount: 3
        ),

        // ── 3 weeks ago — Round of 16, Fort Worth ───────────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000002-0000-0000-0000-000000000002")!,
            name: "Trinity River Open",
            venueName: "Fort Worth Botanic Garden Courts",
            city: "Fort Worth, TX",
            startDate: daysAgo(21),
            endDate: daysAgo(21),
            result: "Round of 16",
            notes: "Dropped a close one in the second set. Need to work on net approaches when ahead.",
            highlights: [
                "Won opener 7-5, 6-4 in a tough match",
                "R16 loss came down to two break points at 5-5 — tight match"
            ],
            matchCount: 2
        ),

        // ── 5 weeks ago — Withdrew, Houston ─────────────────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000003-0000-0000-0000-000000000003")!,
            name: "Bayou Classic Junior",
            venueName: "Memorial Park Tennis Center",
            city: "Houston, TX",
            startDate: daysAgo(35),
            endDate: daysAgo(34),
            result: "Withdrew (injury)",
            notes: "Withdrew after Match 1 due to hamstring tightness. Prioritized health over the draw. Good decision.",
            highlights: [
                "Won opening match 6-3, 6-1 before withdrawal",
                "Body was signaling all morning — right call to pull out"
            ],
            matchCount: 1
        ),

        // ── 7 weeks ago — Semifinalist, OKC (multi-day) ─────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000004-0000-0000-0000-000000000004")!,
            name: "Sooner State Junior Championships",
            venueName: "OKC Tennis Center",
            city: "Oklahoma City, OK",
            startDate: daysAgo(49),
            endDate: daysAgo(48),
            result: "Semifinalist",
            notes: "Best tournament of the year so far. Beat the #3 seed in the QF — a real statement win.",
            highlights: [
                "Beat the #3 seed 7-5, 3-6, 6-3 in quarterfinals",
                "SF loss was close — 4-6, 6-3, 5-7 in a 3-set battle",
                "Showed real ability to recover after losing a set"
            ],
            matchCount: 4
        ),

        // ── 9 weeks ago — First round, Tulsa ────────────────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000005-0000-0000-0000-000000000005")!,
            name: "Green Country Junior Open",
            venueName: "Tulsa Tennis Club",
            city: "Tulsa, OK",
            startDate: daysAgo(63),
            endDate: daysAgo(63),
            result: "First round",
            notes: "Arrived late due to highway traffic, rushed warm-up. Lesson learned: leave 30 min earlier.",
            highlights: [
                "Lost 4-6, 3-6 — never found rhythm after the rushed arrival",
                "Opponent was well-prepared and consistent"
            ],
            matchCount: 1
        ),

        // ── 11 weeks ago — Runner-up, San Antonio (multi-day) ───────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000006-0000-0000-0000-000000000006")!,
            name: "Alamo Junior Classic",
            venueName: "San Antonio Country Club Courts",
            city: "San Antonio, TX",
            startDate: daysAgo(77),
            endDate: daysAgo(76),
            result: "Runner-up",
            notes: "Incredible run to the final. Lost a close match but competed brilliantly all weekend.",
            highlights: [
                "Went 4-1 through the draw before the final",
                "Final loss was 5-7, 6-3, 4-6 — played at a high level throughout",
                "Career-best result to date going into this run"
            ],
            matchCount: 5
        ),

        // ── 14 weeks ago — Quarterfinals, Austin (multi-day) ────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000007-0000-0000-0000-000000000007")!,
            name: "Capital City Junior Open",
            venueName: "Pharr Tennis Center",
            city: "Austin, TX",
            startDate: daysAgo(98),
            endDate: daysAgo(97),
            result: "Quarterfinals",
            notes: "Rained out Saturday morning, afternoon matches were exhausting. Energy was lower by Sunday.",
            highlights: [
                "Won two Saturday matches after the rain delay",
                "Pushed the eventual champion to 7-5 in the third set"
            ],
            matchCount: 3
        ),

        // ── 17 weeks ago — Round of 16, Dallas ──────────────────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000008-0000-0000-0000-000000000008")!,
            name: "Lone Star Junior Open",
            venueName: "Samuell Grand Tennis Center",
            city: "Dallas, TX",
            startDate: daysAgo(119),
            endDate: daysAgo(119),
            result: "Round of 16",
            notes: "Good solid play. Came back from a set down in the second match — shows grit.",
            highlights: [
                "Won the opening match 3-6, 7-5, 6-2 after being down a set",
                "R16 opponent was seeded #2 — competitive loss"
            ],
            matchCount: 2
        ),

        // ── 20 weeks ago — Semifinalist, Houston (multi-day) ────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "00000009-0000-0000-0000-000000000009")!,
            name: "Memorial Park Open",
            venueName: "Memorial Park Tennis Center",
            city: "Houston, TX",
            startDate: daysAgo(140),
            endDate: daysAgo(139),
            result: "Semifinalist",
            notes: "Second semifinal of the season — consistent improvement showing week over week.",
            highlights: [
                "Beat the #4 seed in the QF",
                "SF loss was competitive — opponent went on to win the title"
            ],
            matchCount: 4
        ),

        // ── 24 weeks ago — Champion, Fort Worth (multi-day) ─────────────
        TournamentHistoryEntry(
            id: UUID(uuidString: "0000000a-0000-0000-0000-00000000000a")!,
            name: "Panther City Cup",
            venueName: "Fort Worth Botanic Garden Courts",
            city: "Fort Worth, TX",
            startDate: daysAgo(168),
            endDate: daysAgo(167),
            result: "Champion",
            notes: "Career win. Beat the top seed 6-3, 6-2 in the final. One to remember.",
            highlights: [
                "Beat the top seed 6-3, 6-2 in the final",
                "Went undefeated through the entire draw (5-0)",
                "Dominant serving performance all weekend — 12 aces total"
            ],
            matchCount: 5
        ),
    ]
}
