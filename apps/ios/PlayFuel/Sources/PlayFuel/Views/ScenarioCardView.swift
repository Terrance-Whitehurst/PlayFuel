import SwiftUI

/// US-06 — A single match-duration scenario card.
///
/// Renders one ScenarioPlan (short / normal / long).
/// Shows: scenario label, duration, estimated end, gap pill (color by status),
/// food strategy, pickup strategy, re-warm-up time, and inline amber overrun band.
/// Phase 3: fed from Plan.scenarioPlans decoded from API.
///
/// SCENARIO_CARD_BUTTON_AFFORDANCE (session morbp13jbtvy):
/// A colored PlayFuel-green pill button ("See suggestions") sits at the top-right
/// corner of each card header as the explicit tap affordance. Only the pill button
/// opens ScenarioDetailSheetView — the card body is non-interactive (display only).
/// Sheet reopens cleanly on every tap (no state leak — @State resets on dismiss).
///
/// Layout: ZStack — non-interactive card content as bottom layer with
/// `.accessibilityElement(children: .combine)`; pill button as top layer at
/// `.topTrailing` alignment so VoiceOver reaches it as a separate element.
struct ScenarioCardView: View {

    let plan: ScenarioPlan

    /// Plan-level food options passed down from TournamentDashboardView.
    /// Top-level on Plan (OQ-POP-1); forwarded to ScenarioDetailSheetView for
    /// client-side per-scenario filtering.
    let foodOptions: [FoodOption]

    /// Computed from plan.weather.extremeHeatRisk (WeatherSnapshot computed var).
    /// Forwarded to ScenarioDetailSheetView for the cool-down heat overlay step.
    let extremeHeatRisk: Bool

    @State private var showingDetail = false

    var body: some View {
        ZStack(alignment: .topTrailing) {

            // ── Non-interactive card content ──────────────────────────────────
            // Combined into one VoiceOver element (no button trait) so a parent
            // can glance-read the scenario, gap status, and food info in one swipe.
            VStack(alignment: .leading, spacing: 0) {

                // Header bar — scenario label + duration only.
                // Est. End moved to content area (estimatedEndRow) so the
                // pill button corner is unobstructed.
                headerBar

                VStack(alignment: .leading, spacing: 14) {

                    // Estimated end time (moved from header — see note above)
                    estimatedEndRow

                    // Overrun warning band (amber) — renders if overrunWarning != nil
                    if let warning = plan.overrunWarning {
                        overrunBand(warning: warning)
                    }

                    // Gap pill row
                    gapRow

                    // Food strategy
                    if let food = plan.foodStrategy {
                        strategyRow(
                            icon: "fork.knife",
                            label: "Food Strategy",
                            text: food.text,
                            color: .green
                        )
                    }

                    // Parent pickup strategy
                    strategyRow(
                        icon: "car.fill",
                        label: "Parent Pickup",
                        text: plan.pickupStrategy.text,
                        color: .blue
                    )

                    // Re-warm-up
                    if let rewarm = plan.rewarmUp {
                        strategyRow(
                            icon: "figure.walk",
                            label: "Re-Warm-Up",
                            text: rewarmText(rewarm),
                            color: .orange
                        )
                    } else if plan.gapStatus == .overrun {
                        strategyRow(
                            icon: "figure.walk",
                            label: "Re-Warm-Up",
                            text: "Not available \u{2014} match overrun leaves no warm-up window.",
                            color: .secondary
                        )
                    }
                }
                .padding(16)
            }
            // Glassmorphic card background — ultraThinMaterial + top-lit white stroke
            .background {
                ZStack {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(.ultraThinMaterial)
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(
                            LinearGradient(
                                colors: [.white.opacity(0.40), .white.opacity(0.06)],
                                startPoint: .top,
                                endPoint: .bottom
                            ),
                            lineWidth: 1
                        )
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16))
            // Min width for horizontal scroll (existing constant)
            .frame(width: 300)
            // Card content as one combined VoiceOver element; no button trait.
            // VoiceOver reads cardAccessibilityLabel, then focuses the pill button
            // as a separate "See suggestions, button" element.
            .accessibilityElement(children: .combine)
            .accessibilityLabel(cardAccessibilityLabel)

            // ── Colored pill button — top-right corner ────────────────────────
            // Explicit interactive affordance per user feedback (session morbp13jbtvy).
            // PlayFuel green (Color.accentColor = #227F52 light / #3DB87D dark).
            // White text WCAG AA contrast: ~4.88:1 against #227F52. ✅
            // NOT red (EmergencyStrip reserved) / orange (overrun reserved) /
            // yellow (tight reserved).
            suggestionsButton
        }
        // Sheet opens on every button tap; @State resets cleanly on dismiss.
        .sheet(isPresented: $showingDetail) {
            ScenarioDetailSheetView(
                scenario: plan,
                foodOptions: foodOptions,
                extremeHeatRisk: extremeHeatRisk
            )
        }
    }

