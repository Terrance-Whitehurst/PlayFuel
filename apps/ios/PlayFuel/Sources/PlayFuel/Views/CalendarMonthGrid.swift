import SwiftUI

/// Pure SwiftUI calendar grid for one displayed month.
///
/// Shows a weekday header row (S M T W T F S) + a 7-column LazyVGrid of day cells.
/// Days with tournament entries get a small accent-colour dot below the number.
/// The selected day gets a filled accent circle; today gets a ring outline.
///
/// Usage:
/// ```swift
/// CalendarMonthGrid(
///     displayedMonth: $displayedMonth,
///     markedDates: myDates,
///     selectedDate: $selectedDate
/// )
/// ```
struct CalendarMonthGrid: View {

    let displayedMonth: Date
    let markedDates: [Date]
    @Binding var selectedDate: Date?

    private let calendar = Calendar.current
    private let columns  = Array(repeating: GridItem(.flexible()), count: 7)
    // Abbreviated symbols — S and T appear twice (Sunday/Saturday, Tuesday/Thursday).
    // ForEach uses index-based identity to avoid key collisions.
    private let weekdayLabels = ["S", "M", "T", "W", "T", "F", "S"]

    var body: some View {
        VStack(spacing: 4) {
            // Weekday header row
            LazyVGrid(columns: columns, spacing: 4) {
                ForEach(0..<weekdayLabels.count, id: \.self) { i in
                    Text(weekdayLabels[i])
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }

            // Day grid
            LazyVGrid(columns: columns, spacing: 4) {
                // Leading empty cells so day 1 falls on the correct weekday column
                ForEach(0..<leadingEmptyCells, id: \.self) { _ in
                    Color.clear.frame(height: 38)
                }

                // Numbered day cells
                ForEach(1...max(1, daysInMonth), id: \.self) { day in
                    DayGridCell(
                        day:        day,
                        isSelected: isSelected(day: day),
                        isToday:    isToday(day: day),
                        hasEntry:   hasEntry(day: day)
                    )
                    .onTapGesture {
                        selectedDate = dateForDay(day)
                    }
                }
            }
        }
    }

    // MARK: - Calendar Math

    private var firstDayOfMonth: Date {
        let comps = calendar.dateComponents([.year, .month], from: displayedMonth)
        return calendar.date(from: comps) ?? displayedMonth
    }

    /// Number of empty cells before day 1 (Sunday-first calendar).
    /// `weekday` is 1 = Sunday … 7 = Saturday, so leading cells = weekday - 1.
    private var leadingEmptyCells: Int {
        calendar.component(.weekday, from: firstDayOfMonth) - 1
    }

    private var daysInMonth: Int {
        calendar.range(of: .day, in: .month, for: displayedMonth)?.count ?? 30
    }

    private func dateForDay(_ day: Int) -> Date {
        var comps = calendar.dateComponents([.year, .month], from: displayedMonth)
        comps.day = day
        return calendar.date(from: comps) ?? displayedMonth
    }

    private func isSelected(day: Int) -> Bool {
        guard let sel = selectedDate else { return false }
        return calendar.isDate(sel, equalTo: dateForDay(day), toGranularity: .day)
    }

    private func isToday(day: Int) -> Bool {
        calendar.isDateInToday(dateForDay(day))
    }

    /// Returns true if any of the `markedDates` falls on this day.
    private func hasEntry(day: Int) -> Bool {
        let target = dateForDay(day)
        return markedDates.contains { calendar.isDate($0, inSameDayAs: target) }
    }
}

// MARK: - Day Cell

/// Single calendar cell.
private struct DayGridCell: View {
    let day:        Int
    let isSelected: Bool
    let isToday:    Bool
    let hasEntry:   Bool

    var body: some View {
        VStack(spacing: 2) {
            ZStack {
                // Background circle for selected state
                if isSelected {
                    Circle()
                        .fill(Color.accentColor)
                        .frame(width: 30, height: 30)
                } else if isToday {
                    Circle()
                        .strokeBorder(Color.accentColor, lineWidth: 1.5)
                        .frame(width: 30, height: 30)
                }

                Text("\(day)")
                    .font(isToday ? .caption.weight(.bold) : .caption)
                    .foregroundStyle(
                        isSelected ? .white :
                        isToday    ? Color.accentColor :
                        Color.primary
                    )
            }

            // Dot indicator for tournament entries
            if hasEntry {
                Circle()
                    .fill(isSelected ? .white : Color.accentColor)
                    .frame(width: 5, height: 5)
            } else {
                // Preserve consistent cell height even without a dot
                Color.clear.frame(width: 5, height: 5)
            }
        }
        .frame(height: 38)
        .contentShape(Rectangle())
    }
}

// MARK: - Previews

#Preview {
    let cal   = Calendar.current
    let today = Date()
    let marked = [
        cal.date(byAdding: .day, value: -7, to: today) ?? today,
        cal.date(byAdding: .day, value:  3, to: today) ?? today,
        cal.date(byAdding: .day, value: 10, to: today) ?? today,
    ]
    return CalendarMonthGrid(
        displayedMonth: today,
        markedDates:    marked,
        selectedDate:   .constant(today)
    )
    .padding()
}

#Preview("Dark") {
    let cal   = Calendar.current
    let today = Date()
    let marked = [
        cal.date(byAdding: .day, value: -7, to: today) ?? today,
        cal.date(byAdding: .day, value:  3, to: today) ?? today,
        cal.date(byAdding: .day, value: 10, to: today) ?? today,
    ]
    return CalendarMonthGrid(
        displayedMonth: today,
        markedDates:    marked,
        selectedDate:   .constant(today)
    )
    .padding()
    .preferredColorScheme(.dark)
}
