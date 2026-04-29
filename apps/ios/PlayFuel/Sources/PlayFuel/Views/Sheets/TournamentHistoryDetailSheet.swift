import SwiftUI

/// Detail sheet for a single `TournamentHistoryEntry`.
///
/// Presented from `DashboardView` when the user taps a tournament row
/// in the calendar's date-selection list or the "Recent" list.
///
/// Sections (each conditional on non-empty data):
///   1. Header   — name, venue + city, date range
///   2. Result   — result pill + match count
///   3. Highlights — bulleted list
///   4. Notes    — free-text parent notes
///   5. Location — venue name + city (Map snippet deferred for v1)
struct TournamentHistoryDetailSheet: View {

    let entry: TournamentHistoryEntry
    @Environment(\.dismiss) private var dismiss

    private let calendar = Calendar.current

    var body: some View {
        NavigationStack {
            List {
                // ── 1. Header ──────────────────────────────────────────
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(entry.name)
                            .font(.title3.weight(.bold))

                        Label {
                            Text("\(entry.venueName), \(entry.city)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        } icon: {
                            Image(systemName: "mappin.and.ellipse")
                                .foregroundStyle(Color.accentColor)
                                .font(.subheadline)
                        }

                        Label {
                            Text(dateRangeText)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        } icon: {
                            Image(systemName: "calendar")
                                .foregroundStyle(Color.accentColor)
                                .font(.subheadline)
                        }
                    }
                    .padding(.vertical, 4)
                }

                // ── 2. Result ──────────────────────────────────────────
                Section {
                    HStack {
                        Text("Result")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(entry.result)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(resultColor)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(resultColor.opacity(0.12), in: Capsule())
                    }

                    HStack {
                        Text("Matches played")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("\(entry.matchCount)")
                            .font(.subheadline.weight(.semibold))
                    }
                }

                // ── 3. Highlights ──────────────────────────────────────
                if !entry.highlights.isEmpty {
                    Section("Highlights") {
                        ForEach(entry.highlights, id: \.self) { highlight in
                            HStack(alignment: .top, spacing: 8) {
                                Image(systemName: "star.fill")
                                    .font(.caption2)
                                    .foregroundStyle(.yellow)
                                    .padding(.top, 3)
                                Text(highlight)
                                    .font(.subheadline)
                            }
                        }
                    }
                }

                // ── 4. Notes ───────────────────────────────────────────
                if !entry.notes.isEmpty {
                    Section("Notes") {
                        Text(entry.notes)
                            .font(.subheadline)
                    }
                }

                // ── 5. Location ────────────────────────────────────────
                Section("Location") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.venueName)
                            .font(.subheadline.weight(.semibold))
                        Text(entry.city)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 2)
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Tournament Detail")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Helpers

    private var dateRangeText: String {
        if calendar.isDate(entry.startDate, inSameDayAs: entry.endDate) {
            return entry.startDate.formatted(.dateTime.month(.wide).day().year())
        }
        let start = entry.startDate.formatted(.dateTime.month(.abbreviated).day())
        let end   = entry.endDate.formatted(.dateTime.month(.abbreviated).day().year())
        return "\(start) – \(end)"
    }

    private var resultColor: Color {
        if entry.result.contains("Champion")    { return .green }
        if entry.result.contains("Runner-up")   { return .mint }
        if entry.result.contains("Semi")        { return .blue }
        if entry.result.contains("Quarter")     { return .orange }
        if entry.result.contains("Withdrew")    { return .red }
        return .secondary
    }
}

// MARK: - Previews

#Preview {
    TournamentHistoryDetailSheet(entry: FakeHistoryData.dummyHistory[5])
        .presentationDetents([.medium, .large])
}

#Preview("Dark") {
    TournamentHistoryDetailSheet(entry: FakeHistoryData.dummyHistory[5])
        .presentationDetents([.medium, .large])
        .preferredColorScheme(.dark)
}