    // MARK: - Suggestions Button

    /// Colored pill button that opens the detail sheet.
    /// Positioned at card top-right via ZStack `.topTrailing` + padding insets.
    /// Min 44×44 pt tap target (Apple HIG) via `.frame(minWidth:minHeight:)` +
    /// `.contentShape(Rectangle())` to extend the hit region beyond the visual pill.
    /// Glass pill button — accentColor base + glass sheen + top-lit stroke.
    /// Solid accentColor base preserves WCAG AA white-text contrast (~4.88:1 ✅).
    private var suggestionsButton: some View {
        Button(action: { showingDetail = true }) {
            // ViewThatFits: "See suggestions" first (fits at 300pt card width).
            // Falls back to "Details" only on extreme constraint.
            ViewThatFits(in: .horizontal) {
                Text("See suggestions")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background {
                        ZStack {
                            Capsule()
                                .fill(Color.accentColor)
                            Capsule()
                                .fill(.white.opacity(0.10))
                            Capsule()
                                .strokeBorder(
                                    LinearGradient(
                                        colors: [.white.opacity(0.50), .white.opacity(0.08)],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    ),
                                    lineWidth: 1
                                )
                        }
                    }
                    .shadow(color: Color.accentColor.opacity(0.35), radius: 8, x: 0, y: 4)
                Text("Details")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background {
                        ZStack {
                            Capsule()
                                .fill(Color.accentColor)
                            Capsule()
                                .fill(.white.opacity(0.10))
                            Capsule()
                                .strokeBorder(
                                    LinearGradient(
                                        colors: [.white.opacity(0.50), .white.opacity(0.08)],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    ),
                                    lineWidth: 1
                                )
                        }
                    }
                    .shadow(color: Color.accentColor.opacity(0.35), radius: 8, x: 0, y: 4)
            }
        }
        .buttonStyle(.plain)
        // HIG minimum 44×44 pt tap target
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(Rectangle())
        // Inset from card top-right corner: 8pt top, 10pt trailing
        .padding(.top, 8)
        .padding(.trailing, 10)
    }

    // MARK: - Header

