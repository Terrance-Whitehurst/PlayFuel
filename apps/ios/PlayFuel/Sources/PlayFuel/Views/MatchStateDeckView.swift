import SwiftUI

// MARK: - MatchStateCard Model

/// A single card in the pre-match / between-matches / end-of-day deck.
/// Decoded from `MatchStateCards.json` bundled in the iOS app.
/// match-done-state-cards spec \u00a7D.
struct MatchStateCard: Codable, Identifiable {
    let id: String
    let deck: String
    let title: String
    let iconSfSymbol: String
    let short: String
    let long: String
    let heatAware: Bool
    let heatSuffix: String?
    let minGapMinutes: Int?

    static let fallback = MatchStateCard(
        id: "fallback",
        deck: "fallback",
        title: "Take a beat",
        iconSfSymbol: "pause.circle",
        short: "Sip water, breathe.",
        long: "Sip water, breathe.",
        heatAware: false,
        heatSuffix: nil,
        minGapMinutes: nil
    )
}

// MARK: - Card Registry (module-level cache, loaded once at import)

private enum CardRegistry {
    static let cards: [MatchStateCard] = {
        guard let url = Bundle.main.url(forResource: "MatchStateCards", withExtension: "json"),
              let data = try? Data(contentsOf: url) else {
            // Safe fallback: return empty; MatchStateDeckView will show the fallback card.
            return []
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let result = try? decoder.decode(CardBundle.self, from: data) else {
            return []
        }
        return result.cards
    }()
}

private struct CardBundle: Decodable {
    let version: String
    let cards: [MatchStateCard]
}

// MARK: - MatchStateDeckView

/// State-aware swipeable card deck shown on the tournament dashboard.
///
/// Three decks switch based on match done state:
///   - `pre_match`         — when `activePlan.isDone == false` (default / before Done)
///   - `between_matches`   — when done AND at least one other plan is undone
///   - `end_of_day`        — when all plans are done
///
/// Cards with `min_gap_minutes` are hidden when the normal scenario's gapMinutes is
/// below the threshold. If filtering leaves zero cards, a fallback card is shown so
/// the deck is never empty.
///
/// match-done-state-cards spec \u00a7E.3
struct MatchStateDeckView: View {

    let activePlan: Plan
    let allPlans: [Plan]

    @State private var selectedCard: MatchStateCard?

    // MARK: - Deck state machine (spec \u00a7E.2)

    private var currentDeck: String {
        if !activePlan.isDone { return "pre_match" }
        let hasUndone = allPlans.contains { !$0.isDone }
        return hasUndone ? "between_matches" : "end_of_day"
    }

    private var deckTitle: String {
        switch currentDeck {
        case "pre_match":       return "Before the match"
        case "between_matches": return "Between matches"
        case "end_of_day":      return "End of day"
        default:                return "Reminders"
        }
    }

    private var deckIcon: String {
        switch currentDeck {
        case "pre_match":       return "figure.walk"
        case "between_matches": return "arrow.counterclockwise.circle"
        case "end_of_day":      return "moon.zzz.fill"
        default:                return "list.bullet"
        }
    }

    /// Gap minutes from the normal scenario for the gap filter (spec V-12).
    private var normalGapMinutes: Int? {
        activePlan.scenarioPlans.first(where: { $0.scenario == "normal" })?.gapMinutes
    }

    /// Cards to display after deck selection and gap filtering (spec \u00a7E.3).
    private var visibleCards: [MatchStateCard] {
        let deckCards = CardRegistry.cards.filter { $0.deck == currentDeck }
        let filtered = deckCards.filter { card in
            guard let minGap = card.minGapMinutes,
                  let gap = normalGapMinutes else { return true }
            return gap >= minGap
        }
        return filtered.isEmpty ? [MatchStateCard.fallback] : filtered
    }

    // MARK: - Body

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(deckTitle, systemImage: deckIcon)
                .font(.headline)
                .padding(.horizontal, 16)

            TabView {
                ForEach(visibleCards) { card in
                    MatchStateCardThumbnail(card: card, plan: activePlan)
                        .onTapGesture { selectedCard = card }
                        .padding(.horizontal, 4)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .frame(height: 130)
            .padding(.horizontal, 12)
        }
        .sheet(item: $selectedCard) { card in
            MatchStateCardSheet(card: card, plan: activePlan)
        }
    }
}

// MARK: - MatchStateCardThumbnail (spec \u00a7E.4)

/// Compact card shown in the swipeable carousel.
/// `chevron.right` in the top-right signals tap-ability, consistent with WeatherCardView.
/// `.contentShape` ensures the full rounded-rect area registers taps.
struct MatchStateCardThumbnail: View {

