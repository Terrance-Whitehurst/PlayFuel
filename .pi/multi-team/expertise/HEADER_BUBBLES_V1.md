# HEADER_BUBBLES_V1.md — Dashboard Bubble Header Pattern
> Authority: Product Manager · Planning Lead · Date: 2026-04-27
> Status: LOCKED — Engineering executes §H verbatim

---

## §J — PM Verification Findings (PRE-SPEC — read before any §)

> Same verification discipline that caught `plans.match_id` (NUTRITION_FIRST_IA) and `matches.format`
> (DOUBLES_SPEC). All findings below reflect what is actually on disk, not what was assumed.

| Finding | Impact on Spec |
|---------|----------------|
| **QA-IA-1 STILL PRESENT.** In `TournamentDashboardView.swift`, `envelopeContent()` renders the Picker first (when hasBothTypes), then calls `planContent()` where EmergencyBanner sits. When hasBothTypes=true, visual order is Picker → EmergencyBanner — the banner is at visual position #1, not #0. | §F.7 specifies the exact fix: resolve the active plan in `envelopeContent()`, hoist EmergencyStrip ABOVE the Picker. The bubble pivot is our opportunity to fix QA-IA-1 in the same Engineering pass. |
| **No `EmergencyStrip` exists.** `EmergencyBanner.swift` is a full-height VStack rendering `heatEmergencyText` verbatim. No 1-line strip variant exists anywhere. | §F.6 is a genuine NEW file, not a modification. |
| **`WeatherCardView` `compact: Bool = false` confirmed.** The compact pill renders `"❤️ 88°F · flags · chevron"` via `@State var expanded: Bool = false`. | §F.8 — no API change; compact mode stays in code but is unwired from dashboard. |
| **`PlanSummaryCard(explanation: PlanExplanation)` confirmed.** Fields: `summary`, `weatherNote?`, `foodNote?`, `safetyNote`, `provider`. There is NO "scenario explanations" field — it does not exist on `PlanExplanation`. | §B Plan Summary Sheet scoped to actual model fields: summary + weatherNote + foodNote + safetyNote. Orchestrator brief referenced "scenario explanations" — confirmed those are a separate component (ScenarioCardView) and are NOT in PlanExplanation. |
| **HardCodedStrings exact symbols confirmed.** `HardCodedStrings.heatEmergencyText` and `HardCodedStrings.userDisclaimer` — both camelCase, matching the Swift enum on disk. | §B Heat Guidance Sheet references exact symbols. |

---

## §A — Principles (Bubble Pattern)

1. **Bubbles serve background information.** PlanSummary and Weather are context the parent may want; they are not the first thing a parent must act on. Background info belongs one tap deep.
2. **Safety never hides behind a tap.** The EmergencyStrip (option b hybrid) is rendered inline — not in the bubble row. Parents must encounter the heat warning without any required action. The bubble row contains ZERO heat-related content.
3. **The dashboard glance-test is preserved.** After this pivot, the above-strip area contains only: the safety strip (conditional), the type picker (conditional), and 2 small icon buttons. The parent's eye lands directly on ScheduleStrip and NextActionCard.
4. **Calm, not cluttered.** Two circles. That's it. No labels, no text blocks, no cards above the schedule strip.
5. **WeatherCard code is preserved** — `compact: Bool` stays in `WeatherCardView.swift` for future use; it is simply unwired from the dashboard.

---

## §B — Per-Bubble Sheet Content

### Plan Summary Sheet
- **Title:** "Today's Plan"
- **Body (top to bottom):**
  1. `explanation.summary` — body font, primary color (the 2–4 sentence coach voice)
  2. `explanation.weatherNote` (if non-nil) — subheadline, secondary color, section header "Conditions"
  3. `explanation.foodNote` (if non-nil) — subheadline, secondary color, section header "Food"
  4. Divider
  5. `explanation.safetyNote` — caption, secondary color (§A disclaimer verbatim — always present)
  6. Provider badge ("Template" / "Claude" / "GPT") — visible ONLY `#if DEBUG`
