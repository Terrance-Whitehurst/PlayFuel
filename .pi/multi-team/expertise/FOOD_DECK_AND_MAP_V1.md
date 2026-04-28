# FOOD_DECK_AND_MAP_V1.md — Food Option Deck + Venue Map
> Authority: Product Manager · Planning Lead · Date: 2026-04-28
> Status: LOCKED — Engineering executes §G verbatim
> Ref: HEADER_BUBBLES_V1.md, NUTRITION_FIRST_IA_V1.md, RULES_CONSTANTS_V1.md

---

## §I — PM Verification Findings (PRE-SPEC — read before any §)

> Verified by reading every source-of-truth file on disk before scribing.
> Prior 4 specs each caught ≥1 real bug this way. This spec: 8 findings.

| # | Finding | Impact on Spec |
|---|---------|----------------|
| **I-1** | **`RawPlace` has NO `lat`/`lng` fields.** Confirmed: `RawPlace` dataclass in `places.py` has `name, types, distance_meters, drive_time_minutes, place_id, provider` only. No coordinates whatsoever. | §G.2: add `lat: float \| None = None` and `lng: float \| None = None` to `RawPlace`; backfill all 4 Dallas fixtures. |
| **I-2** | **`FoodOption` Pydantic model has NO `lat`/`lng` fields.** Confirmed: `models/api.py FoodOption` has `name, category, drive_time_minutes, recommended_order, is_draft, distance_meters, place_id, provider`. No coords. | §G.1: add `lat: Optional[float] = None` and `lng: Optional[float] = None` to `FoodOption`. |
| **I-3** | **`FoodOption.driveTimeMin` is `Int` (non-optional) in iOS** — but `drive_time_minutes: Optional[int]` in Python. `FoodOptionDTO.toModel()` already papers over this with `driveTimeMinutes ?? 0`, hiding the mismatch. Widen to `Int?` on both iOS model and DTO mapping. | §G.7 (iOS): widen `driveTimeMin: Int` → `driveTimeMin: Int?`. §G.8 (iOS DTOs): update `toModel()` to pass `driveTimeMinutes` (not `?? 0`). §G.9 (iOS): update FoodCardView nil-coalesce. Resolves **OQ-FOOD-DECK-1**. |
| **I-4** | **Starbucks is ABSENT from `FakeData.dallasFoodOptions`.** Mock provider returns Starbucks as fixture #4, but `FakeData.swift` only has Chipotle, Jimmy John's, and Central Market (3 entries, no Starbucks). User said "click into Starbucks and see oats" — Starbucks must appear. | §G.15 (iOS): add Starbucks to `FakeData.dallasFoodOptions` with `category: "breakfast_cafe"`, DRAFT badge. |
| **I-5** | **`fast_casual_bowl` template text DIVERGES between §F.3 doc and `food.py`.** §F.3 doc: "Chicken rice bowl with light beans, mild toppings, sauce on the side." `food.py _TEMPLATES["fast_casual_bowl"]`: "Order a rice bowl: brown or white rice base, black beans, grilled chicken or steak. Add fresh salsa and lettuce. Skip sour cream, cheese, and guac to keep fat and fiber low before competition. Eat 60–90 min before next match. Wash down with 16–20 oz water." The `food.py` version is more detailed and structurally richer. Use `food.py` as authoritative (it runs; §F.3 doc is stale). The new `FoodSuggestions` structured form should match the `food.py` text. | §A per-category templates: parse `food.py` text into 5-bucket structure. §F.3 doc discrepancy flagged as **OQ-FOOD-DECK-8** (stale doc). |
| **I-6** | **`HeaderBubbleRow` signature is `plan: Plan` only.** The Map bubble requires `tournament: Tournament` for the venue pin. `TournamentDashboardView.swift` passes only `plan` today. Signature widening required: add `tournament: Tournament`. | §G.13 (iOS): update `HeaderBubbleRow` signature to `(plan: Plan, tournament: Tournament)`. §G.14 (iOS): update `TournamentDashboardView` call site. |
| **I-7** | **`FoodOptionDTO.toModel()` hardcodes `driveTimeMin: driveTimeMinutes ?? 0`.** Once `FoodOption.driveTimeMin` becomes `Int?`, this mapping must change to pass through `driveTimeMinutes` directly (nil-safe). | §G.8: update `FoodOptionDTO.toModel()` to pass `driveTimeMin: driveTimeMinutes`. |
| **I-8** | **`PlanExplanation.scenario_explanations` DOES exist** on the model — it's a `dict[str, str]` field (confirmed in `models/api.py`). Planning Lead's HEADER_BUBBLES §J finding said it "does not exist" — incorrect. It does exist. However, it's correctly NOT rendered in `PlanSummarySheet` because `ScenarioCardView` is the right surface for scenario explanations. This spec does not surface it in `FoodOptionDetailSheet` either. | No structural change — but note: `PlanExplanation.scenario_explanations` exists if Engineering ever needs it. |

---

## §A — FoodSuggestions Schema

### A.1 Canonical Bucket Schema — LOCKED (5 buckets)

```python
# Python / Pydantic (models/api.py)
class FoodSuggestions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    
    main_options: list[str] = []   # headline meal orders (what to get)
    add_ons: list[str] = []        # supplemental carbs, sides, easy fuels
    drinks: list[str] = []         # recommended beverages
    avoid: list[str] = []          # what to skip (pre-match / dietary)
    notes: list[str] = []          # timing, logistics, brief tips
```

