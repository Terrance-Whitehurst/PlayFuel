import SwiftUI

/// Tournament History Dashboard.
///
/// Presented as a full-screen sheet from ProfileMenuSheet → Dashboard row.
/// All data comes from `FakeHistoryData.dummyHistory` until real API
/// history persistence is wired.
///
/// Layout:
///   • Month switcher  (← April 2026 →)
///   • CalendarMonthGrid — dots on days with tournament entries
///   • When a date is selected: entry list for that day
///   • When no date selected: "Recent" list (last 3 by date)
///   • Tap any entry → TournamentHistoryDetailSheet
struct DashboardView: View {

    @Environment(\.dismiss) private var dismiss
    @State private var displayedMonth: Date = Date()
    @State private var selectedDate:   Date? = nil
    @State private var selectedEntry:  TournamentHistoryEntry? = nil

    private let history  = FakeHistoryData.dummyHistory
    private let calendar = Calendar.current

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    // ── Month switcher ─────────────────────────────────
                    monthSwitcher
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)

                    // ── Calendar grid ──────────────────────────────────
                    CalendarMonthGrid(
                        displayedMonth: displayedMonth,
                        markedDates:    markedDatesInDisplayedMonth,
                        selectedDate:   $selectedDate
                    )
                    .padding(.horizontal, 16)

                    Divider()
                        .padding(.vertical, 12)

                    // ── Entry list / recent list ───────────────────────
                    if let selected = selectedDate {
                        entriesSection(for: selected)
                            .padding(.horizontal, 16)
                    } else {
                        recentSection
                            .padding(.horizontal, 16)
                    }

                    Spacer(minLength: 32)
                }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Tournament History")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .sheet(item: $selectedEntry) { entry in
                TournamentHistoryDetailSheet(entry: entry)
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
        }
    }

    // MARK: - Month Switcher

    private var monthSwitcher: some View {
        HStack {
            Button {
                displayedMonth = calendar.date(byAdding: .month, value: -1, to: displayedMonth) ?? displayedMonth
                selectedDate = nil
            } label: {
                Image(systemName: "chevron.left")
                    .font(.title3.weight(.semibold))
                    .padding(8)
                    .contentShape(Rectangle())
            }

            Spacer()

            Text(displayedMonth.formatted(.dateTime.month(.wide).year()))
                .font(.headline)

            Spacer()

            Button {
                displayedMonth = calendar.date(byAdding: .month, value: 1, to: displayedMonth) ?? displayedMonth
                selectedDate = nil
            } label: {
                Image(systemName: "chevron.right")
                    .font(.title3.weight(.semibold))
                    .padding(8)
                    .contentShape(Rectangle())
            }
        }
    }

    // MARK: - Calendar Dot Data

    /// Start dates of entries whose startDate falls in the displayed month.
    /// Used by CalendarMonthGrid to render the small dot below a day number.
    private var markedDatesInDisplayedMonth: [Date] {
        history
            .filter { calendar.isDate($0.startDate, equalTo: displayedMonth, toGranularity: .month) }
            .map { $0.startDate }
    }

    // MARK: - Filtered Entries

    /// Returns all entries that cover the given date (start ≤ date ≤ end).
    private func entriesOn(_ date: Date) -> [TournamentHistoryEntry] {
        let target = calendar.startOfDay(for: date)
        return history.filter { entry in
            let start = calendar.startOfDay(for: entry.startDate)
            let end   = calendar.startOfDay(for: entry.endDate)
            return start <= target && target <= end
        }
        .sorted { $0.startDate > $1.startDate }
    }

    // MARK: - Selected Date Section

    @ViewBuilder
    private func entriesSection(for date: Date) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(date.formatted(.dateTime.weekday(.wide).month().day()))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 4)

            if entriesOn(date).isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "calendar.badge.minus")
                        .font(.system(size: 32))
                        .foregroundStyle(.secondary)
                    Text("No tournaments on this day")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
            } else {
                ForEach(entriesOn(date)) { entry in
                    HistoryEntryRow(entry: entry)
                        .onTapGesture { selectedEntry = entry }
                }
            }
        }
    }

    // MARK: - Recent Section (no date selected)

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recent Tournaments")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 4)

            ForEach(recentEntries) { entry in
                HistoryEntryRow(entry: entry)
                    .onTapGesture { selectedEntry = entry }
            }
        }
    }

    private var recentEntries: [TournamentHistoryEntry] {
        Array(history.sorted { $0.startDate > $1.startDate }.prefix(3))
    }
}

// MARK: - History Entry Row

/// Compact card row used in both the date-selection list and the "Recent" list.
private struct HistoryEntryRow: View {
    let entry: TournamentHistoryEntry

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text(entry.city)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                Text(entry.result)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(resultColor(entry.result))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(resultColor(entry.result).opacity(0.12), in: Capsule())

                Text(entry.startDate.formatted(.dateTime.month(.abbreviated).day()))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10))
    }

    private func resultColor(_ result: String) -> Color {
        if result.contains("Champion")   { return .green }
        if result.contains("Runner-up")  { return .mint }
        if result.contains("Semi")       { return .blue }
        if result.contains("Quarter")    { return .orange }
        if result.contains("Withdrew")   { return .red }
        return .secondary
    }
}

// MARK: - Previews

#Preview {
    DashboardView()
}

#Preview("Dark") {
    DashboardView()
        .preferredColorScheme(.dark)
}