    /// Scenario identity bar: label + duration.
    /// Est. End time has moved to `estimatedEndRow` in the card content area
    /// so the top-right corner is free for `suggestionsButton`.
    private var headerBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(plan.scenarioLabel)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                Text("\(DurationFormatting.friendly(minutes: plan.durationMin)) match")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.85))
            }
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(headerColor)
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 16, topTrailingRadius: 16))
    }

    private var headerColor: Color {
        switch plan.scenario {
        case "short":  return .green
        case "normal": return .blue
        case "long":   return .purple
        default:       return .gray
        }
    }

    // MARK: - Estimated End Row

    /// Displays match estimated end time. Previously in the header bar;
    /// moved here so the header corner is uncluttered for the pill button.
    private var estimatedEndRow: some View {
        HStack {
            Label {
                Text("Est. End")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            } icon: {
                Image(systemName: "clock")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            // fix/scenario-card-end-time: backend returns ISO 8601 UTC.
            // asClockTimeFromISO converts to device-local time.
            // FakeData strings (e.g. "10:15 AM") pass through unchanged.
            Text(plan.estimatedEnd.asClockTimeFromISO)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
        }
    }

    // MARK: - Gap Row

    private var gapRow: some View {
        HStack(spacing: 10) {
            Label {
                Text("Gap to Next Match")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
            } icon: {
                Image(systemName: "arrow.left.and.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            gapPill
        }
    }

    private var gapPill: some View {
        Group {
            if let gap = plan.gapMinutes {
                Text(gapLabel(gap))
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(gapPillColor.opacity(0.15))
                    .foregroundStyle(gapPillColor)
                    .clipShape(Capsule())
            } else {
                Text("No next match")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func gapLabel(_ gap: Int) -> String {
        switch plan.gapStatus {
        case .overrun:       return "\u{26a0} \(DurationFormatting.friendly(minutes: abs(gap))) overrun"
        case .tight:         return "\u{26a1} \(DurationFormatting.friendly(minutes: gap)) tight"
        case .ok:            return "\u{2713} \(DurationFormatting.friendly(minutes: gap))"
        case .no_next_match: return "No next match"
        }
    }

    /// Gap pill color — mirrors §C.1 table and §H decisions table.
    /// .yellow tight / .orange overrun (NOT red — brief's "red" overridden by existing palette).
    private var gapPillColor: Color {
        switch plan.gapStatus {
        case .ok:            return .green
        case .tight:         return .yellow
        case .overrun:       return .orange
        case .no_next_match: return .gray
        }
    }

    // MARK: - Overrun Band

    private func overrunBand(warning: OverrunWarning) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            // HardCodedStrings.overrunMessage carries the canonical text;
            // also show warning.message from the plan (same content, from server).
            Text(warning.message)
                .font(.caption.weight(.medium))
                .foregroundStyle(.orange)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Strategy Row

    private func strategyRow(icon: String, label: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(label, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(color)
            Text(text)
                .font(.caption)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Helpers

    private func rewarmText(_ rewarm: RewarmUp) -> String {
        let absOffset = abs(rewarm.startOffsetMin)
        return "Start \(DurationFormatting.friendly(minutes: absOffset)) before Match 2, \(DurationFormatting.friendly(minutes: rewarm.durationMin)) dynamic warm-up."
    }

    /// VoiceOver accessibility label for the combined card content element.
    /// Reads scenario, gap, and status. Button ("See suggestions") is a separate
    /// VoiceOver focus element that follows naturally in the focus order.
    private var cardAccessibilityLabel: String {
        let gapText: String
        if plan.gapStatus == .no_next_match {
            gapText = "Last match today"
        } else if let gap = plan.gapMinutes {
            gapText = "Gap \(DurationFormatting.friendly(minutes: abs(gap)))"
        } else {
            gapText = "Gap unknown"
        }

        let statusText: String
        switch plan.gapStatus {
        case .ok:            statusText = "on track"
        case .tight:         statusText = "tight"
        case .overrun:       statusText = "schedule overrun"
        case .no_next_match: statusText = "last match"
        }

        return "\(plan.scenarioLabel) match, \(gapText), \(statusText)"
    }
}

// MARK: - Previews

#Preview {
    // Dallas: 88°F + 72% humidity → extremeHeatRisk=true
    // Verify: green short card → accentColor pill on green header (darker green, shadow separates).
    // Blue normal card → accentColor pill on blue (distinct hue, clearly visible).
    // Purple long card → accentColor pill on purple (distinct hue, clearly visible).
    ScrollView(.horizontal) {
        HStack(spacing: 16) {
            ScenarioCardView(plan: FakeData.dallasShortScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
            ScenarioCardView(plan: FakeData.dallasNormalScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
            ScenarioCardView(plan: FakeData.dallasLongScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
        }
        .padding()
    }
}

#Preview("Dark") {
    ScrollView(.horizontal) {
        HStack(spacing: 16) {
            ScenarioCardView(plan: FakeData.dallasShortScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
            ScenarioCardView(plan: FakeData.dallasNormalScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
            ScenarioCardView(plan: FakeData.dallasLongScenario,
                             foodOptions: FakeData.dallasFoodOptions,
                             extremeHeatRisk: true)
        }
        .padding()
    }
    .preferredColorScheme(.dark)
}
