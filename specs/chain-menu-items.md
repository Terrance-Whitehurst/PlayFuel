# chain-menu-items.md — Chain-Specific Restaurant Menu Items
> Authority: Product Manager · Date: 2026-05-04
> Status: LOCKED — Engineering executes §G verbatim after clearing §G.0 pre-check
> Ref: FOOD_DECK_AND_MAP_V1.md, SAFETY_DISCLAIMERS.md §C, RULES_CONSTANTS_V1.md

---

## PM Verification Findings (pre-spec — read before any §)

> All key source files read before scribing. Decisions in the brief are LOCKED;
> divergences against disk are flagged below.

| # | Finding | Source | Impact |
|---|---------|--------|--------|
| **V-1** | `FoodOption` Pydantic (`models/api.py` L~297) has `suggestions`, `lat`, `lng` — **DOES NOT** have `chain_matched` or `chain_as_of`. Both are genuinely new fields. | `models/api.py` | Add in §J |
| **V-2** | iOS `FoodOption.swift` has `suggestions: FoodSuggestions?`, `lat: Double?`, `lng: Double?` — **DOES NOT** have `chainMatched: Bool` or `chainAsOf: String?`. Both are genuinely new fields. | `FoodOption.swift` | Add in §J |
| **V-3** | `_SUGGESTIONS` dict and `suggestions_for()` + `derive_recommended_order()` functions in `food.py` are **FULLY IMPLEMENTED** for all 12 categories. `assemble_food_options` already calls `suggestions_for(category)`. Brief implies these may not exist — they do. Chain lookup inserts BEFORE this call as an override. No re-implementation needed. | `food.py L~458` | §D integration point confirmed |
| **V-4** | Brief's §J says "view-level conditional rendering in `FoodSuggestionsView`". **No such file exists.** Correct file: `FoodOptionDetailSheet.swift` (`Views/Sheets/`). Already renders 5-bucket suggestions. Needs 2 additions: chain caption + disclaimer. | `FoodOptionDetailSheet.swift` | File path corrected in §J |
| **V-5** | `_NAME_HEURISTICS` in `food.py` already catches Chipotle, CAVA, Qdoba, Moe's, Jimmy John's, Subway, Jersey Mike's, Potbelly, Firehouse for **category bucketing**. Chain registry lookup is a SEPARATE, ADDITIVE step — it overrides the TEMPLATE (suggestions text), not the category assignment. Both run; they're independent. | `food.py L~96` | §D must clarify independence |
| **V-6** | `chain_menus.json` does NOT exist in `rules/`. New file, no conflict. Next free migration: 0017 — no migration needed for this feature. | `ls rules/` · `ls migrations/` | Confirmed §J |
| **V-7** | Brief says "iOS rendering reuses `FoodSuggestionsView` zero-changes". Incorrect — `FoodOptionDetailSheet.swift` needs 2 new rendering blocks (chain caption, chain disclaimer). Not zero-changes. | `FoodOptionDetailSheet.swift` | §E + §J corrected |
| **V-8** | `categorize_place()` still must run in `assemble_food_options` so `FoodOption.category` is always set. Chain lookup result overrides `suggestions` and sets `chain_matched`/`chain_as_of` but does NOT change the `category` field. | `food.py L~525` | §D confirmed |

---

## §A — Data-Source Survey

