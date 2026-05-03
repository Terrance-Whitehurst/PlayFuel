/// Round vocabulary for draw-size picker and match-round picker.
///
/// Keep in sync with Python `ROUND_LABELS` in
/// `apps/api/src/playfuel_api/rules/constants.py`.
///
/// Numeric representation: the number of players still alive at that stage
/// (32 = Round of 32, 8 = Quarterfinal, 2 = Final). NOT a sequential round
/// number. This matches the DB column `matches.round` and `tournaments.draw_size`.
enum RoundVocab {

    /// Valid draw sizes, in picker display order.
    static let drawSizes: [Int] = [32, 64, 128, 256]

    /// Returns valid round values for a given draw size, earliest stage first.
    /// e.g. drawSize=64 → [64, 32, 16, 8, 4, 2]
    static func roundOptions(for drawSize: Int) -> [Int] {
        var rounds: [Int] = []
        var r = drawSize
        while r >= 2 {
            rounds.append(r)
            r /= 2
        }
        return rounds
    }

    /// Full display label for iOS picker rows (spelled-out for accessibility).
    /// e.g. 8 → "Quarterfinal", 32 → "Round of 32"
    static func label(for round: Int) -> String {
        switch round {
        case 2:  return "Final"
        case 4:  return "Semifinal"
        case 8:  return "Quarterfinal"
        default: return "Round of \(round)"
        }
    }

    /// Short abbreviation used as DB `round_label` and wire value.
    /// e.g. 8 → "QF", 32 → "R32"
    static func abbreviation(for round: Int) -> String {
        switch round {
        case 2:  return "F"
        case 4:  return "SF"
        case 8:  return "QF"
        default: return "R\(round)"
        }
    }

    /// Label for the draw-size segmented picker row.
    /// e.g. 64 → "R64"
    static func drawSizeLabel(_ drawSize: Int) -> String {
        "R\(drawSize)"
    }
}