Swift mirror:
```swift
// Models/FoodSuggestions.swift (NEW)
struct FoodSuggestions: Codable, Hashable {
    let mainOptions: [String]   // CodingKey: mainOptions (camelCase from API)
    let addOns: [String]
    let drinks: [String]
    let avoid: [String]
    let notes: [String]
    
    // Default empty init — allows FoodSuggestions() as safe default
    init(mainOptions: [String] = [], addOns: [String] = [],
         drinks: [String] = [], avoid: [String] = [], notes: [String] = []) {
        self.mainOptions = mainOptions
        self.addOns = addOns
        self.drinks = drinks
        self.avoid = avoid
        self.notes = notes
    }
}
```

**Why 5 buckets, not 3 or 7:** The §I-5 authoritative template (food.py) requires:
main order text (what to get), drink specifics, explicit avoidance list, and a timing/logistics note.
`add_ons` captures supplemental carbs/sides that the user directly mentioned ("oats, carbs").
Three buckets (meals/drinks/avoid) cannot express the timing note or carb supplements cleanly.
Seven+ is over-engineering for 5 well-understood categories. Five is the minimum complete set.

**LLM input contract (IMMUTABLE):** `FoodRecommendationSummary` (the LLM/TemplateProvider input)
consumes ONLY the derived `recommendedOrder` flat string — NOT the structured `FoodSuggestions`.
Structured suggestions are iOS-rendering only. Do NOT pass `suggestions` to the LLM input builder.

### A.2 `derive_recommended_order` Algorithm

```python
# rules/duration_format.py already exists. Add to rules/food.py:
def derive_recommended_order(suggestions: FoodSuggestions) -> str:
    """Collapse structured FoodSuggestions → single-line recommendedOrder string.
    
    Algorithm: main_options[0] (if any). Then ". Drinks: " + drinks[0] if non-empty.
    Then ". Avoid: " + avoid[0] if non-empty. Then notes[0] if non-empty.
    
    Rationale: one-line fallback for LLM input and legacy iOS clients.
    Returns empty string (not crash) when all buckets are empty.
    """
    parts: list[str] = []
    if suggestions.main_options:
        parts.append(suggestions.main_options[0])
    if suggestions.drinks:
        parts.append("Drinks: " + suggestions.drinks[0])
    if suggestions.avoid:
        parts.append("Avoid: " + suggestions.avoid[0])
    if suggestions.notes:
        parts.append(suggestions.notes[0])
    return ". ".join(parts)
```

### A.3 Per-Category Structured Templates

**Source:** `food.py _TEMPLATES` (authoritative per §I-5 finding).

#### `fast_casual_bowl` — CONFIRMED (`is_draft=False`)
```python
FoodSuggestions(
    main_options=[
        "Rice bowl: brown or white rice base",
        "Add black beans, grilled chicken or steak",
        "Add fresh salsa and lettuce",
    ],
    add_ons=[],
    drinks=["16–20 oz water"],
    avoid=[
        "Sour cream",
        "Cheese",
        "Guacamole — keep fat and fiber low before competition",
    ],
    notes=["Eat 60–90 min before next match"],
)
```

#### `breakfast_cafe` — DRAFT (`is_draft=True`, OQ-B carries)
> **Priority for demo:** User said "click into Starbucks and see oats" — populate with parent-friendly content.
```python
FoodSuggestions(
    main_options=[
        "Oatmeal (plain or lightly sweetened)",
        "Whole-grain item with eggs if available",
    ],
    add_ons=["Banana or fruit cup — easy carb bridge"],
    drinks=[
        "Water (primary)",
        "Small black coffee or tea if tolerated",
    ],
    avoid=[
        "Pastries and muffins — high sugar spike",
        "Large milk-based drinks close to match time",
        "High-sugar syrups and flavored drinks",
    ],
    notes=["Eat ≥45 min before play. DRAFT — confirm with your athlete."],
)
```

#### `sandwich_shop` — DRAFT (`is_draft=True`, OQ-B carries)
```python
FoodSuggestions(
    main_options=[
        "Turkey or chicken on whole-grain bread",
        "Add lettuce, tomato, mustard",
    ],
    add_ons=["Baked chips or pretzels if gap allows"],
    drinks=["Water or diluted sports drink"],
    avoid=[
        "Heavy sauces and extra cheese",
        "Oil-based dressings",
    ],
    notes=["Eat within 30 min of ordering. DRAFT — confirm with your athlete."],
)
```

#### `grocery_prepared` — DRAFT (`is_draft=True`, OQ-B carries)
```python
FoodSuggestions(
    main_options=[
        "Rotisserie chicken with rice",
        "Prepared grain bowl — lean protein + complex carbs",
    ],
    add_ons=["Fresh fruit for post-match recovery"],
    drinks=["Water or electrolyte drink"],
    avoid=["Fried items", "Heavy cream-based dishes"],
    notes=["Eat 60–90 min before play. DRAFT — confirm with your athlete."],
)
```

