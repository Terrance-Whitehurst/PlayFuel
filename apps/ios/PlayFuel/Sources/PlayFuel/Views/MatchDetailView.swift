import SwiftUI

/// Per-match detail view presenting header metadata + post-match write-up.
///
/// Access path: TournamentDashboardView → "View match details" button → .sheet
///
/// Three post-match write-up states:
///   1. Loading (fetching from API)
///   2. Empty — CTA "Add Post-Match Write-Up"
///   3. Populated — PostMatchEvaluationView (read-only) with Edit button
///
/// OQ-EVAL-UX-2: `Plan` does not carry `roundLabel`/`opponentLabel` today.
/// MatchDetailView falls back gracefully to "Match #N" — no crash on missing data.
///
/// POST_MATCH_EVAL_V1.md §E.2
struct MatchDetailView: View {

    let plan: Plan
    let matchIndex: Int          // 1-based ordinal from the schedule strip (for fallback label)

    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    // MARK: - State

    @State private var evaluation: MatchEvaluation? = nil
    @State private var isLoadingEval: Bool = false
    @State private var loadError: String? = nil
    @State private var showEvalForm: Bool = false
    @State private var editingEval: MatchEvaluation? = nil    // pre-fill when editing

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // MARK: Header
                    headerSection
                        .padding(.horizontal, 16)

                    Divider()

                    // MARK: Post-Match Write-Up
                    postMatchSection

                    Spacer(minLength: 24)
                }
                .padding(.top, 16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Match Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                await loadEvaluation()
            }
            .sheet(isPresented: $showEvalForm, onDismiss: {
                Task { await loadEvaluation() }
            }) {
                PostMatchEvaluationForm(
                    matchId: plan.matchId,
                    existingEval: editingEval
                ) { saved in
                    evaluation = saved
                }
                .environmentObject(appState)
            }
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Title: "Match #N" (OQ-EVAL-UX-2 graceful fallback — Plan doesn't carry roundLabel)
            Text("Match #\(matchIndex)")
                .font(.title2.bold())

            // Scheduled time
            if let startISO = plan.scheduledStart {
                let display = startISO.asClockTimeFromISO
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(display)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            // Match type pill
            HStack(spacing: 6) {
                Image(systemName: plan.matchType == .doubles ? "person.2.fill" : "person.fill")
                    .font(.caption)
                Text(plan.matchType.displayName)
                    .font(.caption)
            }
            .foregroundStyle(Color.accentColor)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.accentColor.opacity(0.12), in: Capsule())

            // Plan mini-card
            planMiniCard
        }
    }

    // MARK: - Plan Mini-Card

    private var planMiniCard: some View {
        GroupBox {
            HStack {
                Image(systemName: "doc.text.fill")
                    .foregroundStyle(Color.accentColor)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Match Plan Ready")
                        .font(.subheadline.bold())
                    Text("Return to the dashboard for full scenario cards and food options.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
        }
        .padding(.top, 4)
    }

    // MARK: - Post-Match Section

    @ViewBuilder
    private var postMatchSection: some View {
        if isLoadingEval {
            // Loading state
            HStack {
                ProgressView()
                Text("Loading write-up...")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 16)

        } else if let err = loadError {
            // Error state
            VStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Retry") {
                    Task { await loadEvaluation() }
                }
                .buttonStyle(.bordered)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 16)

        } else if let eval = evaluation {
            // Populated: read-only card with Edit
            PostMatchEvaluationView(evaluation: eval) {
                editingEval = eval
                showEvalForm = true
            }

        } else {
            // Empty: CTA to add write-up
            emptyEvalCTA
        }
    }

    // MARK: - Empty CTA

    private var emptyEvalCTA: some View {
        GroupBox {
            VStack(spacing: 12) {
                Image(systemName: "pencil.and.list.clipboard")
                    .font(.system(size: 36))
                    .foregroundStyle(Color.accentColor)

                Text("No write-up yet")
                    .font(.headline)

                Text("Add a post-match write-up to capture what happened, what worked, and what to focus on next time.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                Button("Add Post-Match Write-Up") {
                    editingEval = nil
                    showEvalForm = true
                }
                .buttonStyle(.borderedProminent)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
        }
        .padding(.horizontal, 16)
    }

    // MARK: - Load Evaluation

    private func loadEvaluation() async {
        isLoadingEval = true
        loadError = nil
        do {
            evaluation = try await appState.repository.getMatchEvaluation(matchId: plan.matchId)
        } catch {
            loadError = "Couldn't load write-up. \(error.localizedDescription)"
        }
        isLoadingEval = false
    }
}

#Preview {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    MatchDetailView(plan: FakeData.dallasDoublesPlan, matchIndex: 1)
        .environmentObject(state)
}