    let card: MatchStateCard
    let plan: Plan

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: card.iconSfSymbol)
                    .foregroundStyle(Color.accentColor)
                Text(card.title)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(card.short)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
        .contentShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - MatchStateCardSheet (spec \u00a7E.5)

/// Expanded card sheet shown when a thumbnail is tapped.
/// Always includes the verbatim safety disclaimer footer.
/// Appends heat suffix when the plan has hot or very_hot weather flags.
struct MatchStateCardSheet: View {

    let card: MatchStateCard
    let plan: Plan
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Icon + long copy (with optional heat suffix)
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: card.iconSfSymbol)
                            .font(.title2)
                            .foregroundStyle(Color.accentColor)
                        Text(longCopy)
                            .font(.body)
                    }

                    Divider()

                    // Verbatim disclaimer \u2014 MUST NOT be removed or paraphrased (spec \u00a7B).
                    // Character-perfect copy required per AC#5.
                    Text("General tournament-day reminders. Not medical, nutrition, or training advice. Talk to your coach, physician, or athletic trainer for anything specific to your child.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .navigationTitle(card.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    // MARK: - Heat suffix logic (spec \u00a7E.5, V-11)
    //
    // WeatherSnapshot uses flags: [WeatherFlag] \u2014 NO flagHot/flagVeryHot Bool properties.
    // Check via flags.contains(.hot) / flags.contains(.very_hot).

    private var longCopy: String {
        guard card.heatAware,
              (plan.weather.flags.contains(.hot) || plan.weather.flags.contains(.very_hot)),
              let suffix = card.heatSuffix else { return card.long }
        return card.long + suffix
    }
}

// MARK: - DoneToggleButton (spec \u00a7E.6)
//
// Declared as `struct` (internal) here in MatchStateDeckView.swift so it is
// accessible from ScheduleStripView.swift (same module). Not `private` because
// MatchChip in ScheduleStripView uses it via cross-file access.

struct DoneToggleButton: View {

    let isDone: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            Image(systemName: isDone ? "checkmark.circle.fill" : "checkmark.circle")
                .foregroundStyle(isDone ? Color.green : Color.secondary)
                .font(.body)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isDone ? "Mark undone" : "Mark done")
    }
}

// MARK: - Previews

#Preview("Pre-match deck — default") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return MatchStateDeckView(
        activePlan: FakeData.dallasPlan,
        allPlans: FakeData.dallasPlanEnvelope.allPlans
    )
    .padding(.vertical, 16)
    .background(Color(.systemGroupedBackground))
    .environmentObject(state)
}

#Preview("Between-matches deck") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    // Build a done plan for the preview
    let donePlan = Plan(
        id: FakeData.dallasPlan.id,
        planId: FakeData.dallasPlan.planId,
        tournamentId: FakeData.dallasPlan.tournamentId,
        generatedAt: FakeData.dallasPlan.generatedAt,
        warnings: FakeData.dallasPlan.warnings,
        scenarioPlans: FakeData.dallasPlan.scenarioPlans,
        weather: FakeData.dallasPlan.weather,
        foodOptions: FakeData.dallasPlan.foodOptions,
        timeline: FakeData.dallasPlan.timeline,
        bagFallbackOnly: FakeData.dallasPlan.bagFallbackOnly,
        llmSummary: FakeData.dallasPlan.llmSummary,
        matchType: FakeData.dallasPlan.matchType,
        matchId: FakeData.dallasPlan.matchId,
        nextAction: FakeData.dallasPlan.nextAction,
        scheduledStart: FakeData.dallasPlan.scheduledStart,
        isDone: true,
        placesUnavailable: false  // OQ-FOOD-EMPTY-1: preview uses populated path
    )
    return MatchStateDeckView(
        activePlan: donePlan,
        allPlans: [donePlan, FakeData.dallasSinglesPlan2]   // plan2 undone
    )
    .padding(.vertical, 16)
    .background(Color(.systemGroupedBackground))
    .environmentObject(state)
}

#Preview("Dark") {
    let auth  = AuthService()
    let api   = APIClient(authService: auth)
    let repo  = Repository(api: api)
    let state = AppState(repository: repo, authService: auth)
    return MatchStateDeckView(
        activePlan: FakeData.dallasPlan,
        allPlans: FakeData.dallasPlanEnvelope.allPlans
    )
    .padding(.vertical, 16)
    .background(Color(.systemGroupedBackground))
    .environmentObject(state)
    .preferredColorScheme(.dark)
}