#### `restaurant` — DRAFT fallback (`is_draft=True`)
```python
FoodSuggestions(
    main_options=[
        "Lean protein: chicken, fish, or turkey",
        "Complex carbs: rice, pasta, or bread",
        "Side of vegetables",
    ],
    add_ons=[],
    drinks=["Water — avoid sodas or sugary drinks"],
    avoid=[
        "Heavy sauces and fried foods",
        "Large portions — keep it light",
    ],
    notes=["Eat 90+ min before next match. DRAFT — confirm with your athlete."],
)
```

---

## §B — Stacked-Deck UX — Scroll-Snap Pattern (LOCKED)

### B.1 Pattern Choice: Scroll-Snap Horizontal Deck

Selected over tarot-style peek-deck for three reasons:
1. **Simpler animation** — no z-axis stacking or ScaleEffect animation math;
   `ScrollView(.horizontal)` + `.scrollTargetBehavior(.viewAligned)` is iOS 17+ native.
2. **Peek affordance** — ~30pt of the next card visible on the right edge communicates
   "there are more" exactly as the user described ("cards stacked behind each other in one row").
3. **Accessibility** — horizontal scroll is accessible out of the box; swipe interaction
   is standard SwiftUI without custom gesture recognizers.

### B.2 Layout Geometry

```
Leading inset: 16pt
Card width:    280pt
Card height:   170pt
Card spacing:  12pt
Trailing inset: (screen_width - 280 - 16 - 12) → next card peeks ~30–40pt
```

Use `.containerRelativeFrame` or fixed width. On iPhone 14/15/16/17 Pro (393pt logical),
the trailing peek is ~(393 - 16 - 280 - 12) = 85pt visible, which is generous but correct —
parent sees the full second card edge. Acceptable for demo; flag as polish OQ.

### B.3 Per-Card Visible Content

```
┌────────────────────────────────┐
│  Restaurant Name         DRAFT │  ← name (semibold/headline) + DRAFT badge (grey pill) if isDraft
│  Category Pill                 │  ← e.g. "Breakfast café" (small, secondary)
│                                │
│  🚗 2 min  ·  600m             │  ← drive time (DurationFormatting.friendly) + distance
│                                │
│  [Tap for suggestions →]       │  ← subtle caption affordance (optional — tap whole card)
└────────────────────────────────┘
```

- Background: `.secondarySystemBackground` rounded rect, `cornerRadius: 16`, shadow `opacity: 0.08`
- Tap the entire card → presents `FoodOptionDetailSheet`
- Do NOT render a "Recommended for [scenario]" badge — no per-option scenario assignment
  exists in the current model (`food_strategy` is on `ScenarioPlan`, not `FoodOption`).
  Spec deliberately omits this. See OQ-FOOD-DECK-6 for post-MVP path.
- Distance formatting: `"\(Int(option.distanceMeters ?? 0) / 10 * 10)m"` (round to 10m) or
  `"? m"` when `distanceMeters == nil`. Drive time: `DurationFormatting.friendly(minutes: option.driveTimeMin ?? 0)` after widening.

### B.4 Empty / Bag-Only State

When `bagFallbackOnly == true` OR `foodOptions.isEmpty`:
- Render a single full-width `BagFoodFallbackCard` — same orange container + `HardCodedStrings.bagFoodFallback` verbatim as `FoodCardView` uses today.
- NOT in a scroll deck — it's a single card, no peek affordance.
- This path uses `HardCodedStrings.bagFoodFallback` verbatim — no reparaphrasing.

### B.5 Sheet Presentation

Tap any deck card → `.sheet(isPresented:)` presenting `FoodOptionDetailSheet(option:)`:
- `.presentationDetents([.medium, .large])`
- `.presentationDragIndicator(.visible)`
- "Done" toolbar button (accessibility — consistent with all other sheets this session)

---

## §C — FoodOptionDetailSheet Structure

Sheet opens on deck card tap. Medium + large detents. Drag + Done button to dismiss.

```
NavigationStack {
    ScrollView {
        VStack(alignment: .leading, spacing: 16) {

            // 1. DRAFT badge (when isDraft)
            if option.isDraft {
                Text("Suggestions in development — confirm with your athlete")
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Color.gray.opacity(0.15), in: Capsule())
            }

            // 2. Header
            Text(option.name)           // large title
            CategoryPill(option.category)
            DriveDistanceRow(option)    // 🚗 X min · Ym

            Divider()

            // 3. Main options (always present if non-empty)
            if !option.suggestions.mainOptions.isEmpty {
                SectionHeader("What to order")
                BulletList(option.suggestions.mainOptions)
            }

            // 4. Add-ons (skip if empty)
            if !option.suggestions.addOns.isEmpty {
                SectionHeader("Add-ons & carbs")
                BulletList(option.suggestions.addOns)
            }

            // 5. Drinks
            if !option.suggestions.drinks.isEmpty {
                SectionHeader("Drinks")
                BulletList(option.suggestions.drinks)
            }

            // 6. Avoid (red iconography — skip if empty)
            if !option.suggestions.avoid.isEmpty {
                SectionHeader("Avoid before match", icon: "exclamationmark.triangle.fill", color: .red)
                BulletList(option.suggestions.avoid, color: .red.opacity(0.8))
            }

            // 7. Notes (small grey text — skip if empty)
            if !option.suggestions.notes.isEmpty {
                ForEach(option.suggestions.notes, id: \.self) { note in
                    Text(note).font(.caption).foregroundStyle(.secondary)
                }
            }

            Divider()

            // 8. Footer action — Open in Maps
            // Uses MKMapItem constructed from option.lat/lng + option.name
            // Gated: only shown when lat != nil && lng != nil
            if let lat = option.lat, let lng = option.lng {
                Button {
                    openInMaps(lat: lat, lng: lng, name: option.name)
                } label: {
                    Label("Open in Maps", systemImage: "map.fill")
                }
                .buttonStyle(.bordered)
            }

            Divider()

            // 9. Safety footer — VERBATIM from FoodCardView
            Text("If your player has food allergies, intolerances, or dietary restrictions, consult the relevant professional before following these suggestions.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding()
    }
    .navigationTitle(option.name)
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
        ToolbarItem(placement: .confirmationAction) {
            Button("Done") { dismiss() }
        }
    }
}
```

