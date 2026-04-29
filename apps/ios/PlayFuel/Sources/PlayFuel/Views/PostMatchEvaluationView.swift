import SwiftUI

/// Read-only structured card display for a completed post-match evaluation.
/// Presented inline inside `MatchDetailView`.
///
/// Each section card renders only when the underlying data is non-empty/non-nil.
/// The "Edit" button at the top-right swaps to `PostMatchEvaluationForm` (pre-filled).
///
/// POST_MATCH_EVAL_V1.md §E.4
struct PostMatchEvaluationView: View {

    let evaluation: MatchEvaluation
    let onEdit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {

            // Header row: section title + Edit button
            HStack {
                Text("Post-Match Write-Up")
                    .font(.headline)
                Spacer()
                Button(action: onEdit) {
                    Label("Edit", systemImage: "pencil")
                        .font(.subheadline)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            .padding(.horizontal, 16)

            // Card: Result + Score
            resultCard

            // Card: Ratings — only when at least one rating is set
            if evaluation.effortRating != nil || evaluation.focusRating != nil {
                ratingsCard
            }

            // Card: What Went Well — only when non-empty
            if !evaluation.wentWell.isEmpty {
                bulletCard(
                    title: "What Went Well",
                    systemImage: "checkmark.circle.fill",
                    tint: .green,
                    items: evaluation.wentWell
                )
            }

            // Card: What to Improve — only when non-empty
            if !evaluation.toImprove.isEmpty {
                bulletCard(
                    title: "What to Improve",
                    systemImage: "arrow.up.circle.fill",
                    tint: .orange,
                    items: evaluation.toImprove
                )
            }

            // Card: Opponent Observations — only when non-empty
            if let obs = evaluation.opponentObservations, !obs.isEmpty {
                paragraphCard(
                    title: "Opponent Observations",
                    systemImage: "person.fill.questionmark",
                    tint: .purple,
                    body: obs
                )
            }

            // Card: Key Moments — only when non-empty
            if let moments = evaluation.keyMoments, !moments.isEmpty {
                paragraphCard(
                    title: "Key Moments",
                    systemImage: "star.fill",
                    tint: Color.accentColor,
                    body: moments
                )
            }
        }
    }

    // MARK: - Result Card

    private var resultCard: some View {
        GroupBox {
            HStack(spacing: 12) {
                // Result pill
                Text("\(evaluation.result.emoji) \(evaluation.result.displayName)")
                    .font(.title3.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(resultColor, in: Capsule())

                Spacer()

                // Score (if available)
                if let score = evaluation.scoreText, !score.isEmpty {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Score")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(score)
                            .font(.subheadline.bold())
                    }
                }
            }
        }
        .padding(.horizontal, 16)
    }

    private var resultColor: Color {
        switch evaluation.result {
        case .won:              return .green
        case .lost:             return .red
        case .withdrew, .retired: return Color(.systemGray)
        }
    }

    // MARK: - Ratings Card

    private var ratingsCard: some View {
        GroupBox("Ratings") {
            VStack(alignment: .leading, spacing: 8) {
                if let effort = evaluation.effortRating {
                    ratingRow(label: "Effort", rating: effort)
                }
                if let focus = evaluation.focusRating {
                    ratingRow(label: "Focus", rating: focus)
                }
            }
        }
        .padding(.horizontal, 16)
    }

    private func ratingRow(label: String, rating: Int) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            HStack(spacing: 4) {
                ForEach(1...5, id: \.self) { i in
                    Image(systemName: i <= rating ? "circle.fill" : "circle")
                        .font(.caption)
                        .foregroundStyle(i <= rating ? Color.accentColor : Color(.systemGray4))
                }
            }
            Text("\(rating)/5")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
        }
    }

    // MARK: - Bullet Card

    private func bulletCard(
        title: String,
        systemImage: String,
        tint: Color,
        items: [String]
    ) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Label(title, systemImage: systemImage)
                    .font(.subheadline.bold())
                    .foregroundStyle(tint)
                    .padding(.bottom, 2)

                ForEach(items, id: \.self) { item in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•")
                            .foregroundStyle(tint)
                        Text(item)
                            .font(.subheadline)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Paragraph Card

    private func paragraphCard(
        title: String,
        systemImage: String,
        tint: Color,
        body: String
    ) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Label(title, systemImage: systemImage)
                    .font(.subheadline.bold())
                    .foregroundStyle(tint)
                    .padding(.bottom, 2)

                Text(body)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16)
    }
}

#Preview {
    let eval = MatchEvaluation(
        id: UUID(uuidString: "00000001-0000-0000-0000-000000000001")!,
        matchId: UUID(uuidString: "AAAA0000-0000-0000-0000-000000000001")!,
        result: .won,
        scoreText: "6-4, 7-5",
        effortRating: 4,
        focusRating: 5,
        wentWell: ["First serve percentage was high", "Stayed patient in long rallies"],
        toImprove: ["Net approach timing on second ball"],
        opponentObservations: "Strong crosscourt forehand. Backhand breaks down when pushed wide to the ad side with heavy topspin.",
        keyMoments: "Saved two break points at 4-4 in the second set with back-to-back first serves.",
        createdAt: Date(timeIntervalSinceNow: -3600),
        updatedAt: Date(timeIntervalSinceNow: -3600)
    )
    ScrollView {
        PostMatchEvaluationView(evaluation: eval, onEdit: {})
            .padding(.vertical)
    }
}