- **Sheet:** `NavigationStack { ScrollView }` · `.presentationDetents([.medium, .large])` · `.presentationDragIndicator(.visible)`
- **Dismiss:** drag-to-dismiss (no X button, no "Got it" button — iOS standard)

### Weather Sheet
- **Title:** "Conditions"
- **Body:** `WeatherCardView(weather: weather, compact: false)` — the full card, unchanged
- **Sheet:** same wrapper as Plan Summary Sheet

### Heat Guidance Sheet (opened from EmergencyStrip tap — NOT from a bubble)
- **Title:** "Heat Emergency Guidance"
- **Body:**
  1. `HardCodedStrings.heatEmergencyText` — body font, primary color, verbatim, no paraphrasing
  2. Divider
  3. `HardCodedStrings.userDisclaimer` — caption, secondary color, verbatim
- **Dismiss:** drag-to-dismiss only (no "Got it" button — drag handle is iOS standard; OQ-HB-3)
- **⚠️ OQ-11 note:** embed existing disclaimer comment in source: `// Pending attorney review — do not treat as legally cleared`

---

## §C — Safety Decision

**Choice: Option (b) — hybrid.** Bubbling the heat emergency text would make safety information opt-in, directly contradicting `SAFETY_DISCLAIMERS.md §B` and `NUTRITION_FIRST_IA_V1.md §A.3`, both of which treat the heat warning as a forced encounter. The existing full EmergencyBanner is too large for the user's "don't overload" ask — it consumes significant screen real estate on every extreme-heat day. The 1-line EmergencyStrip honors both constraints: invisible on normal days (zero screen tax), unmissable when active (full-width red bar), and one tap to the verbatim §B + §A text. **No OQ-11 legal review impact** — the §B text is preserved completely in the strip's tap-target sheet; the strip itself also contains a condensed version of the warning ("⚠️ Extreme heat — tap for guidance"), making the sheet strictly one level deeper than the current full-text banner, not more obscure.

---

## §D — Updated Dashboard Card Order

> Baseline: `NUTRITION_FIRST_IA_V1.md §B`. This replaces that spec's positions 2 and 8.

| Position | Card | Conditional | Change from IA V1 |
|----------|------|-------------|------------------|
| 0 | `EmergencyStrip` (1-line red, "⚠️ Extreme heat — tap for guidance") | `extreme_heat_risk == true` only | **REPLACES** full `EmergencyBanner`. Banner kept in codebase but no longer used by dashboard. |
| 1 | Singles/Doubles segmented Picker | `envelope.hasBoth` only | Unchanged. |
| 2 | **NEW** `HeaderBubbleRow` — [Plan Summary] [Weather] | Always when plan loaded | **NEW.** PlanSummaryCard and WeatherCardView removed from inline scroll. |
| 3 | `ScheduleStripView` | Always | Unchanged. |
| 4 | `NextActionCard` | Always | Unchanged. |
| 5 | `FoodCardView` | When `!plan.foodOptions.isEmpty` | Unchanged. |
| 6 | Scenario cards (horizontal scroll) | Always | Unchanged. |
| 7 | Full Day Timeline button | When `!plan.timeline.isEmpty` | Unchanged. |
| 8 | Disclaimer footer | Always | Unchanged. |