`openInMaps` helper:
```swift
private func openInMaps(lat: Double, lng: Double, name: String) {
    let placemark = MKPlacemark(coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng))
    let mapItem = MKMapItem(placemark: placemark)
    mapItem.name = name
    mapItem.openInMaps()
}
```

---

## §D — Venue Map — VenueMapSheet

### D.1 Library Decision: MapKit (LOCKED)

**MapKit.** Justification: (1) Zero new dependencies — MapKit is in the iOS SDK since iOS 2;
no `Package.swift` edits, no third-party keys, no Google Cloud account required.
(2) SwiftUI `Map` API (iOS 17+) provides the same interactive map experience parents
expect from the iOS Maps app they already use. (3) Demo-ready in a single delegate; Google
Maps iOS SDK would require provisioning a key and registering a bundle ID in Google Console,
which cannot be done in a sandbox. Google Maps is a post-MVP option if parents request
richer POI data overlays (see OQ-FOOD-DECK-5).

### D.2 Map Placement: Option (a) — Third Bubble in HeaderBubbleRow

**Reasoning:** Consistent with HEADER_BUBBLES_V1 pattern (one sheet entry per bubble; same
44pt circle visual style). Adding "View on map" to the FoodOptionDetailSheet footer (§C.8)
is additive — it's a pin-level hand-off to Apple Maps, not a full in-app map view.
Three HeaderBubbleRow bubbles is the correct limit; a fourth would crowd the row.

**Note:** `HeaderBubbleRow` signature widening is required — add `tournament: Tournament`
parameter alongside `plan: Plan` (see §I-6 and §G.13).

### D.3 Render Contract

```swift
// VenueMapSheet.swift (NEW)
// Requires: import MapKit

struct VenueMapSheet: View {
    let tournament: Tournament
    let foodOptions: [FoodOption]
    
    @State private var selectedFood: FoodOption? = nil
    @State private var showFoodDetail = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Map(initialPosition: .region(venueRegion)) {
                // Tournament venue pin — blue
                Marker(tournament.venue,
                       systemImage: "tennisball.fill",
                       coordinate: CLLocationCoordinate2D(
                           latitude: tournament.lat,
                           longitude: tournament.lon))
                .tint(.blue)

                // Food option pins — orange (only when lat/lng available)
                ForEach(foodOptionsWithCoords) { option in
                    Annotation(option.name,
                                coordinate: CLLocationCoordinate2D(
                                    latitude: option.lat!,
                                    longitude: option.lng!)) {
                        Button {
                            selectedFood = option
                            showFoodDetail = true
                        } label: {
                            ZStack {
                                Circle()
                                    .fill(Color.orange)
                                    .frame(width: 36, height: 36)
                                Image(systemName: "fork.knife")
                                    .foregroundStyle(.white)
                                    .font(.system(size: 16, weight: .semibold))
                            }
                        }
                    }
                }
            }
            .mapStyle(.standard)
            .navigationTitle("Tournament Map")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .sheet(isPresented: $showFoodDetail) {
                if let food = selectedFood {
                    FoodOptionDetailSheet(option: food)
                        .presentationDetents([.medium, .large])
                        .presentationDragIndicator(.visible)
                }
            }
        }
    }

    private var venueRegion: MKCoordinateRegion {
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: tournament.lat, longitude: tournament.lon),
            span: MKCoordinateSpan(latitudeDelta: 0.06, longitudeDelta: 0.06)
        )
    }

    private var foodOptionsWithCoords: [FoodOption] {
        foodOptions.filter { $0.lat != nil && $0.lng != nil }
    }
}
```

- **Tournament annotation:** blue, `tennisball.fill` system image, tournament venue name
- **Food pins:** orange, `fork.knife` system image. Tap → `FoodOptionDetailSheet` (reuse §C)
- **Region span:** `latitudeDelta: 0.06, longitudeDelta: 0.06` ≈ 4-mile view. Acceptable for
  Dallas demo where all 4 fixtures are within ~3 miles. OQ-FOOD-DECK-4 for adaptive span.
- **Gating:** bubble always shown (tournament.lat/lon are non-optional). If no food options
  have coords, only the venue pin renders — no error state needed.
- **Empty food state:** natural — venue pin alone renders cleanly. No explicit empty state needed.

### D.4 "Open in Maps" in FoodOptionDetailSheet (Option d — Additive)

