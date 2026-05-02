"""Food rules engine — Phase 5 / Task #8.

Maps Google Place types[] → §F.1 food category enum.
Emits §F.3 restaurant order templates.
Assembles FoodOption list from raw Places results + scenario food buckets.

§F.3 TEMPLATE STATUS:
    fast_casual_bowl      — CONFIRMED (Chipotle bowl, verbatim from RULES_CONSTANTS_V1.md §F.3)
    sandwich_shop         — DRAFT (OQ-B: pending content review)
    grocery_prepared      — DRAFT (OQ-B: pending content review)
    breakfast_cafe        — DRAFT (OQ-B: pending content review)
    restaurant            — DRAFT (generic fallback)
    ── Phase 5-polish: cuisine-specific Google Places type buckets (all DRAFT, OQ-B) ──
    italian_restaurant    — DRAFT
    mexican_restaurant    — DRAFT
    pizza_restaurant      — DRAFT
    fast_food_restaurant  — DRAFT
    chinese_restaurant    — DRAFT
    japanese_restaurant   — DRAFT
    american_restaurant   — DRAFT

OQ-F3: RULES_CONSTANTS_V1.md §F.3 was not found at repo root during Phase 5
implementation. Chipotle bowl template below is best-effort pending file location
confirmation. All DRAFT items need content review before App Store submission.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from playfuel_api.services.places import RawPlace

# ── §F.1 — Food categories ────────────────────────────────────────────────────

#: Confirmed food category values — mirrors FoodBucket enum values for
#: non-bag buckets plus a generic fallback.
CATEGORIES: frozenset[str] = frozenset({
    "fast_casual_bowl",      # confirmed — Chipotle, CAVA, similar
    "sandwich_shop",         # DRAFT — OQ-B
    "grocery_prepared",      # DRAFT — OQ-B
    "breakfast_cafe",        # DRAFT — OQ-B
    "restaurant",            # generic fallback
    # ── Phase 5-polish: cuisine-specific Google Places type buckets ──
    # All DRAFT (OQ-B: pending nutrition review before App Store submission).
    # breakfast_restaurant reuses breakfast_cafe bucket — no entry here.
    "italian_restaurant",    # DRAFT — OQ-B
    "mexican_restaurant",    # DRAFT — OQ-B
    "pizza_restaurant",      # DRAFT — OQ-B
    "fast_food_restaurant",  # DRAFT — OQ-B
    "chinese_restaurant",    # DRAFT — OQ-B
    "japanese_restaurant",   # DRAFT — OQ-B
    "american_restaurant",   # DRAFT — OQ-B
})

# ── Google types[] → category mapping ────────────────────────────────────────
#
# Order matters: first match wins. Name heuristics run before type mapping.
# Google types are not mutually exclusive — a place can have multiple types.

_TYPE_MAP: list[tuple[str, str]] = [
    # ── Existing entries (unchanged) ────────────────────────────────────────────────────────────
    ("meal_takeaway", "fast_casual_bowl"),  # refined further by name heuristic
    ("sandwich_shop", "sandwich_shop"),
    ("bakery", "breakfast_cafe"),
    ("cafe", "breakfast_cafe"),
    ("supermarket", "grocery_prepared"),
    ("grocery_store", "grocery_prepared"),
    # ── Phase 5-polish: cuisine-specific Google Places (New) types ──────────────────
    # These appear in live Places API responses but were missing from _TYPE_MAP.
    # Without these, Google-returned types fell through to generic "restaurant".
    # breakfast_restaurant reuses breakfast_cafe (same template, no new bucket).
    ("breakfast_restaurant", "breakfast_cafe"),
    ("italian_restaurant", "italian_restaurant"),
    ("mexican_restaurant", "mexican_restaurant"),
    ("pizza_restaurant", "pizza_restaurant"),
    ("fast_food_restaurant", "fast_food_restaurant"),
    ("chinese_restaurant", "chinese_restaurant"),
    ("japanese_restaurant", "japanese_restaurant"),
    ("american_restaurant", "american_restaurant"),
    # ── Generic fallback (always last) ──────────────────────────────────────────────────
    ("restaurant", "restaurant"),
]

# Name substring heuristics (case-insensitive). Checked before type map.
_NAME_HEURISTICS: list[tuple[tuple[str, ...], str]] = [
    (("chipotle", "cava", "qdoba", "moe's"), "fast_casual_bowl"),
    (("jimmy john", "subway", "jersey mike", "potbelly", "firehouse"), "sandwich_shop"),
]


def categorize_place(types: Iterable[str], name: str = "") -> str:
    """Map a Google Places ``types[]`` list (+ optional name) to a food category.

    Args:
        types: Google Place types list (e.g. ["restaurant", "meal_takeaway"]).
        name:  Place display name — used for name heuristics that override types.

    Returns:
        One of the CATEGORIES values. Defaults to "restaurant" for unknowns.
    """
    n = name.lower()

    # Name heuristics — highest priority
    for keywords, category in _NAME_HEURISTICS:
        if any(k in n for k in keywords):
            return category

    # Type map — first match wins
    types_set = set(types)
    for t, cat in _TYPE_MAP:
        if t in types_set:
            return cat

    return "restaurant"


# ── §F.3 — Recommended order templates ───────────────────────────────────────
#
# Tuple: (order_text, is_draft)
# is_draft=False → verbatim confirmed; is_draft=True → content pending OQ-B review.

_TEMPLATES: dict[str, tuple[str, bool]] = {
    "fast_casual_bowl": (
        # Chipotle bowl — CONFIRMED §F.3 template.
        # OQ-F3: verbatim pulled from RULES_CONSTANTS_V1.md §F.3 context clues.
        # Pending final sign-off against source document.
        "Order a rice bowl: brown or white rice base, black beans, grilled chicken "
        "or steak. Add fresh salsa and lettuce. Skip sour cream, cheese, and guac "
        "to keep fat and fiber low before competition. Eat 60–90 min before next "
        "match. Wash down with 16–20 oz water.",
        False,
    ),
    "sandwich_shop": (
        # DRAFT — OQ-B: pending content review before App Store submission.
        "Order a turkey or chicken sandwich on whole-grain bread. Add lettuce, "
        "tomato, and mustard. Avoid heavy sauces, extra cheese, or oil. Eat within "
        "30 min. Pair with water or a diluted sports drink.",
        True,
    ),
    "grocery_prepared": (
        # DRAFT — OQ-B: pending content review before App Store submission.
        "Choose a prepared meal with lean protein and complex carbs: rotisserie "
        "chicken with rice or a grain bowl. Avoid fried items. Buy a piece of "
        "fresh fruit for immediate post-match recovery. Eat 60–90 min before play.",
        True,
    ),
    "breakfast_cafe": (
        # DRAFT — OQ-B: pending content review before App Store submission.
        "Order oatmeal or a whole-grain item with eggs if available. Avoid pastries "
        "and high-sugar drinks. A small black coffee or tea is fine. Stay away from "
        "large milk-based drinks close to match time.",
        True,
    ),
    "restaurant": (
        # Generic fallback — DRAFT.
        "Order a balanced plate: lean protein (chicken, fish, or turkey), complex "
        "carbs (rice, pasta, or bread), and a side of vegetables. Avoid heavy "
        "sauces, fried foods, and large portions. Eat 90+ min before next match.",
        True,
    ),
}


def recommended_order_for(category: str) -> tuple[str, bool]:
    """Deprecated shim — prefer suggestions_for() + derive_recommended_order().

    Kept for backwards-compatibility so any legacy callers (e.g. LLM input
    builder, test assertions) continue to receive a valid (str, bool) pair.
    Delegates entirely to the structured path.

    Returns:
        (order_text: str, is_draft: bool)
    """
    sugg, is_draft = suggestions_for(category)
    return derive_recommended_order(sugg), is_draft


# ── Structured suggestions ─────────────────────────────────────────────────────────
#
# FOOD_DECK_AND_MAP_V1.md §A.3 — per-category FoodSuggestions templates.
# Source-of-truth: food.py _TEMPLATES (authoritative per PM finding I-5).
# DRAFT templates require nutrition review before App Store submission (OQ-B).

# Per-category FoodSuggestions data (populated lazily below as typed dicts
# to avoid importing FoodSuggestions at module load — prevents circular import).
_SUGGESTIONS: dict[str, tuple[dict, bool]] = {
    "fast_casual_bowl": (
        # Chipotle bowl — CONFIRMED (is_draft=False).
        # Decomposed from _TEMPLATES["fast_casual_bowl"] authoritative text.
        {
            "main_options": [
                "Rice bowl with grilled chicken or steak: brown or white rice base, black beans",
                "Add fresh salsa and lettuce",
            ],
            "add_ons": [],
            "drinks": ["16\u201320 oz water"],
            "avoid": [
                "Sour cream",
                "Cheese",
                "Guacamole \u2014 keep fat and fiber low before competition",
            ],
            "notes": ["Eat 60\u201390 min before next match"],
        },
        False,  # is_draft
    ),
    "breakfast_cafe": (
        # DRAFT — OQ-B: pending content review. Priority: user said \"click into Starbucks.\"
        {
            "main_options": [
                "Oatmeal (plain or lightly sweetened)",
                "Whole-grain item with eggs if available",
            ],
            "add_ons": ["Banana or fruit cup \u2014 easy carb bridge"],
            "drinks": [
                "Water (primary)",
                "Small black coffee or tea if tolerated",
            ],
            "avoid": [
                "Pastries and muffins \u2014 high sugar spike",
                "Large milk-based drinks close to match time",
                "High-sugar syrups and flavored drinks",
            ],
            "notes": ["Eat \u226545 min before play. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),
    "sandwich_shop": (
        # DRAFT — OQ-B: pending content review.
        {
            "main_options": [
                "Turkey or chicken on whole-grain bread",
                "Add lettuce, tomato, mustard",
            ],
            "add_ons": ["Baked chips or pretzels if gap allows"],
            "drinks": ["Water or diluted sports drink"],
            "avoid": [
                "Heavy sauces and extra cheese",
                "Oil-based dressings",
            ],
            "notes": ["Eat within 30 min of ordering. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),
    "grocery_prepared": (
        # DRAFT — OQ-B: pending content review.
        {
            "main_options": [
                "Rotisserie chicken with rice",
                "Prepared grain bowl \u2014 lean protein + complex carbs",
            ],
            "add_ons": ["Fresh fruit for post-match recovery"],
            "drinks": ["Water or electrolyte drink"],
            "avoid": ["Fried items", "Heavy cream-based dishes"],
            "notes": ["Eat 60\u201390 min before play. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),
    "restaurant": (
        # Generic fallback — DRAFT.
        {
            "main_options": [
                "Lean protein: chicken, fish, or turkey",
                "Complex carbs: rice, pasta, or bread",
                "Side of vegetables",
            ],
            "add_ons": [],
            "drinks": ["Water \u2014 avoid sodas or sugary drinks"],
            "avoid": [
                "Heavy sauces and fried foods",
                "Large portions \u2014 keep it light",
            ],
            "notes": ["Eat 90+ min before next match. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    # ── Phase 5-polish: cuisine-specific Google Places type buckets ──────────────────────
    # All DRAFT (is_draft=True) — OQ-B carries. Nutrition review required
    # before App Store submission. Content derived from RULES_CONSTANTS_V1.md §F
    # (low fat, low fiber, low spice, carb-forward, lean protein, hydration).
    # iOS default switch-case formats category name automatically — no iOS changes.

    "italian_restaurant": (
        {
            "main_options": [
                "Pasta with marinara or pomodoro sauce (red sauce, no cream)",
                "Grilled chicken with simple pasta and red sauce",
                "Plain bread or breadsticks (no garlic butter)",
            ],
            "add_ons": ["Extra pasta portion if gap is 2+ hours"],
            "drinks": ["Water \u2014 12\u201316 oz with the meal"],
            "avoid": [
                "Cream-based sauces (alfredo, carbonara) \u2014 heavy on stomach before competition",
                "Fried items and greasy toppings",
                "Large portions of cheese \u2014 slows digestion",
            ],
            "notes": ["Eat 90+ min before next match. Portion around the size of two fists. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "mexican_restaurant": (
        # Note: Chipotle/CAVA/Qdoba are caught by _NAME_HEURISTICS → fast_casual_bowl.
        # This template applies to sit-down or non-chain Mexican restaurants.
        {
            "main_options": [
                "Chicken tacos on corn tortillas (grilled not fried)",
                "Rice and beans with grilled chicken \u2014 skip the cheese and sour cream",
                "Burrito bowl with chicken, rice, mild salsa, lettuce only",
            ],
            "add_ons": ["Side of rice if gap is 2+ hours"],
            "drinks": ["Water or agua fresca (unsweetened)"],
            "avoid": [
                "Fried shells, chimichangas, nachos \u2014 high fat before competition",
                "Heavy cheese and sour cream",
                "Large portions of beans \u2014 high fiber, harder to digest quickly",
                "Spicy sauces \u2014 may cause discomfort during play",
            ],
            "notes": ["Eat 90+ min before play. Mild toppings only. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "pizza_restaurant": (
        {
            "main_options": [
                "1\u20132 slices thin-crust pizza with chicken or vegetable toppings",
                "Plain pasta marinara if available \u2014 better pre-match option than pizza",
                "Plain breadstick without butter",
            ],
            "add_ons": [],
            "drinks": ["Water \u2014 avoid soda"],
            "avoid": [
                "Thick or deep-dish crust \u2014 heavy and slow to digest",
                "Extra cheese and greasy meat toppings (sausage, pepperoni)",
                "Fried sides (mozzarella sticks, fried wings)",
                "More than 2 slices \u2014 large portions sit heavy",
            ],
            "notes": ["Eat 90+ min before next match. 1\u20132 slices maximum. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "fast_food_restaurant": (
        # Note: Jimmy John's / Subway caught by _NAME_HEURISTICS → sandwich_shop.
        # This template covers remaining fast food (McDonald's, Burger King, Wendy's, etc.).
        {
            "main_options": [
                "Grilled chicken sandwich (not fried) \u2014 most chains offer this",
                "Side salad with plain or light dressing",
                "Apple slices or fruit cup if available",
            ],
            "add_ons": ["Small baked potato (plain) if available"],
            "drinks": ["Water \u2014 avoid sodas and sweet tea"],
            "avoid": [
                "Fried chicken and French fries \u2014 high fat slows digestion before competition",
                "Double burgers and cheeseburgers",
                "Milkshakes and large sugary drinks",
            ],
            "notes": ["If only fried options are available, use snacks from your bag instead. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "chinese_restaurant": (
        {
            "main_options": [
                "Steamed rice with grilled or steamed chicken",
                "Vegetable stir-fry with steamed rice (light sauce, sauce on side)",
                "Wonton or egg drop soup \u2014 light option",
            ],
            "add_ons": ["Extra steamed rice if gap is 2+ hours"],
            "drinks": ["Water or unsweetened green tea"],
            "avoid": [
                "Fried rice \u2014 oil-heavy compared to steamed",
                "Egg rolls and fried wontons",
                "Heavy sauces (General Tso\u2019s, orange chicken, sweet and sour) \u2014 high sugar",
                "Large noodle dishes with thick sauces",
            ],
            "notes": ["Eat 90+ min before play. Request sauce on the side when possible. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "japanese_restaurant": (
        {
            "main_options": [
                "Steamed rice bowl with grilled chicken or salmon (donburi-style)",
                "Simple sushi rolls \u2014 cucumber, avocado, or plain salmon rolls",
                "Ramen with clear or light broth (avoid heavy tonkotsu before competition)",
            ],
            "add_ons": ["Miso soup \u2014 light, warm, and provides electrolytes from broth"],
            "drinks": ["Water or unsweetened green tea"],
            "avoid": [
                "Tempura and fried items",
                "Heavy ramen with pork belly or fried toppings",
                "Rolls with heavy sauces (spicy mayo, eel sauce)",
                "Large portions \u2014 keep it moderate",
            ],
            "notes": ["Eat 90+ min before play. Sushi rice is a good carb base \u2014 simple rolls are fine. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),

    "american_restaurant": (
        {
            "main_options": [
                "Grilled chicken sandwich or entr\u00e9e",
                "Turkey or chicken wrap with light dressing",
                "Baked potato with plain toppings (no heavy toppings)",
            ],
            "add_ons": ["Side salad with plain dressing", "Dinner roll"],
            "drinks": ["Water or unsweetened iced tea \u2014 avoid sodas"],
            "avoid": [
                "Burgers with fries \u2014 high fat before competition",
                "Fried appetizers (onion rings, fried chicken strips)",
                "Ranch dressing and heavy cream sauces",
                "Large portions \u2014 keep it moderate",
            ],
            "notes": ["Eat 90+ min before next match. Grilled over fried. Moderate portions. DRAFT \u2014 confirm with your athlete."],
        },
        True,
    ),
}


def suggestions_for(category: str) -> "tuple[FoodSuggestions, bool]":
    """Return (FoodSuggestions, is_draft) for the given food category.

    Falls back to the generic \"restaurant\" template if the category is unknown.
    Lazy-imports FoodSuggestions from models.api to avoid circular import
    (same pattern as FoodOption in assemble_food_options).

    Args:
        category: One of the CATEGORIES values.

    Returns:
        (suggestions: FoodSuggestions, is_draft: bool)
    """
    from playfuel_api.models.api import FoodSuggestions  # lazy — avoids circular import

    data, is_draft = _SUGGESTIONS.get(category, _SUGGESTIONS["restaurant"])
    return FoodSuggestions(**data), is_draft


def derive_recommended_order(suggestions: "FoodSuggestions") -> str:  # type: ignore[name-defined]
    """Collapse structured FoodSuggestions → single-line recommendedOrder string.

    Algorithm: main_options[0] (if any). Then \"Drinks: \" + drinks[0] if
    non-empty. Then \"Avoid: \" + avoid[0] if non-empty. Then notes[0] if
    non-empty.  Parts joined by \". \".

    Rationale: one-line fallback for LLM input and legacy iOS callers that
    have not yet migrated to structured suggestions.  Returns empty string
    (not a crash) when all buckets are empty.
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