**Removed from inline scroll:** `PlanSummaryCard` (was #2) and `WeatherCardView compact` (was #8). Both accessible via bubbles.

---

## §E — User Stories

_(Full Given/When/Then entries appended to `USER_STORIES.md`)_

**US-DASH-5** — As a parent, I want to open the dashboard and see only actionable schedule information, so that I'm not buried in explanatory text before I can act.

**US-DASH-6** — As a parent, I want extreme-heat warnings to be unavoidable without overwhelming me on normal days, so that I am always safe but never distracted by empty alerts.

---

## §F — Engineering Hand-Off

> Engineering executes this list verbatim. BD has no changes in this delegate. All work is iOS.

### New Files

**1. `Views/HeaderBubble.swift`** — Reusable bubble button component.
```
init(systemImage: String, label: String, badge: String? = nil, action: () -> Void)
```
- Shape: circle, 44×44pt (`.frame(width: 44, height: 44)`)
- Background: `Color(.systemGray5)` fill, circle clip
- Icon: `Image(systemName: systemImage)` · `.font(.system(size: 18, weight: .medium))` · accent foreground
- Badge: if `badge != nil`, overlay `Text(badge!)` in top-right corner — `.font(.caption2.weight(.bold))`, white text, red capsule background, `.offset(x: 12, y: -12)`
- VoiceOver: `.accessibilityLabel(label)` + `.accessibilityAddTraits(.isButton)`
- Tap: `Button(action: action)` wrapping the whole circle

**2. `Views/HeaderBubbleRow.swift`** — HStack of 2 `HeaderBubble` instances.
```
struct HeaderBubbleRow: View {
    let plan: Plan
    @State private var planSheetShown = false
    @State private var weatherSheetShown = false
}
```
- Layout: `HStack(spacing: 16) { planBubble; weatherBubble }` · `.padding(.horizontal, 16)`
- Plan bubble: `systemImage: "text.bubble.fill"`, `label: "Today's Plan"`, no badge
- Weather bubble: `systemImage: "cloud.sun.fill"`, `label: "Current Conditions"`, `badge: "\(Int(plan.weather.tempF))°"` (no °F suffix — matches iOS Weather convention)
- Both toggle their respective `@State` Bool → `.sheet(isPresented: $planSheetShown) { PlanSummarySheet(explanation: plan.llmSummary!) }` and `.sheet(isPresented: $weatherSheetShown) { WeatherSheet(weather: plan.weather) }`
- Guard: if `plan.llmSummary == nil`, plan bubble's tap does nothing and badge shows `"—"`

**3. `Views/Sheets/PlanSummarySheet.swift`** — Plan Summary sheet wrapper.
- `init(explanation: PlanExplanation)`
- `NavigationStack { ScrollView { VStack(alignment: .leading, spacing: 16) { ... } } .navigationTitle("Today's Plan") .navigationBarTitleDisplayMode(.inline) }`
- Body matches §B Plan Summary Sheet exactly (summary, weatherNote, foodNote, safetyNote, DEBUG badge)
- `.presentationDetents([.medium, .large])` · `.presentationDragIndicator(.visible)`

**4. `Views/Sheets/WeatherSheet.swift`** — Weather sheet wrapper.
- `init(weather: WeatherSnapshot)`
- Same `NavigationStack` + sheet modifiers · `.navigationTitle("Conditions")`
- Body: `WeatherCardView(weather: weather, compact: false)`

**5. `Views/Sheets/HeatGuidanceSheet.swift`** — Heat guidance sheet.
- No init params (content is fully static from `HardCodedStrings`)
- Same `NavigationStack` + sheet modifiers · `.navigationTitle("Heat Emergency Guidance")`
- Body: verbatim `HardCodedStrings.heatEmergencyText` (body font) → Divider → `HardCodedStrings.userDisclaimer` (caption, secondary)
- Source comment: `// ⚠️ OQ-11: Pending attorney review — do not treat as legally cleared`
- Drag-to-dismiss only (no button)

**6. `Views/EmergencyStrip.swift`** — NEW 1-line heat strip.
- Standalone View; `EmergencyBanner.swift` is **not modified** (keep for previews/other surfaces)
- `@State private var sheetShown = false`
- Body: `Button { sheetShown = true } label: { HStack { Image(systemName: "exclamationmark.triangle.fill"); Text("⚠️ Extreme heat — tap for guidance") .font(.subheadline.weight(.semibold)) .foregroundStyle(.white); Spacer(); Image(systemName: "chevron.right") .font(.caption).foregroundStyle(.white.opacity(0.8)) } .padding(.horizontal, 16).padding(.vertical, 10) }` · `.background(Color.red)` · `.buttonStyle(.plain)` · `.sheet(isPresented: $sheetShown) { HeatGuidanceSheet() .presentationDetents([.medium, .large]) .presentationDragIndicator(.visible) }`
- Height: ~44pt via padding. No corner radius (full-width edge-to-edge strip, like iOS system banners).

### Edited Files

**7. `Views/TournamentDashboardView.swift`** — The core reorder + QA-IA-1 fix.

Remove from `planContent(plan:envelope:)`:
- The `if plan.weather.extremeHeatRisk { EmergencyBanner() }` block (position #0)
- The `if let llmSummary = plan.llmSummary { PlanSummaryCard(explanation: llmSummary) }` block (position #2)
- The `WeatherCardView(weather: plan.weather, compact: true)` block (position #8)

Rewrite `envelopeContent(envelope:)` to fix QA-IA-1 — resolve the active plan FIRST, then render in strict order:
```swift
@ViewBuilder
private func envelopeContent(envelope: PlanEnvelope) -> some View {
    let plan = resolveActivePlan(from: envelope)

    // #0 IMMOVABLE — EmergencyStrip renders above Picker (fixes QA-IA-1)
    if let plan, plan.weather.extremeHeatRisk {
        EmergencyStrip()
    }

    // #1 Picker — only when both match types present
    if envelope.hasBothTypes {
        Picker(...) // unchanged from current implementation
        .onChange(...) // unchanged
    }

    // #2 Bubble header row
    if let plan {
        HeaderBubbleRow(plan: plan)
    }

    // #3–8 Plan content (stripped of EmergencyBanner, PlanSummaryCard, WeatherCard)
    if let plan {
        planContent(plan: plan, envelope: envelope)
    } else {
        generateButton
    }
}
```

Update `planContent()` doc comment to remove positions #0, #2, #8 from the listed order. Remaining order: ScheduleStrip (#3) → NextActionCard (#4) → FoodCard (#5) → Scenarios (#6) → Timeline btn (#7) → Disclaimer (#8 renumbered).

**8. `Views/WeatherCardView.swift`** — No API change. Update top doc comment:
> `compact: Bool` mode remains in code for future use. As of Phase 8.1, the dashboard surfaces weather via `HeaderBubbleRow` → `WeatherSheet`, not via the compact pill. Pass `compact: false` (default) in all current call sites.

**9. `apps/ios/PlayFuel/README.md`** — Update Screen Tour table with the new §D order. Add "Header Bubbles (Phase 8.1)" section: two-sentence summary of the pattern, list of new files under `Views/Sheets/`, note that `EmergencyBanner.swift` is unchanged.

### Acceptance Criteria

- Dashboard scroll between EmergencyStrip/Picker and ScheduleStrip shows only `HeaderBubbleRow` — no inline PlanSummaryCard, no inline WeatherCardView.
- Both bubbles open correct sheets on tap; sheets dismiss via drag.
- **QA-IA-1 fixed:** `EmergencyStrip` renders at visual position #0 (above the Picker) when `extreme_heat_risk == true` and `hasBothTypes == true`.
- When `extreme_heat_risk == false`, no strip rendered; dashboard top is Picker (or bubbles directly when hasBoth==false).
- `EmergencyBanner.swift` is **untouched** — it still compiles and its `#Preview` works.
- `WeatherCardView` compact pill code is still present but unused by the dashboard.
- All existing tests still pass. No API or schema changes. iOS file-level compiles.

---

## §G — DRAFT-Flagged OQs

| ID | Issue |
|----|-------|
| OQ-HB-1 | Plan Summary "unread dot" badge on bubble — DRAFT, not in this delegate |
| OQ-HB-2 | Weather badge format ("88°" vs "88°F") — locked at "88°" (no suffix), cosmetic iteration |
| OQ-HB-3 | Heat guidance sheet dismiss — locked at drag-only; "Got it" button tracked for accessibility review |
| OQ-HB-4 | Whether Disclaimer footer should be bubbled in v2 — out of scope for v1 |
| OQ-HB-5 | `cloud.sun.fill` is a static symbol; consider mapping to condition-specific symbol (e.g. `sun.max.fill` when hot, `cloud.rain.fill` when rain_risk) in v2 |