In addition to the bubble map sheet, every `FoodOptionDetailSheet` footer contains an
"Open in Maps" button that opens the specific restaurant in Apple Maps for turn-by-turn
directions (§C.8). This is additive to the bubble map — two different surfaces, two different
parent flows:
- Bubble map: see the whole picture (tournament + all food)
- Detail sheet "Open in Maps": get directions to this specific restaurant

---

## §E — Updated Dashboard Order

```
0. EmergencyStrip      (when extreme_heat_risk — above Picker; QA-IA-1 fixed in Phase 8.1)
1. Singles/Doubles Picker  (when envelope.hasBoth)
2. HeaderBubbleRow [Plan Summary] [Weather] [Map]    ← +1 bubble (NEW)
3. ScheduleStripView
4. NextActionCard
5. FoodOptionDeck                                    ← REPLACES FoodCardView inline
6. Scenario cards
7. Full Day Timeline button
8. Disclaimer footer
```

`FoodCardView` is NOT rendered on the dashboard. Its source remains in the build for
previews (see §G.14 fate decision). `FoodOptionDeck` is the only on-dashboard food surface.

---

## §F — User Stories (append to USER_STORIES.md)

### US-FOOD-1 — Food Deck Glanceability

**As a** parent at a tennis tournament,
**I want** to see nearby food options as a swipeable deck of cards (not a wall of text),
**so that** I can see multiple options at a glance without scrolling through a long list.

**Given** the plan has ≥1 non-bag-only food option,
**When** I scroll to the food section of the dashboard,
**Then** I see a horizontal scroll-snap deck of cards, each showing restaurant name, category, and drive time. The edge of the next card is visible (~30pt), signaling more options.

**Given** the plan has no nearby food (bag_fallback_only),
**When** I scroll to the food section,
**Then** I see a single full-width bag-food fallback card with the verbatim `HardCodedStrings.bagFoodFallback` text.

### US-FOOD-2 — Per-Restaurant Structured Suggestions

**As a** parent deciding what to order at Starbucks (or any restaurant),
**I want** to tap the card and see structured suggestions — what to order, what to drink, what to avoid, and timing notes,
**so that** I don't have to parse a single wall of text to find the relevant information.

**Given** I tap a food option card in the deck,
**When** the detail sheet opens,
**Then** I see structured sections: "What to order," "Add-ons & carbs" (if applicable), "Drinks," "Avoid before match" (if applicable), timing notes, and an allergy/dietary disclaimer footer. Empty sections are hidden.