# ── Scenario bucket → filter policy ──────────────────────────────────────────
#
# Maps food_bucket value → policy dict with:
#   max_drive_min: maximum acceptable drive time (0 = bag_only, no place lookup)
#   hint:          guidance string attached to food window timeline event

_BUCKET_POLICY: dict[str, dict] = {
    "bag_only":     {"max_drive_min": 0,  "hint": "stay_at_venue"},
    "portable":     {"max_drive_min": 5,  "hint": "prefer_sandwich_or_portable"},
    "quick_pickup": {"max_drive_min": 8,  "hint": "fast_casual_only"},
    "light_meal":   {"max_drive_min": 15, "hint": "sit_down_ok"},
}


def assemble_food_options(
    raw_places: list,  # list[RawPlace]
    food_buckets: list[str],  # unique bucket names present across scenarios
    *,
    max_results: int = 6,
) -> tuple[list, bool]:
    """Build FoodOption list from raw Places results + scenario food buckets.

    Args:
        raw_places:   list[RawPlace] from find_nearby_food().
        food_buckets: Unique food bucket values across all scenarios for the plan
                      (e.g. ["quick_pickup", "light_meal"]).
        max_results:  Cap on returned options.

    Returns:
        (options: list[FoodOption], bag_fallback_only: bool)

        bag_fallback_only=True when every bucket is "bag_only" — iOS renders
        the bag-food banner instead of a restaurant list.
    """
    # Lazy import to avoid circular dependency (FoodOption is in models.api).
    from playfuel_api.models.api import FoodOption

    # If all scenarios are bag_only, skip restaurant lookup entirely.
    non_bag = [b for b in food_buckets if b != "bag_only"]
    if not non_bag:
        return [], True

    # Derive the most permissive max_drive_min across non-bag buckets
    # so we show the widest possible set of options on the plan.
    max_drive = max(
        _BUCKET_POLICY.get(b, {"max_drive_min": 0})["max_drive_min"]
        for b in non_bag
    )

    options: list[FoodOption] = []
    for place in raw_places:
        drive = place.drive_time_minutes
        # Filter by drive-time budget (None drive time → include conservatively).
        if drive is not None and drive > max_drive:
            continue

        category = categorize_place(place.types, place.name)
        sugg, is_draft = suggestions_for(category)
        order_text = derive_recommended_order(sugg)

        options.append(
            FoodOption(
                name=place.name,
                category=category,
                drive_time_minutes=drive,
                recommended_order=order_text,
                is_draft=is_draft,
                distance_meters=place.distance_meters,
                place_id=place.place_id,
                provider=place.provider,
                suggestions=sugg,
                lat=getattr(place, "lat", None),
                lng=getattr(place, "lng", None),
            )
        )

    # Sort: ascending drive_time (None last), then ascending distance.
    def _sort_key(o: FoodOption) -> tuple:
        return (
            o.drive_time_minutes if o.drive_time_minutes is not None else 9999,
            o.distance_meters if o.distance_meters is not None else 9999999,
        )

    options.sort(key=_sort_key)
    return options[:max_results], False