| Option | Verdict | Reason |
|--------|---------|--------|
| **National-chain hardcoded JSON in repo** | ✅ **MVP choice** | Stable menus, zero hallucination, zero recurring cost, zero new API dependency. `as_of` date stamped per entry. Aligned with §C "never invents menu items." |
| Third-party menu APIs (DoorDash, Uber Eats, Yelp Fusion, MenuLink) | ❌ Reject for MVP | Licensing for in-app redisplay is unclear/expensive; coverage of small regional spots is hit-or-miss; introduces a new vendor dependency for a non-critical feature. Revisit post-TestFlight if demand justifies it. |
| LLM-generated menu items | ❌ Hard reject | Direct violation of SAFETY_DISCLAIMERS.md §C "Invented menu items." Even 99% accurate, hallucinated allergens at a youth tournament is the worst-case outcome. Non-negotiable. |
| Web scraping | ❌ Reject | ToS risk (Chick-fil-A, Chipotle, McDonald's prohibit automated access); brittle; maintenance sink; menu scraping is explicitly out of scope in `README.md`. |
| User-contributed / curator-reviewed | ❌ Defer | Cold-start problem; moderation burden incompatible with parent-only operator model. |

---

## §B — Safety Strategy

**Posture:** The "never invents menu items" rule is satisfied when items are sourced from the chain's own published menu at registry-build time, with an `as_of` date in the record. This is curation, not fabrication.

**Disclaimer (verbatim — must render under every chain-match suggestions block):**
> "Items shown are typical menu items at this chain. Menus and ingredients vary by location and change over time. Verify allergens with the restaurant before ordering."

**Allergen handling:** Do NOT surface per-item allergen claims. The disclaimer above is the allergen posture — parent responsibility, not app responsibility. Same posture as today's bucket templates.

**Update cadence:** Registry is a versioned JSON in the repo (`chain_menus.json`). Each entry has `as_of: "YYYY-MM-DD"`. Quarterly review (4× per year) is documented but not automated. iOS renders an additional inline note when `chainAsOf` is older than 9 months:
> "Menu data is older than 9 months — verify with the restaurant."

**Safety-lint scope:** The existing `safety_lint` step on LLM output is UNCHANGED. Chain registry items are NOT LLM-produced — they are static, PR-reviewed repo content. Safety lint does not apply to chain registry items; PR review is the gate.

---

## §C — MVP Boundary

**Scope:** ~26 chains × 3–5 tournament-friendly items each ≈ ~130 curated entries.

**Chain selection — Sun Belt junior-tennis prevalence (TX, FL, GA, Carolinas, AZ, So. Cal.):**

| Category | Chains |
|----------|--------|
| Fast-casual bowl | Chick-fil-A, Chipotle, CAVA, Sweetgreen, Chopt, Panda Express |
| Sandwich / sub | Subway, Jersey Mike's, Jimmy John's, Firehouse Subs |
| Breakfast / café | Starbucks, Dunkin', Einstein Bros. Bagels, Tropical Smoothie Cafe, Jamba |
| Burgers (grilled options) | Five Guys, Shake Shack, Whataburger, In-N-Out |
| Pizza (limited) | Domino's, Pizza Hut |
| Mexican fast-casual | Qdoba, Moe's Southwest Grill |
| Grocery prepared | Whole Foods, Sprouts |

**Per-chain items (3–5 each):**
- 1 main (lean protein + complex carb)
- 1 add-on / side (fruit, light snack)
- 1 drink (water-first)
- 1–2 "avoid" callouts specific to this chain
- 1 timing note

**Fall-through:** Any restaurant NOT matching a chain entry → existing `suggestions_for(category)` bucket template (today's behavior). ~80%+ of plans that don't hit a chain are UNAFFECTED.

---

## §D — Match Strategy

**Chain lookup is name-based, independent of category bucketing:**

1. `categorize_place(types, name)` runs as today → sets `FoodOption.category` (unchanged).
2. `lookup_chain(name)` runs immediately after → normalizes the name and checks the registry.
3. If match: `suggestions` from registry; `chain_matched = True`; `chain_as_of = entry.as_of`.
4. If no match: `suggestions` from `suggestions_for(category)` (today's behavior); `chain_matched = False`.

**Normalization algorithm (in `chain_lookup.py`):**
```python
import re

def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, strip trailing store numbers/suffixes."""
    n = name.lower()
    n = re.sub(r"[^\w\s]", "", n)          # strip punctuation
    n = re.sub(r"\s*#\s*\d+", "", n)       # strip #4521
    n = re.sub(r"\s*-\s*\d+", "", n)       # strip - 123
    n = re.sub(r"\b(drive\s*thru|drivethru|drive\s*through)\b", "", n)
    return n.strip()
```

**Matching:** compare `normalize_name(place.name)` against each chain's `match_aliases` list (aliases are already normalized in the registry). First exact match wins. No fuzzy matching.

**Independence from `_NAME_HEURISTICS`:** `_NAME_HEURISTICS` buckets a place into a CATEGORY (e.g. Chipotle → `fast_casual_bowl`). Chain lookup overrides the TEMPLATE TEXT only. Both run; they're independent. Chipotle still gets category `fast_casual_bowl` even when the chain registry overrides its suggestions.

---

## §E — UX Integration

**Replacement, not addition.** `FoodOptionDetailSheet.swift` renders chain-specific items when `option.chainMatched == true`, replacing the generic category template in the same 5-bucket layout. Zero new view files.

**Two new rendering blocks in `FoodOptionDetailSheet.swift`:**

1. **Chain caption** (immediately below the header / above the divider, when `chainMatched == true`):
   ```swift
   if option.chainMatched, let asOf = option.chainAsOf {
       let display = String(asOf.prefix(7))  // "YYYY-MM"
       Text("Chain menu · as of \(display)")
           .font(.caption).foregroundStyle(.secondary)
   }
   ```

2. **Chain disclaimer** (below notes, above the existing "Open in Maps" button, when `chainMatched == true`):
   ```swift
   if option.chainMatched {
       Text("Items shown are typical menu items at this chain. Menus and ingredients vary by location and change over time. Verify allergens with the restaurant before ordering.")
           .font(.caption2).foregroundStyle(.secondary)
   }
   ```

3. **Stale-data note** (below chain disclaimer, when `chainMatched == true` and `chainAsOf` is older than 9 months):
   ```swift
   if option.chainMatched, let staleNote = staleDataNote {
       Text(staleNote)
           .font(.caption2).foregroundStyle(.orange)
   }
   // private var staleDataNote: String? — computes from chainAsOf vs Date.now
   ```

**Tap target:** tapping individual items does NOTHING. Informational only. No ordering integration.

**Loading state:** registry is a local JSON bundled with the API; lookup is sub-millisecond. No loading UI.

---

## §F — Acceptance Criteria

- **AC#1** When a parent opens a food card for a chain in the registry (e.g. Chick-fil-A, Chipotle, Starbucks), `FoodOptionDetailSheet` shows chain-specific items from `chain_menus.json`, not the generic category template. `FoodOption.chainMatched == true`.
- **AC#2** When a parent opens a food card for a non-covered chain or local restaurant, the existing category-template behavior is unchanged. `FoodOption.chainMatched == false`. Zero regression for the ~80%+ of plans that don't hit a chain.
- **AC#3** The chain-menu disclaimer renders verbatim ("Items shown are typical menu items at this chain. Menus and ingredients vary by location and change over time. Verify allergens with the restaurant before ordering.") on every chain-match card and ONLY on chain-match cards.
- **AC#4** When `chainAsOf` is a date more than 9 months before today (testable by setting `as_of` to a fixed old date in a test registry), the additional "Menu data is older than 9 months — verify with the restaurant." note renders in orange.
- **AC#5** `FoodOption` API response includes `chainMatched: Bool` and `chainAsOf: String?`. Tests assert: (a) matched chain → `chainMatched=true` + `chainAsOf="YYYY-MM-DD"`; (b) unmatched → `chainMatched=false` + `chainAsOf=null`; (c) `chain_menus.json` loads without error on API startup.

---

## §G — Engineering / Validation Pre-Commit Asks + Open Questions

**Engineering pre-check (do before writing a line of code):**
- **§G.0** Run a live `flyctl logs` plan-gen call and grep for `places.displayName.text` shape in the raw Google Places response. Spot-check Chipotle, Starbucks, and Chick-fil-A — confirm `displayName.text` returns the chain name in a form that normalizes correctly. Use `normalize_name()` on the returned string and confirm it matches a registry alias. If it doesn't match for a chain, add the observed form as a new alias BEFORE shipping.

**Validation pre-check:**
- Confirm disclaimer copy does not trip SAFETY_DISCLAIMERS.md §C (it explicitly disclaims and does not claim — passes, but confirm).

**Open Questions:**

| ID | Severity | Description | Owner |
|----|----------|-------------|-------|
| **OQ-CHAIN-1** | 🟡 Pre-TestFlight | Allergen disclaimer: is "Verify allergens with the restaurant before ordering" sufficient for a parent of an allergic child? PM lean: YES (explicit disclaimer, parent has primary responsibility per §F of SAFETY_DISCLAIMERS). Flag for legal review at TestFlight gate alongside OQ-06. | PM + External counsel |
| **OQ-CHAIN-2** | 🟡 Pre-TestFlight | Does adding "no sauce / no pickles" to a recommended item constitute a customization that changes allergen profile? PM lean: NO (we're suggesting tournament-friendly modifications, not making allergen claims). Flag with OQ-CHAIN-1. | PM + External counsel |
| **OQ-CHAIN-3** | 🟢 Quarterly | Chain registry `as_of` dates — who owns the quarterly review? Recommend: PM reviews before each TestFlight cycle. Registry PRs require PM sign-off. | PM |
| **OQ-CHAIN-4** | 🟢 Post-MVP | ~23 chain stubs are marked `[DRAFT — populate before TestFlight]`. Population task needs to be assigned before beta ship. | PM / planning |

---

## §H — Non-Goals (explicitly out of scope)

- Live menu data feeds or any third-party menu API
- LLM-generated items (even retrieval-grounded)
- Per-item allergen or nutrition labels (calories, macros)
- Ordering integration (DoorDash, Uber Eats deep-links)
- Local restaurant menus
- User-contributed menu items
- Map deep-link to chain ordering
- Web scraping of chain menus
- Fuzzy name matching (Levenshtein, embeddings)

---

## §I — Registry Schema + Skeleton Registry

**File:** `apps/api/src/playfuel_api/rules/chain_menus.json`

**Schema:**
```json
{
  "version": "1.0.0",
  "registry_as_of": "YYYY-MM-DD",
  "chains": [
    {
      "id": "<slug>",
      "display_name": "<Display Name>",
      "match_aliases": ["<normalized alias 1>", "<normalized alias 2>"],
      "category_hint": "<food.py category string>",
      "as_of": "YYYY-MM-DD",
      "suggestions": {
        "main_options": [],
        "add_ons": [],
        "drinks": [],
        "avoid": [],
        "notes": []
      }
    }
  ]
}
```

**First 3 entries (fully populated — demo-critical):**

```json
{
  "id": "chick-fil-a",
  "display_name": "Chick-fil-A",
  "match_aliases": ["chickfila", "chick fil a", "chick-fil-a"],
  "category_hint": "fast_casual_bowl",
  "as_of": "2026-05-04",
  "suggestions": {
    "main_options": ["Grilled Chicken Sandwich (no pickles, no sauce)", "Grilled Nuggets — 8 ct"],
    "add_ons": ["Fruit Cup", "Side Salad (no dressing)"],
    "drinks": ["Bottled Water", "Diet Lemonade if tolerated"],
    "avoid": ["Waffle Fries — high fat before match", "Milkshakes — high sugar/dairy"],
    "notes": ["Eat 60–90 min before next match. Grilled only — avoid Classic fried."]
  }
}
```
```json
{
  "id": "chipotle",
  "display_name": "Chipotle Mexican Grill",
  "match_aliases": ["chipotle", "chipotle mexican grill"],
  "category_hint": "fast_casual_bowl",
  "as_of": "2026-05-04",
  "suggestions": {
    "main_options": [
      "Rice bowl: white or brown rice, black beans, grilled chicken",
      "Burrito bowl (no tortilla): chicken, rice, mild salsa, lettuce"
    ],
    "add_ons": [],
    "drinks": ["Water — 16–20 oz with the meal"],
    "avoid": ["Sour cream", "Cheese", "Guacamole — high fat before competition"],
    "notes": ["Eat 60–90 min before next match. Mild salsa only."]
  }
}
```
```json
{
  "id": "starbucks",
  "display_name": "Starbucks",
  "match_aliases": ["starbucks"],
  "category_hint": "breakfast_cafe",
  "as_of": "2026-05-04",
  "suggestions": {
    "main_options": [
      "Classic Oatmeal (plain, no brown sugar packet)",
      "Spinach, Feta & Cage Free Egg White Wrap"
    ],
    "add_ons": ["Banana — easy carb bridge"],
    "drinks": ["Water (primary)", "Small plain coffee or unsweetened tea if tolerated"],
    "avoid": [
      "Frappuccinos and blended drinks — high sugar",
      "Pastries and muffins — spike and crash",
      "Bagels with cream cheese — heavy pre-match"
    ],
    "notes": ["Eat ≥45 min before play. Oatmeal is the safest pre-match choice."]
  }
}
```

**Remaining 23 entries (stubs — populate before TestFlight):**

Each stub: `"id"`, `"display_name"`, `"match_aliases"`, `"category_hint"`, `"as_of": "TBD"`, `"suggestions": {}` — marked `[DRAFT — populate before TestFlight]`.

Chains: Panera Bread · Subway · Jersey Mike's · Jimmy John's · Firehouse Subs · Sweetgreen · CAVA · Panda Express · Chopt · Dunkin' · Einstein Bros. Bagels · Tropical Smoothie Cafe · Jamba · Five Guys · Shake Shack · Whataburger · In-N-Out · Domino's · Pizza Hut · Whole Foods · Sprouts · Qdoba · Moe's Southwest Grill

---

## §J — Migration Plan

**No new DB migration.** Next free number: 0017 (for reference only).

**Files changed:**

| File | Change |
|------|--------|
| `apps/api/src/playfuel_api/rules/chain_menus.json` | **NEW** — registry (§I schema, 3 full + 23 stubs) |
| `apps/api/src/playfuel_api/rules/chain_lookup.py` | **NEW** — `load_registry()`, `normalize_name()`, `lookup_chain(name: str) -> dict \| None`; loads JSON once at module import (no file I/O per request) |
| `apps/api/src/playfuel_api/models/api.py` | **MODIFY** `FoodOption` — add `chain_matched: bool = False` and `chain_as_of: Optional[str] = None` |
| `apps/api/src/playfuel_api/rules/food.py` | **MODIFY** `assemble_food_options` — after `categorize_place()`, call `lookup_chain(place.name)`: if match, use registry suggestions + set `chain_matched=True`, `chain_as_of=entry["as_of"]`; else use `suggestions_for(category)` + `chain_matched=False` |
| `apps/api/src/playfuel_api/tests/test_chain_menu_lookup.py` | **NEW** — ≥7 tests (see below) |
| `apps/ios/.../Models/FoodOption.swift` | **MODIFY** — add `let chainMatched: Bool` and `let chainAsOf: String?` |
| `apps/ios/.../Networking/DTOs.swift` | **MODIFY** `FoodOptionDTO` — add `chainMatched: Bool?` and `chainAsOf: String?`; `toModel()` maps both (nil → false / nil) |
| `apps/ios/.../Views/Sheets/FoodOptionDetailSheet.swift` | **MODIFY** — add chain caption, chain disclaimer, stale-data note (per §E); all gated on `option.chainMatched` |

**Required tests (≥7):**

| Test | AC |
|------|----|
| `test_lookup_chain_exact_match_chick_fil_a` | AC#1 — canonical alias match |
| `test_lookup_chain_store_number_stripped` | AC#1 — "Chick-fil-A #4521" normalizes correctly |
| `test_lookup_chain_no_match_returns_none` | AC#2 — unknown restaurant → None |
| `test_lookup_chain_case_insensitive` | AC#1 — "CHIPOTLE" → match |
| `test_assemble_food_options_chain_matched_uses_registry` | AC#1 + AC#5 — `FoodOption.chainMatched=True`, suggestions from registry |
| `test_assemble_food_options_unmatched_uses_category_template` | AC#2 + AC#5 — `FoodOption.chainMatched=False`, suggestions from `suggestions_for()` |
| `test_chain_menus_json_loads_without_error` | AC#5(c) — registry parses at startup |

**Backward compatibility:** `FoodOption` adds two new optional-with-default fields. Existing tests that construct `FoodOption` without these fields get `chain_matched=False`, `chain_as_of=None` — zero breakage. iOS `FoodOptionDTO` uses `decodeIfPresent` → nil → defaults on older API responses. No regressions expected.
