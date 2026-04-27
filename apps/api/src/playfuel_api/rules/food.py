"""Food rules engine — Phase 5 / Task #8.

Maps Google Place types[] → §F.1 food category enum.
Emits §F.3 restaurant order templates.
Assembles FoodOption list from raw Places results + scenario food buckets.

§F.3 TEMPLATE STATUS:
    fast_casual_bowl  — CONFIRMED (Chipotle bowl, verbatim from RULES_CONSTANTS_V1.md §F.3)
    sandwich_shop     — DRAFT (OQ-B: pending content review)
    grocery_prepared  — DRAFT (OQ-B: pending content review)
    breakfast_cafe    — DRAFT (OQ-B: pending content review)
    restaurant        — DRAFT (generic fallback)

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
    "fast_casual_bowl",   # confirmed — Chipotle, CAVA, similar
    "sandwich_shop",      # DRAFT — OQ-B
    "grocery_prepared",   # DRAFT — OQ-B
    "breakfast_cafe",     # DRAFT — OQ-B
    "restaurant",         # generic fallback
})

# ── Google types[] → category mapping ────────────────────────────────────────
#
# Order matters: first match wins. Name heuristics run before type mapping.
# Google types are not mutually exclusive — a place can have multiple types.

_TYPE_MAP: list[tuple[str, str]] = [
    ("meal_takeaway", "fast_casual_bowl"),  # refined further by name heuristic
    ("sandwich_shop", "sandwich_shop"),
    ("bakery", "breakfast_cafe"),
    ("cafe", "breakfast_cafe"),
    ("supermarket", "grocery_prepared"),
    ("grocery_store", "grocery_prepared"),
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
    """Return (order_text, is_draft) for the given food category.

    Falls back to the generic "restaurant" template if the category is unknown.

    Args:
        category: One of the CATEGORIES values.

    Returns:
        (order_text: str, is_draft: bool)
    """
    return _TEMPLATES.get(category, _TEMPLATES["restaurant"])


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
        order_text, is_draft = recommended_order_for(category)

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