**Given** the food option is a DRAFT template (e.g. Starbucks, Jimmy John's),
**When** the detail sheet opens,
**Then** a grey "Suggestions in development — confirm with your athlete" badge is visible at the top.

### US-MAP-1 — Venue Map Overview

**As a** parent unfamiliar with the tournament venue and surrounding area,
**I want** to tap a Map bubble to see a real interactive map centered on the tournament location with food option pins,
**so that** I can orient myself and see where food is relative to the courts.

**Given** I tap the Map bubble in the dashboard header,
**When** the map sheet opens,
**Then** I see an interactive MapKit map centered on the tournament venue with a blue tennis-ball pin at the venue and orange fork-knife pins at nearby food locations.

**Given** the tournament venue has no food options with coordinates,
**When** the map sheet opens,
**Then** only the venue pin is shown — no error or empty state message needed (venue pin alone is informative).

### US-MAP-2 — Food Pin Drill + Directions

**As a** parent who sees a food pin on the venue map,
**I want** to tap the pin to see that restaurant's structured suggestions, and then optionally get turn-by-turn directions,
**so that** I can make a decision and navigate without leaving the context I'm in.

**Given** I tap a food pin on the venue map,
**When** the food detail sheet opens,
**Then** I see the same structured suggestions as tapping the card in the deck. An "Open in Maps" button at the bottom launches Apple Maps with directions to that restaurant.

---

## §G — Engineering Hand-Off (copy-paste)

### Backend (BD) — 5 items

**G.1** EDIT `apps/api/src/playfuel_api/models/api.py`:
- Add `FoodSuggestions` Pydantic class above `FoodOption` (per §A.1 schema — 5 fields, all `list[str] = []`)
- Add `suggestions: FoodSuggestions = Field(default_factory=FoodSuggestions)` to `FoodOption`
- Add `lat: Optional[float] = None` and `lng: Optional[float] = None` to `FoodOption`
- Keep `recommended_order: str` unchanged (still derived — not removing for back-compat)
- `FoodRecommendationSummary` is NOT changed — LLM still consumes only `recommended_order`

**G.2** EDIT `apps/api/src/playfuel_api/services/places.py`:
- Add `lat: float | None = None` and `lng: float | None = None` to `RawPlace` dataclass
- Backfill all 4 `_DALLAS_FIXTURE` entries with plausible Dallas coordinates:
  - Chipotle: `lat=32.7825, lng=-96.7975`
  - Jimmy John's: `lat=32.7820, lng=-96.8025`
  - Central Market: `lat=32.7755, lng=-96.7920`
  - Starbucks: `lat=32.7805, lng=-96.7990`
- NOTE: These are illustrative coords. Real lat/lng from Google Places will replace these
  when GooglePlacesProvider is implemented (OQ-PLACES-1).

**G.3** EDIT `apps/api/src/playfuel_api/rules/food.py`:
- Add `suggestions_for(category: str) -> tuple[FoodSuggestions, bool]` — returns per-§A.3 templates.
  Lazy-import `FoodSuggestions` from `playfuel_api.models.api` to avoid circular import
  (same pattern as `FoodOption` lazy import in `assemble_food_options`).
- Add `derive_recommended_order(suggestions: FoodSuggestions) -> str` per §A.2 algorithm.
- In `assemble_food_options`: replace `recommended_order_for(category)` call with `suggestions_for(category)`;
  derive `recommended_order` via `derive_recommended_order(suggestions)`;
  populate new `FoodOption(lat=place.lat, lng=place.lng, suggestions=suggestions, ...)`.
- Keep `recommended_order_for(category)` as a thin shim:
  ```python
  def recommended_order_for(category: str) -> tuple[str, bool]:
      """Deprecated shim — prefer suggestions_for + derive_recommended_order."""
      sugg, is_draft = suggestions_for(category)
      return derive_recommended_order(sugg), is_draft
  ```
  So any legacy callers (e.g. LLM input builder) remain green.

**G.4** NEW `apps/api/src/playfuel_api/tests/test_food_suggestions.py` — ≥8 named tests:
1. `test_suggestions_fast_casual_bowl` — returns non-empty `main_options`, `drinks`, `avoid`, `notes`; `is_draft=False`
2. `test_suggestions_breakfast_cafe` — returns oatmeal in `main_options`; `is_draft=True`
3. `test_suggestions_sandwich_shop` — returns turkey/chicken in `main_options`; `is_draft=True`
4. `test_suggestions_grocery_prepared` — returns rotisserie chicken in `main_options`; `is_draft=True`
5. `test_suggestions_restaurant_fallback` — unknown category → restaurant template; `is_draft=True`
6. `test_derive_recommended_order_chipotle` — `derive_recommended_order` with Chipotle data returns a non-empty string containing "rice" and "Drinks"
7. `test_derive_recommended_order_empty` — `FoodSuggestions()` (all empty) → returns `""` (not crash)
8. `test_assemble_food_options_surfaces_lat_lng` — `assemble_food_options` with mock Dallas fixtures surfaces non-None `lat`/`lng` on each returned `FoodOption`
9. `test_assemble_food_options_surfaces_suggestions` — each returned `FoodOption.suggestions.main_options` is non-empty for `fast_casual_bowl` category
10. `test_bag_fallback_only_path` — all-bag-only buckets → `([], True)` with no suggestions crash

**G.5** UPDATE existing food tests — `grep -rn '"recommended_order"' apps/api/src/playfuel_api/tests/`:
- Any test asserting the flat `recommended_order` string still passes (it's derived; value will change
  slightly since `derive_recommended_order` may produce a different string than the old verbatim template).
  Update assertions to use `assert "rice" in result.recommended_order` (content-based) rather than
  exact string match. Most likely affected files: `test_food.py`, `test_generate_plan_hotfix.py`.

---

### iOS (FE) — 14 items + mandatory xcodegen

**G.6** NEW `Sources/PlayFuel/Models/FoodSuggestions.swift`:
- `struct FoodSuggestions: Codable, Hashable` with 5 fields per §A.1 Swift definition
- Default empty init (used by FakeData previews and as decode fallback)
- Doc comment: "Structured per-restaurant meal suggestions. Rendered in FoodOptionDetailSheet. Not consumed by LLM input — LLM uses derived recommendedOrder only."

**G.7** EDIT `Sources/PlayFuel/Models/FoodOption.swift`:
- Add `let suggestions: FoodSuggestions` (with default in init: `FoodSuggestions()`)
- Add `let lat: Double?`
- Add `let lng: Double?`
- **Widen `let driveTimeMin: Int` → `let driveTimeMin: Int?`** (resolves OQ-FOOD-DECK-1 / §I-3)
- Keep all other fields unchanged

**G.8** EDIT `Sources/PlayFuel/Networking/DTOs.swift` — `FoodOptionDTO`:
- Add `struct FoodSuggestionsDTO: Decodable` with 5 `[String]` fields:
  `mainOptions`, `addOns`, `drinks`, `avoid`, `notes` (all `decodeIfPresent ?? []`)
- In `FoodOptionDTO`: add `let suggestions: FoodSuggestionsDTO?` and `let lat: Double?` and `let lng: Double?`
- In `FoodOptionDTO.toModel()`: change `driveTimeMin: driveTimeMinutes ?? 0` → `driveTimeMin: driveTimeMinutes` (pass through nil-safe, per §I-7)
- Map `suggestions?: FoodSuggestionsDTO` → `FoodSuggestions` (nil → `FoodSuggestions()`)
- Map `lat` and `lng` through directly

**G.9** EDIT `Sources/PlayFuel/Views/FoodCardView.swift`:
- `option.driveTimeMin` is now `Int?`. Wrap usage:
  `DurationFormatting.friendly(minutes: option.driveTimeMin ?? 0)`
- Add doc comment at top: "Replaced by FoodOptionDeck on dashboard; preserved for previews/fallback per FOOD_DECK_AND_MAP_V1 §G.14."
- No other changes to FoodCardView

**G.10** NEW `Sources/PlayFuel/Views/FoodOptionDeck.swift`:
- Props: `foodOptions: [FoodOption]`, `bagFallbackOnly: Bool`
- Section header: `Label("Nearby Food Options", systemImage: "fork.knife.circle.fill")` — same as FoodCardView (visual continuity)
- Empty / bag-only branch: `BagFoodFallbackCard` (private inner view using `HardCodedStrings.bagFoodFallback`)
- Deck branch: `ScrollView(.horizontal, showsIndicators: false)` with `LazyHStack(spacing: 12)` —
  `.scrollTargetBehavior(.viewAligned)` + `.scrollTargetLayout()` (iOS 17+)
- Each card: `FoodOptionCard(option:)` (private inner view per §B.3) — tap → `selectedOption = option`
- Sheet presentation: `@State var selectedOption: FoodOption?` → `.sheet(item: $selectedOption)` presenting `FoodOptionDetailSheet`
- Leading/trailing padding: `.safeAreaPadding(.horizontal, 16)` (or `contentMargins`)
- Note: `contentMargins(_:for:)` is iOS 17+; confirm API availability vs `safeAreaPadding`

**G.11** NEW `Sources/PlayFuel/Views/Sheets/FoodOptionDetailSheet.swift` per §C:
- Props: `option: FoodOption`
- Implements §C structure verbatim
- `openInMaps` helper per §C
- "Done" toolbar button + drag dismiss
- Safety footer verbatim: "If your player has food allergies, intolerances, or dietary restrictions, consult the relevant professional before following these suggestions."

**G.12** NEW `Sources/PlayFuel/Views/Sheets/VenueMapSheet.swift` per §D.3:
- `import MapKit` required
- Props: `tournament: Tournament`, `foodOptions: [FoodOption]`
- Uses SwiftUI `Map` (iOS 17+) — NOT `UIViewRepresentable(MKMapView)`
- Food pins: `Annotation` (not `Marker`) — allows custom view (orange circle + `fork.knife` icon)
- Venue pin: `Marker` with `tennisball.fill` tint `.blue`
- Tap food annotation → `FoodOptionDetailSheet` via `@State selectedFood: FoodOption?`
- "Done" toolbar button

**G.13** EDIT `Sources/PlayFuel/Views/HeaderBubbleRow.swift`:
- Add `tournament: Tournament` parameter (alongside existing `plan: Plan`)
- Add `@State private var mapSheetShown = false`
- Add third `HeaderBubble` in the HStack:
  ```swift
  HeaderBubble(
      systemImage: "map.fill",
      label: "Tournament map",
      badge: nil,
      tint: .green,
      action: { mapSheetShown = true }
  )
  ```
- Add `.sheet(isPresented: $mapSheetShown)` presenting `VenueMapSheet(tournament: tournament, foodOptions: plan.foodOptions ?? [])`

**G.14** EDIT `Sources/PlayFuel/Views/TournamentDashboardView.swift`:
- Replace `FoodCardView(foodOptions: ...)` call with `FoodOptionDeck(foodOptions: plan.foodOptions ?? [], bagFallbackOnly: plan.bagFallbackOnly)`
- Update `HeaderBubbleRow(plan: plan)` → `HeaderBubbleRow(plan: plan, tournament: tournament)` — pass tournament from the view's context (TournamentDashboardView already has `tournament` as a property or can resolve it from AppState)
- FoodCardView is NOT rendered here anymore

**G.15** EDIT `Sources/PlayFuel/Data/FakeData.swift`:
- Widen `FoodOption` init to include `suggestions`, `lat`, `lng` fields on all 3 existing fixtures
- Add Starbucks as 4th fixture:
  ```swift
  FoodOption(
      id: UUID(uuidString: "CC000004-0000-0000-0000-000000000004")!,
      name: "Starbucks",
      category: "breakfast_cafe",
      driveTimeMin: 2,   // now Int? — value is 2
      recommendedOrder: "Oatmeal or whole-grain item. Small black coffee ok. Avoid pastries.",
      isDraft: true,
      distanceMeters: 600,
      placeId: nil,
      provider: "fake",
      suggestions: FoodSuggestions(
          mainOptions: ["Oatmeal (plain or lightly sweetened)", "Whole-grain item with eggs if available"],
          addOns: ["Banana or fruit cup — easy carb bridge"],
          drinks: ["Water (primary)", "Small black coffee or tea if tolerated"],
          avoid: ["Pastries and muffins", "Large milk-based drinks", "High-sugar drinks"],
          notes: ["Eat ≥45 min before play. DRAFT — confirm with your athlete."]
      ),
      lat: 32.7805,
      lng: -96.7990
  )
  ```
- Update all 3 existing fixtures with their structured `suggestions` (per §A.3 templates) and `lat`/`lng` coords:
  - Chipotle: `lat: 32.7825, lng: -96.7975`; suggestions per §A.3 `fast_casual_bowl`
  - Jimmy John's: `lat: 32.7820, lng: -96.8025`; suggestions per §A.3 `sandwich_shop`
  - Central Market: `lat: 32.7755, lng: -96.7920`; suggestions per §A.3 `grocery_prepared`
- Update `dallasFoodOptions` to include all 4 entries

**G.16** EDIT `apps/ios/PlayFuel/README.md`:
- Screen Tour: replace FoodCardView row with FoodOptionDeck row; add FoodOptionDetailSheet row; add VenueMapSheet row; add Map bubble to HeaderBubbleRow row description
- Add Phase 8.3 section

**G.17 CRITICAL — pbxproj regen (lesson from Phase 8.2 build failure):**
```
cd apps/ios/PlayFuel && xcodegen generate
```
Verify with:
```
grep -c "FoodSuggestions.swift\|FoodOptionDeck.swift\|FoodOptionDetailSheet.swift\|VenueMapSheet.swift" \
    PlayFuel.xcodeproj/project.pbxproj
```
All four counts must be ≥1. Then run:
```
xcodebuild -project PlayFuel.xcodeproj -scheme PlayFuel \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=latest' build
```
Must return `BUILD SUCCEEDED`.

### Acceptance Criteria (both BD + FE)

1. **277 + new ≥ 287 tests pass**; Scenario 5 xfail unchanged; eval exit 0
2. `FoodSuggestions.fast_casual_bowl` returns non-empty `main_options`, `drinks`, `avoid`, `notes`; `is_draft=False`
3. `FoodSuggestions.breakfast_cafe` returns "oatmeal" in `main_options`; `is_draft=True`
4. `assemble_food_options` returns `FoodOption.lat` and `.lng` as non-nil for Dallas fixtures
5. Dashboard renders `FoodOptionDeck` (not `FoodCardView`) at position #5
6. Deck shows ≥3 cards; next card peeks on right edge
7. Tap any card → `FoodOptionDetailSheet` opens with structured sections
8. Starbucks card shows DRAFT badge; tapping shows "Oatmeal" in main options
9. Map bubble (3rd in HeaderBubbleRow) opens `VenueMapSheet` with venue blue pin + orange food pins
10. Tap orange food pin → `FoodOptionDetailSheet` for that restaurant
11. `FoodOptionDetailSheet` footer renders verbatim allergy/dietary disclaimer
12. iOS BUILD SUCCEEDED after xcodegen regen
13. `FoodCardView.swift` still exists in build (preserved for previews); doc-comment present
14. `FoodOption.driveTimeMin` is `Int?` in iOS model; `FoodOptionDTO.toModel()` passes `driveTimeMinutes` nil-safe

---

## §H — DRAFT-Flagged OQs

| ID | Severity | Description |
|----|----------|-------------|
| **OQ-FOOD-DECK-1** | ✅ RESOLVED | `driveTimeMin: Int → Int?` — latent decode-fail bug fixed in this delegate (§I-3, §G.7-8). |
| **OQ-FOOD-DECK-2** | 🟡 Pre-launch | Structured copy for `sandwich_shop`, `grocery_prepared`, `breakfast_cafe`, `restaurant` templates is DRAFT (OQ-B carries). Nutrition review required before App Store submission. |
| **OQ-FOOD-DECK-3** | ⚪ Post-demo | Mock fixture coords are best-guess Dallas offsets — not real Place API geometry. Replace with Google passthrough when GooglePlacesProvider is implemented (OQ-PLACES-1). |
| **OQ-FOOD-DECK-4** | ⚪ Polish | Map default span `latitudeDelta: 0.06` (≈4mi) is fixed. Adaptive `showAnnotations` may zoom further for distant options. Acceptable for demo. |
| **OQ-FOOD-DECK-5** | ⚪ Post-MVP | "Open in Maps" uses `MKMapItem.openInMaps()`. On the rare device without Apple Maps, fails silently. Google Maps URL scheme (`comgooglemaps://`) as fallback is post-MVP. |
| **OQ-FOOD-DECK-6** | ⚪ Post-MVP | No per-option "Recommended for [scenario]" badge — `food_strategy` is on `ScenarioPlan`, not `FoodOption`. Add optional `recommended_for_buckets: list[str]` to `FoodOption` to enable post-MVP. |
| **OQ-FOOD-DECK-7** | ⚪ Monitor | LLM input uses derived `recommendedOrder` line. If LLM prose quality regresses vs. old verbatim Chipotle string, consider also passing `suggestions` to `PlanExplanationInput.food_recommendations[].suggestions`. |
| **OQ-FOOD-DECK-8** | ⚪ Doc cleanup | `RULES_CONSTANTS_V1.md §F.3` registered template ("Chicken rice bowl with light beans, mild toppings, sauce on the side") diverges from `food.py` authoritative template. §F.3 doc is stale. Update doc to match `food.py` in a future doc-cleanup pass. |

---

## §I (recap) — PM Verification Findings

Summarized from the top of this doc for Engineering reference:

- **RawPlace has NO lat/lng** — must add; backfill 4 Dallas fixtures (§G.2) ← real gap
- **FoodOption Pydantic has NO lat/lng** — must add (§G.1) ← real gap
- **iOS `driveTimeMin: Int` non-optional** — latent bug; widen to `Int?` (§G.7, §G.8, §G.9) ← real latent bug
- **Starbucks absent from `FakeData.dallasFoodOptions`** — add as 4th fixture (§G.15) ← demo gap
- **`food.py` template diverges from §F.3 doc** — use `food.py` as authoritative (§I-5, OQ-FOOD-DECK-8)
- **HeaderBubbleRow signature widening needed** — add `tournament: Tournament` (§G.13, §G.14) ← real call-site change
- **`FoodOptionDTO.toModel()` uses `?? 0` for driveTimeMin** — update to pass-through nil-safe (§G.8)
- **`PlanExplanation.scenario_explanations` DOES exist** — not surfaced in FoodOptionDetailSheet (correct; ScenarioCardView handles it)
